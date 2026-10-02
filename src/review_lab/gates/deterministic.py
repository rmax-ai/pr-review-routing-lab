"""Deterministic, fail-closed toy-contract analyzers.

These checks are intentionally small.  They demonstrate evidence binding and
policy floors on reconstructed repositories; they are not production static
analysis.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import yaml

from ..digests import digest_bytes, digest_obj, file_digest, file_set_digest
from ..models import DeterministicEvidence, ReviewCase

ANALYZER_VERSION = "deterministic-v2"
MAX_INSPECTED_FILE_BYTES = 10_000_000
DOC_SUFFIXES = {".md", ".rst", ".txt", ".adoc"}
MECHANICAL_SUFFIXES = {".lock", ".json", ".yaml", ".yml", ".toml"}
BOUNDARY_WORDS = (
    "permission",
    "permissions",
    "secret",
    "credential",
    "allowlist",
    "auth",
    "security",
    "policy",
    "acl",
    "access",
)
COMMENT_PREFIXES = ("#", "//", "/*", "*", "--")


def _files(root: Path) -> list[Path]:
    if not root.exists():
        raise ValueError("repository snapshot is missing")
    if root.is_symlink() or not root.is_dir():
        raise ValueError("repository snapshot is not a directory")
    paths = list(root.rglob("*"))
    if any(path.is_symlink() for path in paths):
        raise ValueError("symlink repository entry is refused")
    return sorted(path for path in paths if path.is_file() and ".git" not in path.parts)


def _patch_text(patch: str | Path) -> str:
    if isinstance(patch, Path):
        if patch.is_symlink():
            raise ValueError("patch symlink is refused")
        if not patch.exists():
            return ""
        return patch.read_text(encoding="utf-8", errors="strict")
    return str(patch)


def _changed_paths(patch: str) -> list[str]:
    values = re.findall(r"^\+\+\+ b/(.+?)\s*$", patch, flags=re.MULTILINE)
    if not values:
        values = re.findall(r"^\-\-\- a/(.+?)\s*$", patch, flags=re.MULTILINE)
    return sorted({path for path in values if path != "/dev/null"})


def _case_value(case: ReviewCase | dict[str, Any] | None, key: str, default: Any = None) -> Any:
    if case is None:
        return default
    if isinstance(case, ReviewCase):
        return getattr(case, key, default)
    return case.get(key, default)


def _safe_tree_digest(root: Path) -> str:
    try:
        return file_set_digest(root)
    except (OSError, ValueError):
        return digest_obj([])


def _input_hashes(
    root: Path,
    patch: str,
    files: list[Path],
    head_digest: str | None = None,
) -> dict[str, str]:
    hashes = {
        "repo": head_digest or _safe_tree_digest(root),
        "patch": digest_bytes(patch.encode("utf-8")),
    }
    for path in files:
        try:
            hashes[str(path.relative_to(root))] = file_digest(path)
        except OSError:
            continue
    return dict(sorted(hashes.items()))


def _evidence(
    gate: str,
    status: str,
    detail: str,
    root: Path,
    patch: str,
    files: list[Path],
    *,
    head_digest: str | None = None,
    input_hashes: dict[str, str] | None = None,
) -> DeterministicEvidence:
    head = head_digest or _safe_tree_digest(root)
    inputs = input_hashes or _input_hashes(root, patch, files)
    payload = {
        "gate": gate,
        "status": status,
        "detail": detail,
        "input_hashes": inputs,
        "head_digest": head,
        "analyzer_version": ANALYZER_VERSION,
        "duration_ms": 0,
    }
    return DeterministicEvidence(
        **payload,
        evidence_digest=digest_obj(payload),
    )


def _structured_files(
    files: list[Path],
    contents: dict[Path, str] | None = None,
) -> list[tuple[Path, Any]]:
    values: list[tuple[Path, Any]] = []
    for path in files:
        if path.suffix.lower() not in {".yaml", ".yml", ".json"}:
            continue
        try:
            if contents is not None and path not in contents:
                continue
            text = contents[path] if contents is not None else None
            if text is None:
                text = path.read_text(encoding="utf-8")
            value = (
                yaml.safe_load(text) or {}
                if path.suffix.lower() in {".yaml", ".yml"}
                else json.loads(text)
            )
        except (OSError, UnicodeError, TypeError, ValueError, yaml.YAMLError):
            continue
        values.append((path, value))
    return values


def _boundary_in_path(path: str, terms: list[str]) -> bool:
    segments = [segment.casefold() for segment in re.split(r"[/\\]", path) if segment]
    for term in terms:
        normalized = term.casefold().strip("/\\")
        if any(
            segment == normalized or segment.rsplit(".", 1)[0] == normalized
            for segment in segments
        ):
            return True
    return False


def _boundary_in_added_lines(patch: str, terms: list[str]) -> bool:
    for line in patch.splitlines():
        if not line.startswith("+") or line.startswith("+++"):
            continue
        content = line[1:].lstrip()
        if content.startswith(COMMENT_PREFIXES):
            continue
        if any(
            re.search(
                rf"(?<![A-Za-z0-9]){re.escape(term.rstrip('s'))}s?(?![A-Za-z0-9])",
                content,
                re.IGNORECASE,
            )
            for term in terms
        ):
            return True
    return False


def _walk_values(value: Any, key: str) -> list[Any]:
    found: list[Any] = []
    if isinstance(value, dict):
        for name, item in value.items():
            if str(name).lower() == key.lower():
                found.append(item)
            found.extend(_walk_values(item, key))
    elif isinstance(value, list):
        for item in value:
            found.extend(_walk_values(item, key))
    return found


def _case_requirements(case: ReviewCase | dict[str, Any] | None) -> list[Any]:
    if case is None:
        return []
    return case.requirements if isinstance(case, ReviewCase) else case.get("requirements", [])


def run_deterministic_gates(
    repo: str | Path,
    patch: str | Path = "",
    case: ReviewCase | dict[str, Any] | None = None,
) -> list[DeterministicEvidence]:
    """Run all eight gate families over the supplied applied snapshot."""

    root = Path(repo)
    try:
        text = _patch_text(patch)
    except (OSError, UnicodeError, TypeError, ValueError) as exc:
        empty = []
        return [
            _evidence(gate, "inconclusive", f"unable to inspect patch: {exc}", root, "", empty)
            for gate in (
                "evidence_binding",
                "completion_state",
                "calibration_reset",
                "retention_bound",
                "requirement_markers",
                "exact_head_revision",
                "docs_only",
                "security_boundary",
            )
        ]
    try:
        files = _files(root)
    except (OSError, ValueError) as exc:
        empty = []
        return [
            _evidence(gate, "inconclusive", f"unable to inspect input: {exc}", root, text, empty)
            for gate in (
                "evidence_binding",
                "completion_state",
                "calibration_reset",
                "retention_bound",
                "requirement_markers",
                "exact_head_revision",
                "docs_only",
                "security_boundary",
            )
        ]
    names = {str(path.relative_to(root)) for path in files}
    contents: dict[Path, str] = {}
    unreadable: dict[Path, str] = {}
    for path in files:
        try:
            if path.stat().st_size > MAX_INSPECTED_FILE_BYTES:
                unreadable[path] = "file exceeds inspection limit"
                continue
            contents[path] = path.read_text(encoding="utf-8", errors="strict")
        except (OSError, UnicodeError, ValueError) as exc:
            unreadable[path] = str(exc)
    lower = (text + "\n" + "\n".join(contents.values())).lower()
    structured = _structured_files(files, contents)
    head_digest = _safe_tree_digest(root)
    input_hashes = _input_hashes(root, text, files, head_digest)

    def emit(gate: str, status: str, detail: str) -> DeterministicEvidence:
        if unreadable:
            detail += "; unreadable files tolerated: " + ", ".join(
                sorted(str(path.relative_to(root)) for path in unreadable)
            )
        return _evidence(
            gate,
            status,
            detail,
            root,
            text,
            files,
            head_digest=head_digest,
            input_hashes=input_hashes,
        )

    # An empty patch means no changed paths.  The snapshot is still inspected
    # for structured invariants, but untouched security/config files must not
    # create a boundary floor.
    changed = _changed_paths(text)
    added_text = "\n".join(
        line[1:]
        for line in text.splitlines()
        if line.startswith("+") and not line.startswith("+++")
    )

    result: list[DeterministicEvidence] = []

    # 1. Evidence binding compares the subject to the independent invocation
    # value, never to a subject echoed by the evidence file.
    expected_subject = _case_value(case, "workstream_subject")
    subjects: list[str] = []
    for _, value in structured:
        for key in ("workstream_subject", "subject", "workstream"):
            subjects.extend(
                str(item)
                for item in _walk_values(value, key)
                if isinstance(item, (str, int, float, bool))
            )
    if expected_subject and subjects and any(item != str(expected_subject) for item in subjects):
        status, detail = "fail", "evidence subject does not match independent workstream subject"
    elif expected_subject and not subjects and (
        bool(_case_value(case, "evidence_refs", []))
        or any("evidence" in name.casefold() for name in names)
    ):
        status, detail = "inconclusive", "expected evidence subject is absent"
    else:
        status, detail = "pass", "evidence subject is bound"
    result.append(emit("evidence_binding", status, detail))

    # 2. A verified/complete structured evidence record may not contain open items.
    bad_completion = False
    saw_completion_contract = False
    for _, value in structured:
        verified = any(
            item is True
            for key in ("verified", "complete", "completed")
            for item in _walk_values(value, key)
        )
        statuses = [str(item).lower() for item in _walk_values(value, "status")]
        items = _walk_values(value, "items") + _walk_values(value, "entries")
        saw_completion_contract |= verified or bool(statuses) or bool(items)
        if verified and (
            any(item in {"open", "todo", "pending"} for item in statuses)
            or any(
                isinstance(item, dict)
                and str(item.get("status", "")).lower() not in {"closed", "complete", "completed"}
                for item in items
            )
        ):
            bad_completion = True
    if not saw_completion_contract:
        bad_completion = bool(
            re.search(r"\bverified\s*:\s*true\b", lower)
            and re.search(r"\b(?:todo|open)\b|-\s*\[\s*\]", lower)
        )
        completion_status = "fail" if bad_completion else "pass"
    else:
        completion_status = "fail" if bad_completion else "pass"
    result.append(
        emit(
            "completion_state",
            completion_status,
            "verified evidence contains open items"
            if bad_completion
            else "completion invariant holds",
        )
    )

    # 3. Mode changes require an explicit reset marker update.
    mode_change = bool(re.search(r"(?im)^[+].*mode\s*[:=]", text))
    reset_change = bool(re.search(r"(?im)^[+].*reset[_ -]?marker", text))
    if mode_change and not reset_change:
        calibration_status, calibration_detail = (
            "mandatory_review",
            "calibration mode changed without reset marker update",
        )
    else:
        calibration_status, calibration_detail = "pass", "calibration reset marker is consistent"
    result.append(emit("calibration_reset", calibration_status, calibration_detail))

    # 4. Retention is a review floor because a marker cannot prove pruning safety.
    max_entries = None
    declared_entries: list[Any] = []
    for _, value in structured:
        values = _walk_values(value, "max_entries")
        if values:
            try:
                max_entries = int(values[-1])
            except (TypeError, ValueError):
                max_entries = None
        declared_entries.extend(_walk_values(value, "entries"))
    entry_count = sum(
        len(item) if isinstance(item, (list, dict)) else 1 for item in declared_entries
    )
    pruning_changed = bool(re.search(r"(?im)^[+].*\bprun(?:e|ing)\b", text))
    if (
        max_entries is not None
        and declared_entries
        and entry_count > max_entries
        and not pruning_changed
    ):
        retention_status, retention_detail = (
            "mandatory_review",
            "retention bound exceeded without a pruning change",
        )
    elif re.search(r"(?i)max_entries\s*[:=]\s*(\d+)", lower) and re.search(
        r"(?i)entries\s*[:=]\s*\[", lower
    ):
        match = re.search(r"(?i)max_entries\s*[:=]\s*(\d+)", lower)
        entries_match = re.search(r"(?i)entries\s*[:=]\s*\[(.*?)\]", lower, re.DOTALL)
        count = (
            entries_match.group(1).count(",") + 1
            if entries_match and entries_match.group(1).strip()
            else 0
        )
        exceeds = match and count > int(match.group(1))
        retention_status = "mandatory_review" if exceeds and not pruning_changed else "pass"
        retention_detail = "retention bound checked"
    else:
        retention_status, retention_detail = "pass", "retention bound is within declared limit"
    result.append(emit("retention_bound", retention_status, retention_detail))

    # 5. Marker presence is a review trigger, not proof that the requirement is met.
    missing_markers = []
    for requirement in _case_requirements(case):
        expects = getattr(requirement, "expects_marker", None)
        req_id = getattr(requirement, "id", None)
        surface = getattr(requirement, "surface", None)
        marker = getattr(requirement, "marker", None)
        if isinstance(requirement, dict):
            expects = requirement.get("expects_marker", False)
            req_id = requirement.get("id", "")
            surface = requirement.get("surface")
            marker = requirement.get("marker")
        if expects:
            target = str(surface or marker or req_id or "")
            if (
                target
                and not any(target in path for path in changed)
                and target.lower() not in added_text.lower()
            ):
                missing_markers.append(target)
    marker_status = "mandatory_review" if missing_markers else "pass"
    result.append(
        emit(
            "requirement_markers",
            marker_status,
            "missing expected requirement surface: " + ", ".join(sorted(missing_markers))
            if missing_markers
            else "expected requirement markers are present",
        )
    )

    # 6. Exact head revision is independent of quoted patch prose.
    expected_head = _case_value(case, "expected_head_digest")
    actual_head = head_digest
    if expected_head is None:
        head_status, head_detail = "pass", "no independent expected head was supplied"
    elif expected_head == actual_head:
        head_status, head_detail = "pass", "applied head matches expected digest"
    else:
        head_status, head_detail = "fail", "applied head does not match expected digest"
    result.append(emit("exact_head_revision", head_status, head_detail))

    # 7. Documentation-only is informational and never itself a rejection.
    docs_only = not changed or all(
        Path(path).suffix.lower() in DOC_SUFFIXES | MECHANICAL_SUFFIXES for path in changed
    )
    result.append(
        emit(
            "docs_only",
            "informational",
            "empty patch has no changed paths"
            if not changed
            else "documentation-only negative control"
            if docs_only
            else "semantic or mechanical files changed",
        )
    )

    # 8. Security boundary paths are a mandatory-review floor, not auto-human.
    declared = [
        str(item).lower() for item in _case_value(case, "security_boundary_patterns", []) or []
    ]
    boundary = declared or list(BOUNDARY_WORDS)
    touched = any(_boundary_in_path(path, boundary) for path in changed) or _boundary_in_added_lines(
        text, boundary
    )
    result.append(
        emit(
            "security_boundary",
            "mandatory_review" if touched else "pass",
            "security/config boundary touched" if touched else "no security boundary touched",
        )
    )
    return result


def analyze(*args: Any, **kwargs: Any) -> list[DeterministicEvidence]:
    return run_deterministic_gates(*args, **kwargs)
