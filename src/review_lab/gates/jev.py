"""Offline-first Jev adapter with a strictly validated JSON boundary."""

from __future__ import annotations

import json
import math
import os
import shutil
import signal
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from ..models import DataSource, QuestionAnswer, UsageCost
from ..question_sets import CANONICAL_QUESTION_IDS, LEGACY_COMPACT_GATE_A_IDS
from ..util import canonical_bytes, communicate_bounded, read_yaml, scrub_text

MAX_OUTPUT_BYTES = 1_000_000
MAX_TIMEOUT_S = 90.0
ERRORS = {
    "jev_binary_missing",
    "jev_cap_refused",
    "jev_schema_invalid",
    "jev_missing_answer",
    "jev_distribution_invalid",
    "jev_timeout",
    "jev_audit_partial",
}


@dataclass(frozen=True)
class JevResult:
    answers: list[QuestionAnswer]
    usage: UsageCost | None
    latency_ms: int = 0
    error: str | None = None
    raw_envelope_ref: str | None = None
    fixture_version: str = "mock-v1"


class JevAdapter:
    """One interface for the deterministic mock and opt-in live subprocess."""

    def __init__(
        self,
        *,
        fixture_root: str | Path | None = None,
        packet_workdir: str | Path | None = None,
        raw_dir: str | Path | None = None,
    ):
        self.fixture_root = Path(fixture_root) if fixture_root else None
        self.packet_workdir = Path(packet_workdir) if packet_workdir else None
        self.raw_dir = Path(raw_dir) if raw_dir else None

    def evaluate(
        self,
        backend: str,
        question_set: Any,
        state: dict[str, Any],
        questions: dict[str, Any] | list[dict[str, Any]],
        tag: str,
        timeout_s: float = 90,
    ) -> JevResult:
        try:
            gate, expected = _question_contract(question_set)
        except (TypeError, ValueError):
            return JevResult([], None, error="jev_schema_invalid")
        if backend == "mock":
            return self._mock(gate, expected, questions, tag, state)
        if backend == "live":
            return self._live(gate, expected, state, questions, tag, timeout_s)
        return JevResult([], None, error="jev_schema_invalid")

    def _mock(
        self,
        gate: str,
        expected: dict[str, str],
        questions: dict[str, Any] | list[dict[str, Any]],
        tag: str,
        state: dict[str, Any],
    ) -> JevResult:
        started = time.monotonic()
        envelope: Any = questions
        compact = _is_bool_mapping(envelope)
        compact_values = dict(envelope) if compact else None
        if compact:
            keys = set(envelope)
            canonical = set(CANONICAL_QUESTION_IDS[gate])
            if keys != canonical and not (
                gate == "gate_a" and keys.issubset(LEGACY_COMPACT_GATE_A_IDS)
            ):
                return JevResult([], None, _elapsed(started), "jev_schema_invalid")
            # Compact mappings are a deliberately narrow compatibility
            # shorthand.  Full canonical mappings remain contract-checked;
            # only registered legacy keys may use a reduced mapping.
            expected = {key: "boolean" for key in envelope}
        path = _fixture_path(self.fixture_root, tag, gate)
        if path is not None and path.exists():
            if path.is_symlink():
                return JevResult([], None, _elapsed(started), "jev_schema_invalid")
            try:
                envelope = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, UnicodeError, ValueError):
                return JevResult([], None, _elapsed(started), "jev_schema_invalid")
            compact_values = None
        # A compact mapping of question->bool is useful in unit tests and is
        # converted to the same full envelope used by recorded fixtures.
        if compact_values is not None:
            envelope = {
                "ok": True,
                "answers": [
                    {
                        "id": key,
                        "type": "boolean",
                        "value": value,
                        "probabilities": {
                            "true": 1.0 if value else 0.0,
                            "false": 0.0 if value else 1.0,
                        },
                        "derived_confidence": 1.0,
                    }
                    for key, value in sorted(compact_values.items())
                ],
                "usage": {},
            }
        if (path is None or not path.exists()) and state and compact_values is not None:
            envelope = dict(envelope)
            for key in ("case_digest", "head_digest", "packet_digest"):
                if key in state:
                    envelope[key] = state[key]
        result = self._validate_envelope(envelope, expected, DataSource.simulated, started, state)
        return JevResult(
            result.answers,
            result.usage,
            0,
            result.error,
            result.raw_envelope_ref,
            result.fixture_version,
        )

    def _live(
        self,
        gate: str,
        expected: dict[str, str],
        state: dict[str, Any],
        questions: dict[str, Any] | list[dict[str, Any]],
        tag: str,
        timeout_s: float,
    ) -> JevResult:
        del gate
        binary = os.environ.get("REVIEW_LAB_JEV_BIN", "jev")
        binary_path = shutil.which(binary)
        if binary_path is None:
            return JevResult([], None, error="jev_binary_missing")
        if os.environ.get("REVIEW_LAB_JEV_BATCH") == "1":
            return JevResult([], None, error="jev_cap_refused")
        parent = self.packet_workdir
        if parent is not None:
            try:
                parent.mkdir(parents=True, exist_ok=True)
            except OSError:
                return JevResult([], None, error="jev_schema_invalid")
        try:
            temporary = tempfile.TemporaryDirectory(
                prefix="review-lab-jev-",
                dir=str(parent) if parent is not None else None,
            )
        except OSError:
            return JevResult([], None, error="jev_schema_invalid")
        root = Path(temporary.name)
        state_file = root / f"jev-state-{os.getpid()}.json"
        question_file = root / f"jev-questions-{os.getpid()}.json"
        started = time.monotonic()
        process: subprocess.Popen[bytes] | None = None
        try:
            state_file.write_bytes(canonical_bytes(state))
            question_file.write_bytes(canonical_bytes(questions))
            command = [
                binary_path,
                "decide",
                "--state-json-file",
                str(state_file),
                "--questions-file",
                str(question_file),
                "--tag",
                tag,
                "--json",
            ]
            process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                start_new_session=True,
                cwd=str(root),
            )
            captured = communicate_bounded(
                process,
                timeout_s=_clamp_timeout(timeout_s),
                max_output_bytes=MAX_OUTPUT_BYTES,
                kill=lambda: _kill_process_group(process),
            )
            stdout = captured.stdout.decode("utf-8", errors="replace")
            stderr = captured.stderr.decode("utf-8", errors="replace")
            if captured.timed_out:
                self._write_sidecar(tag, stdout, stderr)
                return JevResult([], None, _elapsed(started), "jev_timeout")
            if captured.output_limited:
                self._write_sidecar(tag, stdout, stderr)
                return JevResult([], None, _elapsed(started), "jev_schema_invalid")
            if process.returncode != 0:
                self._write_sidecar(tag, stdout, stderr)
                return JevResult([], None, _elapsed(started), f"jev_exit_{process.returncode}")
            try:
                envelope = json.loads(stdout)
            except (TypeError, UnicodeError, ValueError):
                self._write_sidecar(tag, stdout, stderr)
                return JevResult([], None, _elapsed(started), "jev_schema_invalid")
            if stderr:
                self._write_sidecar(tag, "", stderr)
            return self._validate_envelope(envelope, expected, DataSource.measured, started, state)
        except FileNotFoundError:
            return JevResult([], None, _elapsed(started), "jev_binary_missing")
        except (OSError, TypeError, ValueError):
            return JevResult([], None, _elapsed(started), "jev_schema_invalid")
        finally:
            for path in (state_file, question_file):
                try:
                    path.unlink()
                except FileNotFoundError:
                    pass
            if process is not None and process.poll() is None:
                _kill_process_group(process)
            temporary.cleanup()

    def _write_sidecar(self, tag: str, stdout: str, stderr: str) -> str | None:
        target = self.raw_dir or (
            self.packet_workdir.parent if self.packet_workdir is not None else None
        )
        if target is None:
            return None
        target.mkdir(parents=True, exist_ok=True)
        safe_tag = "".join(char if char.isalnum() else "_" for char in tag)[:80]
        path = target / f"jev-{safe_tag}.raw"
        path.write_text(scrub_text(stdout) + "\n" + scrub_text(stderr), encoding="utf-8")
        return str(path)

    @staticmethod
    def _validate_envelope(
        envelope: Any,
        expected: dict[str, str],
        source: DataSource,
        started: float,
        identity: dict[str, Any] | None = None,
    ) -> JevResult:
        if not isinstance(envelope, dict) or envelope.get("ok") is not True:
            return JevResult([], None, _elapsed(started), "jev_schema_invalid")
        allowed_envelope = {
            "ok",
            "answers",
            "usage",
            "case_digest",
            "head_digest",
            "packet_digest",
            "fixture_version",
        }
        if set(envelope) - allowed_envelope:
            return JevResult([], None, _elapsed(started), "jev_schema_invalid")
        if "fixture_version" in envelope and not isinstance(envelope["fixture_version"], str):
            return JevResult([], None, _elapsed(started), "jev_schema_invalid")
        for key in ("case_digest", "head_digest", "packet_digest"):
            if identity and key in envelope and envelope[key] != identity.get(key):
                return JevResult([], None, _elapsed(started), "jev_audit_partial")
        raw_answers = envelope.get("answers")
        if not isinstance(raw_answers, list):
            return JevResult([], None, _elapsed(started), "jev_schema_invalid")
        for raw_answer in raw_answers:
            if not isinstance(raw_answer, dict):
                return JevResult([], None, _elapsed(started), "jev_schema_invalid")
            probabilities = raw_answer.get("probabilities")
            if not isinstance(probabilities, dict) or not probabilities:
                return JevResult([], None, _elapsed(started), "jev_distribution_invalid")
            values = list(probabilities.values())
            if (
                any(
                    isinstance(value, bool)
                    or not isinstance(value, (int, float))
                    or not math.isfinite(float(value))
                    or float(value) < 0.0
                    or float(value) > 1.0
                    for value in values
                )
                or abs(sum(float(value) for value in values) - 1.0) > 1e-6
            ):
                return JevResult([], None, _elapsed(started), "jev_distribution_invalid")
        try:
            answers = [QuestionAnswer.model_validate(answer) for answer in raw_answers]
        except ValidationError:
            return JevResult([], None, _elapsed(started), "jev_schema_invalid")
        ids = [answer.id for answer in answers]
        if len(ids) != len(set(ids)):
            return JevResult([], None, _elapsed(started), "jev_missing_answer")
        if not set(expected).issubset(ids):
            return JevResult([], None, _elapsed(started), "jev_missing_answer")
        if set(ids) - set(expected):
            return JevResult([], None, _elapsed(started), "jev_schema_invalid")
        if any(answer.type != expected[answer.id] for answer in answers):
            return JevResult([], None, _elapsed(started), "jev_schema_invalid")
        usage_raw = envelope.get("usage") or {}
        if not isinstance(usage_raw, dict):
            return JevResult([], None, _elapsed(started), "jev_schema_invalid")
        if set(usage_raw) - {
            "input_tokens",
            "output_tokens",
            "usd",
            "latency_ms",
            "model",
            "usage_source",
        }:
            return JevResult([], None, _elapsed(started), "jev_schema_invalid")
        try:
            usage_available = any(
                usage_raw.get(key) is not None
                for key in ("input_tokens", "output_tokens", "usd", "latency_ms")
            )
            usage_source = usage_raw.get("usage_source")
            if usage_source is None:
                usage_source = "available" if usage_available else "unavailable"
            if usage_source not in {"available", "unavailable"}:
                return JevResult([], None, _elapsed(started), "jev_schema_invalid")
            usage = UsageCost(
                input_tokens=usage_raw.get("input_tokens"),
                output_tokens=usage_raw.get("output_tokens"),
                usd=usage_raw.get("usd"),
                latency_ms=usage_raw.get("latency_ms"),
                source=source,
                component="jev",
                model=usage_raw.get("model", "jev"),
                usage_source=usage_source,
            )
        except ValidationError:
            return JevResult([], None, _elapsed(started), "jev_schema_invalid")
        return JevResult(
            sorted(answers, key=lambda answer: answer.id),
            usage,
            _elapsed(started),
            None,
            fixture_version=str(envelope.get("fixture_version", "mock-v1")),
        )


