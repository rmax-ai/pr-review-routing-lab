"""Codex-compatible subprocess shim.

The shim has no provider dependency.  It accepts one JSON object on stdout and
keeps all provider prose out of typed machine fields.
"""

from __future__ import annotations

import json
import os
import shlex
import signal
import subprocess
import time
from pathlib import Path
from typing import Any

from ..digests import digest_obj
from ..models import HarnessId, ReviewVerdict
from ..util import communicate_bounded, scrub_text
from .base import ReviewerHarness
from .mock import packet_digest_from_dir, packet_files, packet_integrity

MAX_OUTPUT_BYTES = 1_000_000
MAX_TIMEOUT_S = 90.0


class CodexHarness(ReviewerHarness):
    lane = HarnessId.codex.value

    def command(
        self,
        packet_dir: str | Path,
        model: str = "gpt-6-sol",
        effort: str = "low",
    ) -> list[str]:
        template = os.environ.get(
            "REVIEW_LAB_CODEX_CMD",
            "codex exec -C {packet} -m {model} "
            "-c model_reasoning_effort={effort} --skip-git-repo-check",
        )
        if not isinstance(template, str) or not template.strip():
            raise ValueError("REVIEW_LAB_CODEX_CMD must be a non-empty template")
        values = {
            "packet": shlex.quote(str(packet_dir)),
            "model": shlex.quote(str(model)),
            "effort": shlex.quote(str(effort)),
        }
        try:
            rendered = template.format_map(values)
            return shlex.split(rendered)
        except (KeyError, ValueError) as exc:
            raise ValueError("invalid Codex command template") from exc

    def assemble_command(
        self,
        packet_dir: str | Path,
        model: str = "gpt-6-sol",
        effort: str = "low",
    ) -> list[str]:
        return self.command(packet_dir, model, effort)

    def run(
        self,
        packet_dir: str | Path,
        model: str = "gpt-6-sol",
        effort: str = "low",
        timeout_s: float = 90,
    ) -> ReviewVerdict:
        packet = Path(packet_dir)
        before = packet_files(packet)
        packet_digest = packet_digest_from_dir(packet)
        started = time.monotonic()
        process: subprocess.Popen[bytes] | None = None
        bounded_timeout = _clamp_timeout(timeout_s)
        try:
            process = subprocess.Popen(
                self.command(packet, model, effort),
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=str(packet),
                start_new_session=True,
            )
            if process.stdin is not None:
                process.stdin.write(b"Return one ReviewVerdict JSON object only.\n")
                process.stdin.close()
            captured = communicate_bounded(
                process,
                timeout_s=bounded_timeout,
                max_output_bytes=MAX_OUTPUT_BYTES,
                kill=lambda: _kill(process),
            )
            stdout = captured.stdout.decode("utf-8", errors="replace")
            stderr = captured.stderr.decode("utf-8", errors="replace")
            if captured.timed_out:
                if stderr:
                    self._write_sidecar(packet, stderr)
                return self._error(
                    packet, model, effort, "reviewer_timeout", packet_digest, started
                )
            if captured.output_limited:
                if stderr:
                    self._write_sidecar(packet, stderr)
                return self._error(
                    packet, model, effort, "reviewer_invalid_verdict", packet_digest, started
                )
        except FileNotFoundError:
            return self._error(
                packet, model, effort, "reviewer_binary_missing", packet_digest, started
            )
        except (OSError, ValueError):
            return self._error(
                packet, model, effort, "reviewer_invalid_verdict", packet_digest, started
            )
        finally:
            if process is not None and process.poll() is None:
                _kill(process)
        if stderr:
            self._write_sidecar(packet, stderr)
        if not packet_integrity(packet) or before != packet_files(packet):
            return self._error(
                packet, model, effort, "reviewer_packet_mutated", packet_digest, started
            )
        if process is None or process.returncode:
            code = process.returncode if process is not None else 1
            return self._error(
                packet, model, effort, f"reviewer_exit_{code}", packet_digest, started
            )
        try:
            value = parse_single_json(stdout)
            verdict = ReviewVerdict.model_validate_json(json.dumps(value))
        except (TypeError, ValueError):
            return self._error(
                packet, model, effort, "reviewer_invalid_verdict", packet_digest, started
            )
        case_path = packet / "case.json"
        if case_path.exists():
            try:
                packet_case = json.loads(case_path.read_text(encoding="utf-8"))
            except (OSError, UnicodeError, ValueError):
                return self._error(packet, model, effort, "invalid_record", packet_digest, started)
            expected = {
                "case_ref": packet_case.get("case_ref"),
                "case_digest": packet_case.get("case_digest"),
                "head_digest": packet_case.get("head_digest"),
                "packet_digest": packet_digest,
            }
            if any(
                expected[key] is not None and getattr(verdict, key) != expected[key]
                for key in expected
            ):
                return self._error(packet, model, effort, "invalid_record", packet_digest, started)
            if verdict.harness != HarnessId.codex:
                return self._error(packet, model, effort, "invalid_record", packet_digest, started)
            if verdict.model != model or verdict.effort != effort:
                return self._error(packet, model, effort, "invalid_record", packet_digest, started)
        return verdict

    def _write_sidecar(self, packet: Path, text: str) -> None:
        raw = packet.parent / "raw"
        raw.mkdir(exist_ok=True)
        (raw / "codex.stderr").write_text(scrub_text(text), encoding="utf-8")

    def _error(
        self,
        packet: Path,
        model: str,
        effort: str,
        error: str,
        packet_digest: str,
        started: float,
    ) -> ReviewVerdict:
        return ReviewVerdict(
            case_ref=digest_obj({"case": packet.name})[:12],
            case_id=f"packet_{packet.name}",
            case_digest=digest_obj({"case": packet.name}),
            head_digest=digest_obj({"head": packet.name}),
            packet_digest=packet_digest if len(packet_digest) == 64 else digest_obj({}),
            verdict="human_decision",
            model=model,
            effort=effort,
            harness=HarnessId.codex,
            latency_ms=max(0, int((time.monotonic() - started) * 1000)),
            error=error,
        )


def parse_single_json(text: str) -> dict[str, Any]:
    """Parse exactly one JSON object, allowing surrounding whitespace only."""

    value = text.strip()
    decoder = json.JSONDecoder()
    try:
        first, end = decoder.raw_decode(value)
    except json.JSONDecodeError as exc:
        raise ValueError("no JSON object") from exc
    if not isinstance(first, dict) or value[end:].strip():
        raise ValueError("ambiguous JSON output")
    return first


def _last_json(text: str) -> dict[str, Any]:
    """Backward-compatible name for the strict single-object parser."""

    return parse_single_json(text)


def _kill(process: subprocess.Popen[bytes]) -> None:
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except (OSError, ProcessLookupError):
        try:
            process.kill()
        except OSError:
            pass


def _clamp_timeout(value: float) -> float:
    try:
        return min(max(float(value), 0.01), MAX_TIMEOUT_S)
    except (TypeError, ValueError) as exc:
        raise ValueError("timeout must be numeric") from exc
