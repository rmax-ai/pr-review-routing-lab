"""Fixture-backed reviewer harness used by every default/offline run."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

from ..digests import digest_obj, file_digest
from ..digests import packet_digest as make_packet_digest
from ..models import DataSource, HarnessId, ReviewVerdict, UsageCost
from ..util import read_yaml
from .base import ReviewerHarness


def packet_files(packet: Path) -> dict[str, str]:
    root = Path(packet)
    return {
        str(path.relative_to(root)): file_digest(path)
        for path in sorted(path for path in root.rglob("*") if path.is_file())
        if path != root / "packet_manifest.json"
    }


def packet_digest_from_dir(packet: str | Path) -> str:
    root = Path(packet)
    manifest = root / "packet_manifest.json"
    if manifest.exists():
        raw = json.loads(manifest.read_text(encoding="utf-8"))
        return str(raw.get("packet_digest", ""))
    return make_packet_digest(packet_files(root), "")


def packet_integrity(packet: Path) -> bool:
    return verify_packet_manifest(packet)


def verify_packet_manifest(packet: str | Path) -> bool:
    """Verify a packet manifest and all files it covers."""

    root = Path(packet)
    manifest_path = root / "packet_manifest.json"
    if root.is_symlink() or manifest_path.is_symlink() or not manifest_path.exists():
        return False
    try:
        raw = json.loads(manifest_path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            return False
        expected = raw.get("files")
        if not isinstance(expected, dict):
            return False
        actual = packet_files(root)
        template = str(raw.get("prompt_template_digest", raw.get("template_digest", "")))
    except (OSError, UnicodeError, TypeError, ValueError):
        return False
    return expected == actual and raw.get("packet_digest") == make_packet_digest(actual, template)


class MockHarness(ReviewerHarness):
    """Return a typed, explicitly simulated verdict from a JSON/YAML fixture."""

    def __init__(
        self,
        fixture: str | Path | dict[str, Any] | None = None,
        lane: HarnessId = HarnessId.mock_codex,
    ):
        self.fixture = fixture
        self.lane = lane.value

    def _load(self, packet: Path) -> dict[str, Any]:
        raw: Any = {}
        if isinstance(self.fixture, dict):
            raw = self.fixture
        elif self.fixture:
            path = Path(self.fixture)
            raw = (
                json.loads(path.read_text(encoding="utf-8"))
                if path.suffix.lower() == ".json"
                else read_yaml(path)
            )
        if not raw:
            raw = {}
        if not isinstance(raw, dict):
            raise TypeError("mock fixture must be an object")
        return dict(raw)

    def run(
        self,
        packet_dir: str | Path,
        model: str = "gpt-6-sol",
        effort: str = "low",
        timeout_s: float = 90,
    ) -> ReviewVerdict:
        del timeout_s
        packet = Path(packet_dir)
        before = packet_files(packet)
        try:
            raw = self._load(packet)
        except (OSError, UnicodeError, TypeError, ValueError, yaml.YAMLError):
            raw = {"error": "reviewer_invalid_verdict"}
        used_gold = raw.pop("used_gold", None)
        if used_gold is not None and used_gold is not False:
            raw["error"] = "invalid_record"
            raw["verdict"] = "human_decision"
        failure = next(
            (
                raw.pop(key, None)
                for key in ("failure", "inject_failure", "failure_injection", "failure_mode")
                if raw.get(key) is not None
            ),
            None,
        )
        if failure is not None:
            failure_text = str(failure).casefold()
            failure_map = (
                ("timeout", "reviewer_timeout"),
                ("packet", "reviewer_packet_mutated"),
                ("invalid", "reviewer_invalid_verdict"),
                ("schema", "reviewer_invalid_verdict"),
            )
            raw["error"] = next(
                (code for keyword, code in failure_map if keyword in failure_text),
                "reviewer_invalid_verdict",
            )
            raw["verdict"] = "human_decision"
        if set(raw) - set(ReviewVerdict.model_fields):
            existing_error = raw.get("error")
            raw = {
                **{
                    key: value
                    for key, value in raw.items()
                    if key in ReviewVerdict.model_fields
                },
                "error": existing_error or "reviewer_invalid_verdict",
            }
        if "used_gold:true" in str(raw.get("fixture_provenance", "")).replace(" ", "").lower():
            raw["error"] = "invalid_record"
            raw["verdict"] = "human_decision"
        packet_case: dict[str, Any] = {}
        packet_case_path = packet / "case.json"
        if packet_case_path.exists():
            try:
                packet_case = json.loads(packet_case_path.read_text(encoding="utf-8"))
            except (OSError, UnicodeError, ValueError):
                raw["error"] = "reviewer_invalid_verdict"
        expected_case_digest = packet_case.get("case_digest")
        expected_head_digest = packet_case.get("head_digest")
        expected_case_ref = packet_case.get("case_ref")
        try:
            packet_digest = packet_digest_from_dir(packet)
        except (OSError, UnicodeError, TypeError, ValueError):
            packet_digest = ""
        if len(packet_digest) != 64:
            packet_digest = digest_obj({"packet": packet.name, "files": before})
        if (
            (
                raw.get("case_digest")
                and expected_case_digest
                and raw["case_digest"] != expected_case_digest
            )
            or (
                raw.get("head_digest")
                and expected_head_digest
                and raw["head_digest"] != expected_head_digest
            )
            or (raw.get("case_ref") and expected_case_ref and raw["case_ref"] != expected_case_ref)
            or (raw.get("packet_digest") and raw["packet_digest"] != packet_digest_from_dir(packet))
        ):
            raw["error"] = "invalid_record"
            raw["verdict"] = "human_decision"
            if expected_case_digest:
                raw["case_digest"] = expected_case_digest
            if expected_head_digest:
                raw["head_digest"] = expected_head_digest
            if expected_case_ref:
                raw["case_ref"] = expected_case_ref
            raw["packet_digest"] = packet_digest
        case_digest = str(
            expected_case_digest or raw.get("case_digest") or digest_obj({"case": packet.name})
        )
        head_digest = str(
            expected_head_digest or raw.get("head_digest") or digest_obj({"head": packet.name})
        )
        raw.setdefault("case_ref", expected_case_ref or digest_obj({"case": packet.name})[:12])
        raw.setdefault("case_id", f"packet_{packet.name}")
        raw.setdefault("case_digest", case_digest)
        raw.setdefault("head_digest", head_digest)
        raw.setdefault("packet_digest", packet_digest)
        raw.setdefault("verdict", "accept")
        raw.setdefault("requirement_coverage", [])
        raw.setdefault("findings", [])
        raw.setdefault("unresolved_human_decisions", [])
        raw["model"] = model
        raw["effort"] = effort
        raw["harness"] = self.lane
        raw["fixture_provenance"] = (
            "simulated;author=synthetic;method=fixture;version=mock-v1;used_gold:false"
        )
        usage_raw = raw.get("usage")
        if isinstance(usage_raw, dict):
            # Keep availability at the envelope level for latency-only mock
            # observations; token and cost metrics independently reject
            # incomplete or unpriced available rows instead of treating them
            # as fabricated zeros.
            usage_available = any(
                usage_raw.get(key) is not None
                for key in ("input_tokens", "output_tokens", "usd", "latency_ms")
            )
            raw["usage"] = {
                **usage_raw,
                "source": "simulated",
                "component": "sol_review",
                "usage_source": (
                    usage_raw.get("usage_source")
                    if usage_raw.get("usage_source") is not None
                    else "available" if usage_available else "unavailable"
                ),
            }
        raw.setdefault(
            "usage",
            {
                "input_tokens": None,
                "output_tokens": None,
                "usd": None,
                "latency_ms": None,
                "source": "simulated",
                "component": "sol_review",
                "model": model,
                "usage_source": "unavailable",
            },
        )
        try:
            intact = packet_integrity(packet)
            unchanged = before == packet_files(packet)
        except (OSError, UnicodeError, TypeError, ValueError):
            intact = False
            unchanged = False
        if not intact or not unchanged:
            raw["error"] = "reviewer_packet_mutated"
            raw["verdict"] = "human_decision"
        try:
            verdict = ReviewVerdict.model_validate_json(json.dumps(raw))
        except (TypeError, ValueError):
            verdict = self._fallback(
                packet,
                model=model,
                effort=effort,
                case_ref=expected_case_ref or case_digest[:12],
                case_digest=case_digest,
                head_digest=head_digest,
                packet_digest=packet_digest,
                error="reviewer_invalid_verdict",
            )
        return verdict

    def _fallback(
        self,
        packet: Path,
        *,
        model: str,
        effort: str,
        case_ref: str,
        case_digest: str,
        head_digest: str,
        packet_digest: str,
        error: str,
    ) -> ReviewVerdict:
        """Return a typed terminal even when a fixture is malformed."""

        return ReviewVerdict(
            case_ref=case_ref,
            case_id=f"packet_{packet.name}",
            case_digest=case_digest,
            head_digest=head_digest,
            packet_digest=packet_digest if len(packet_digest) == 64 else digest_obj({}),
            verdict="human_decision",
            model=model,
            effort=effort,
            harness=HarnessId(self.lane),
            error=error,
            usage=UsageCost(
                source=DataSource.simulated,
                component="sol_review",
                model=model,
                usage_source="unavailable",
            ),
            fixture_provenance=(
                "simulated;author=synthetic;method=fixture;version=mock-v1;used_gold:false"
            ),
        )