def _elapsed(started: float) -> int:
    return max(0, int((time.monotonic() - started) * 1000))


def _clamp_timeout(value: float) -> float:
    try:
        return min(max(float(value), 0.01), MAX_TIMEOUT_S)
    except (TypeError, ValueError) as exc:
        raise ValueError("timeout must be numeric") from exc


def _kill_process_group(process: subprocess.Popen[bytes]) -> None:
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except (OSError, ProcessLookupError):
        try:
            process.kill()
        except OSError:
            pass


def _is_bool_mapping(value: Any) -> bool:
    return (
        isinstance(value, dict)
        and bool(value)
        and all(isinstance(item, bool) for item in value.values())
    )


def _question_contract(question_set: Any) -> tuple[str, dict[str, str]]:
    if isinstance(question_set, (str, Path)):
        text = str(question_set)
        path = Path(text)
        if path.exists():
            raw = read_yaml(path)
        else:
            normalized = text.replace("-", "_")
            if normalized not in {"gate_a", "gate_b"}:
                raise ValueError("unknown question set")
            gate = normalized
            # Accept only canonical questions in the default contract.
            canonical = {key: "boolean" for key in sorted(CANONICAL_QUESTION_IDS[gate])}
            return gate, canonical
    else:
        raw = question_set
    if isinstance(raw, dict):
        unknown = set(raw) - {"id", "gate", "instructions", "questions"}
        if unknown:
            raise ValueError(f"unknown question set fields: {sorted(unknown)}")
        gate = str(raw.get("id") or raw.get("gate") or "gate_a")
        if "questions" not in raw:
            raise ValueError("question set questions are required")
        raw_questions = raw.get("questions", [])
        if not raw_questions:
            raise ValueError("question set questions are required")
    else:
        gate, raw_questions = "gate_a", raw
        if raw_questions == []:
            raise ValueError("question set questions are required")
    gate = gate.replace("-", "_")
    if gate not in {"gate_a", "gate_b"}:
        raise ValueError("unknown question set")
    expected: dict[str, str] = {}
    for item in raw_questions or []:
        if isinstance(item, str):
            expected[item] = "boolean"
        elif isinstance(item, dict) and "id" in item:
            if set(item) - {"id", "type"}:
                raise ValueError("unknown question fields")
            expected[str(item["id"])] = str(item.get("type", "boolean"))
        else:
            raise ValueError("question entries must contain an id")
    if not expected:
        expected = {key: "boolean" for key in sorted(CANONICAL_QUESTION_IDS[gate])}
    if gate in CANONICAL_QUESTION_IDS and set(expected) != set(CANONICAL_QUESTION_IDS[gate]):
        raise ValueError("question set does not match the registered contract")
    if any(value != "boolean" for value in expected.values()):
        raise ValueError("registered questions must be boolean")
    return gate, expected


def _fixture_path(root: Path | None, tag: str, gate: str) -> Path | None:
    if root is None:
        return None
    tag_parts = tag.split(":")
    case_ref = tag_parts[0]
    case_id = tag_parts[1] if len(tag_parts) > 2 else case_ref
    candidates = [
        root / case_ref / f"jev_{gate}.json",
        root / case_ref / f"jev_{gate.replace('gate_', 'gate-')}.json",
        root / case_id / f"jev_{gate}.json",
        root / case_id / f"jev_{gate.replace('gate_', 'gate-')}.json",
        root / "jev" / f"{gate}.json",
        root / "jev" / f"{gate.replace('gate_', 'gate-')}.json",
        root / "jev" / case_id / f"{gate}.json",
        root / f"{case_ref}_jev_{gate}.json",
        root / f"jev_{gate}.json",
        root / f"jev_{gate.replace('gate_', 'gate-')}.json",
    ]
    return next((candidate for candidate in candidates if candidate.exists()), candidates[0])
