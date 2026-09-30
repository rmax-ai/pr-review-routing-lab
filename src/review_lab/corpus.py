"""Case loading, manifest verification, private overlays, and packet inputs."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from .digests import case_digest, file_digest, file_set_digest
from .models import CaseManifestEntry, GoldCase, ReviewCase
from .util import read_yaml


class CaseLoadError(ValueError):
    """A case is rejected before any routing decision is made."""

    code = "input_invalid"


class PrivateOverlayError(ValueError):
    code = "policy_refused"


ROLE_BY_TOP_FILE = {
    "case.yaml": "case_meta",
    "change.patch": "patch",
    "requirements.yaml": "requirement",
    "contracts.md": "contract",
    "prior_review.yaml": "prior_review",
}
GOLD_SEGMENTS = {"gold"}
GOLD_FIXTURE_KEYS = {
    "gold",
    "human_required",
    "verdict_expectation",
    "expected_findings",
    "question_labels",
}


def _contains_symlink(root: Path) -> bool:
    if root.is_symlink():
        return True
    try:
        return any(path.is_symlink() for path in root.rglob("*"))
    except OSError as exc:
        raise CaseLoadError(f"cannot scan case root: {exc}") from exc


def _ensure_relative(path: str, root: Path) -> Path:
    candidate = Path(path)
    if "\\" in path or candidate.is_absolute() or ".." in candidate.parts:
        raise CaseLoadError(f"referenced path escapes case root: {path}")
    resolved = (root / candidate).resolve()
    if root.resolve() not in resolved.parents and resolved != root.resolve():
        raise CaseLoadError(f"referenced path escapes case root: {path}")
    return resolved


def _reject_gold_path(path: Path) -> None:
    parts = {part.lower() for part in path.parts}
    if "gold" in parts or any(part.lower().startswith("expected") for part in path.parts):
        raise CaseLoadError("gold and expected inputs are not reviewer-visible")


def _reject_gold_tree(root: Path) -> None:
    for path in root.rglob("*"):
        relative_parts = path.relative_to(root).parts
        if "gold" in {part.lower() for part in relative_parts} or any(
            part.lower().startswith("expected") for part in relative_parts
        ):
            raise CaseLoadError("gold and expected inputs are not reviewer-visible")


def _find_key_values(value: Any, key: str) -> list[Any]:
    found: list[Any] = []
    if isinstance(value, dict):
        for name, item in value.items():
            if str(name) == key:
                found.append(item)
            found.extend(_find_key_values(item, key))
    elif isinstance(value, list):
        for item in value:
            found.extend(_find_key_values(item, key))
    return found


def _contains_key(value: Any, key: str) -> bool:
    return bool(_find_key_values(value, key))


def _reject_fixture_gold_fields(root: Path) -> None:
    """Reject adjudication data even when it is hidden inside a fixture."""

    fixtures = root / "fixtures"
    if not fixtures.is_dir():
        return
    for path in sorted(
        item
        for item in fixtures.rglob("*")
        if item.is_file() and item.suffix.lower() in {".json", ".yaml", ".yml"}
    ):
        try:
            value = read_yaml(path)
        except (OSError, UnicodeError, TypeError, ValueError, yaml.YAMLError) as exc:
            raise CaseLoadError("fixture schema is invalid") from exc
        if any(_contains_key(value, key) for key in GOLD_FIXTURE_KEYS):
            raise CaseLoadError("gold schema fields are not allowed in fixtures")
        used_gold = _find_key_values(value, "used_gold")
        if any(item is not False for item in used_gold):
            raise CaseLoadError("fixtures must attest used_gold: false")


def _verify_patch(case_dir: Path, patch_path: Path, repo_path: Path) -> None:
    """Verify a patch without applying it.

    Git is used only for its read-only ``--check`` operation.  Empty patches
    are valid for synthetic unit cases and need no subprocess.
    """

    if not patch_path.exists() or not repo_path.exists():
        return
    if not patch_path.read_bytes().strip():
        return
    try:
        completed = subprocess.run(
            ["git", "apply", "--check", str(patch_path)],
            cwd=repo_path,
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError as exc:
        raise CaseLoadError(f"patch verifier unavailable: {exc}") from exc
    if completed.returncode:
        raise CaseLoadError("change.patch does not apply to repo")


def _verify_applied_head(
    patch_path: Path,
    repo_path: Path,
    head_path: Path,
) -> None:
    """Apply the patch to an isolated copy and compare the declared head."""

    if not head_path.is_dir():
        raise CaseLoadError("case head directory is required")
    with tempfile.TemporaryDirectory(prefix="review-lab-head-") as temporary:
        applied = Path(temporary) / "repo"
        shutil.copytree(repo_path, applied, symlinks=False)
        if patch_path.read_bytes().strip():
            completed = subprocess.run(
                ["git", "apply", str(patch_path)],
                cwd=applied,
                capture_output=True,
                text=True,
                check=False,
            )
            if completed.returncode:
                raise CaseLoadError("change.patch cannot produce applied head")
        if file_set_digest(applied) != file_set_digest(head_path):
            raise CaseLoadError("head does not match the applied patch")


def build_manifest(case_dir: str | Path) -> list[CaseManifestEntry]:
    """Build the canonical manifest for a case directory."""

    raw_root = Path(case_dir)
    if raw_root.is_symlink():
        raise CaseLoadError("symlink traversal is refused")
    root = raw_root.resolve()
    if not root.is_dir():
        raise CaseLoadError(f"case directory missing: {root}")
    _reject_gold_path(root)
    if _contains_symlink(root):
        raise CaseLoadError("symlink traversal is refused")
    _reject_gold_tree(root)
    _reject_fixture_gold_fields(root)
    case_yaml = root / "case.yaml"
    try:
        raw = read_yaml(case_yaml) if case_yaml.is_file() else {}
    except ValueError as exc:
        raise CaseLoadError("case.yaml is invalid") from exc
    if isinstance(raw, dict) and ("gold" in raw or "expected_findings" in raw):
        raise CaseLoadError("gold/expected fields are not reviewer-visible")
    rows: list[CaseManifestEntry] = []
    base_ref = str(raw.get("base_ref", "repo")) if isinstance(raw, dict) else "repo"
    base_source = _ensure_relative(base_ref, root)
    for source, role in ((base_source, "base"), (root / "head", "target")):
        if source.exists():
            if not source.is_dir():
                raise CaseLoadError(f"{source.name} is not a directory")
            for path in sorted(
                path for path in source.rglob("*") if path.is_file() and ".git" not in path.parts
            ):
                rows.append(
                    CaseManifestEntry(
                        relative_path=str(path.relative_to(root)),
                        sha256=file_digest(path),
                        role=role,
                    )
                )
    for name, role in ROLE_BY_TOP_FILE.items():
        path = root / name
        if path.exists():
            rows.append(
                CaseManifestEntry(
                    relative_path=name,
                    sha256=file_digest(path),
                    role=role,
                )
            )
    if case_yaml.is_file():
        for key, role in (
            ("requirements_ref", "requirement"),
            ("contracts_ref", "contract"),
            ("prior_review_ref", "prior_review"),
        ):
            reference = raw.get(key) if isinstance(raw, dict) else None
            if not reference:
                continue
            path = _ensure_relative(str(reference), root)
            if path.is_file() and str(path.relative_to(root)) not in {
                row.relative_path for row in rows
            }:
                rows.append(
                    CaseManifestEntry(
                        relative_path=str(path.relative_to(root)),
                        sha256=file_digest(path),
                        role=role,
                    )
                )
        for reference in raw.get("evidence_refs", []) if isinstance(raw, dict) else []:
            path = _ensure_relative(str(reference), root)
            if path.is_file() and str(path.relative_to(root)) not in {
                row.relative_path for row in rows
            }:
                rows.append(
                    CaseManifestEntry(
                        relative_path=str(path.relative_to(root)),
                        sha256=file_digest(path),
                        role="evidence",
                    )
                )
    return sorted(rows, key=lambda item: (item.relative_path, item.role))


def _manifest_head_digest(root: Path) -> str:
    head = root / "head"
    if not head.is_dir():
        raise CaseLoadError("case head directory is required")
    return file_set_digest(head)


def _validate_references(root: Path, raw: dict[str, Any]) -> None:
    refs = [
        raw.get("base_ref"),
        raw.get("patch_ref"),
        raw.get("requirements_ref"),
        raw.get("contracts_ref"),
    ]
    refs.extend(raw.get("evidence_refs") or [])
    if raw.get("prior_review_ref"):
        refs.append(raw["prior_review_ref"])
    for ref in refs:
        if not ref:
            continue
        path = _ensure_relative(str(ref), root)
        if not path.exists():
            raise CaseLoadError(f"referenced file does not exist: {ref}")
        if ref == raw.get("base_ref") and not path.is_dir():
            raise CaseLoadError(f"base_ref must name a directory: {ref}")
        if ref != raw.get("base_ref") and not path.is_file():
            raise CaseLoadError(f"referenced input must name a file: {ref}")
        _reject_gold_path(path)


def load_case(path: str | Path) -> ReviewCase:
    raw_directory = Path(path)
    if raw_directory.is_symlink():
        raise CaseLoadError("symlink traversal is refused")
    directory = raw_directory.resolve()
    _reject_gold_path(directory)
    if not directory.is_dir():
        raise CaseLoadError(f"case directory missing: {directory}")
    if _contains_symlink(directory):
        raise CaseLoadError("symlink traversal is refused")
    _reject_gold_tree(directory)
    _reject_fixture_gold_fields(directory)
    source = directory / "case.yaml"
    if not source.exists():
        raise CaseLoadError("case.yaml is required")
    try:
        raw = read_yaml(source)
    except ValueError as exc:
        raise CaseLoadError("case.yaml is invalid") from exc
    if not isinstance(raw, dict):
        raise CaseLoadError("case.yaml must contain an object")
    if "gold" in raw or "expected_findings" in raw:
        raise CaseLoadError("gold/expected fields are not reviewer-visible")
    _validate_references(directory, raw)
    repo = _ensure_relative(str(raw.get("base_ref", "repo")), directory)
    patch = _ensure_relative(str(raw.get("patch_ref", "change.patch")), directory)
    if not repo.is_dir():
        raise CaseLoadError("repo directory is required")
    if not patch.is_file():
        raise CaseLoadError("change.patch is required")
    _verify_patch(directory, patch, repo)
    _verify_applied_head(patch, repo, directory / "head")
    requirements_ref = raw.get("requirements_ref")
    if requirements_ref:
        requirements_path = _ensure_relative(str(requirements_ref), directory)
    else:
        requirements_path = directory / "requirements.yaml"
    if requirements_path.is_file() and "requirements" not in raw:
        try:
            requirements_raw = read_yaml(requirements_path)
        except ValueError as exc:
            raise CaseLoadError("requirements.yaml is invalid") from exc
        if isinstance(requirements_raw, dict):
            requirements_raw = requirements_raw.get("requirements", requirements_raw)
        if not isinstance(requirements_raw, list):
            raise CaseLoadError("requirements.yaml must contain a requirements list")
        raw = dict(raw)
        raw["requirements"] = requirements_raw
    expected_head = raw.get("expected_head_digest")
    actual_head = _manifest_head_digest(directory)
    if expected_head != actual_head:
        raise CaseLoadError("expected_head_digest does not match head")
    manifest = build_manifest(directory)
    raw = dict(raw)
    raw.pop("case_digest", None)
    supplied = raw.pop("expected_case_digest", None)
    supplied_manifest = raw.pop("manifest", None)
    supplied_case_manifest = raw.pop("case_manifest", None)
    if supplied_manifest is not None and supplied_case_manifest is not None:
        raise CaseLoadError("manifest may be supplied only once")
    if supplied_manifest is None:
        supplied_manifest = supplied_case_manifest
    manifest_rows = [item.model_dump(mode="json") for item in manifest]
    if supplied_manifest is not None:
        if not isinstance(supplied_manifest, list):
            raise CaseLoadError("manifest must contain a list")
        try:
            supplied_rows = [
                CaseManifestEntry.model_validate(item).model_dump(mode="json")
                for item in supplied_manifest
            ]
        except (TypeError, ValueError, ValidationError) as exc:
            raise CaseLoadError("manifest schema is invalid") from exc
        compare_supplied = [row for row in supplied_rows if row["relative_path"] != "case.yaml"]
        compare_actual = [row for row in manifest_rows if row["relative_path"] != "case.yaml"]
        if sorted(
            compare_supplied, key=lambda item: (item["relative_path"], item["role"])
        ) != sorted(
            compare_actual,
            key=lambda item: (item["relative_path"], item["role"]),
        ):
            raise CaseLoadError("manifest does not match case files")
    raw["case_manifest"] = manifest_rows
    raw["head_digest"] = actual_head
    raw["case_dir"] = str(directory)
    try:
        case = ReviewCase.model_validate_json(json.dumps(raw))
    except (TypeError, ValueError, ValidationError) as exc:
        raise CaseLoadError("case.yaml schema is invalid") from exc
    # `case_digest` is recomputed from exactly the loaded metadata and manifest.
    if supplied is not None and supplied != case_digest(case):
        raise CaseLoadError("expected_case_digest does not match case")
    if case.case_ref and case.case_ref != case_digest(case)[:12]:
        raise CaseLoadError("case_ref must be derived from case_digest")
    return case


def load_gold(path: str | Path) -> GoldCase:
    source = Path(path)
    if source.is_dir():
        source = source / "expected.yaml"
    if any(parent.is_symlink() for parent in (source, *source.parents)):
        raise CaseLoadError("gold path contains a symlink")
    if not source.exists() or source.is_symlink():
        raise CaseLoadError("gold file is missing or symlinked")
    try:
        return GoldCase.model_validate_json(json.dumps(read_yaml(source)))
    except (OSError, TypeError, ValueError, ValidationError, yaml.YAMLError) as exc:
        raise CaseLoadError("gold schema is invalid") from exc


def gold_warnings(gold: GoldCase) -> list[str]:
    """Return authoring warnings without weakening gold validation."""

    generic = {"bug", "change", "code", "error", "fix", "issue", "problem", "thing"}
    warnings: list[str] = []
    for index, finding in enumerate(gold.expected_findings):
        keywords = finding.match.keywords_any or []
        if len(keywords) > 5:
            warnings.append(f"{gold.case_id}[{index}] has more than five keywords")
        if len(keywords) == 1 and keywords[0].casefold() in generic:
            warnings.append(f"{gold.case_id}[{index}] uses a generic single-word keyword")
    return warnings


def _iter_directories(root: Path) -> Iterator[Path]:
    if not root.exists():
        return
    if not root.is_dir():
        raise CaseLoadError("case root must be a directory")
    if _contains_symlink(root):
        raise CaseLoadError("symlink traversal is refused")
    for path in sorted(root.iterdir()):
        if path.is_dir() and (path / "case.yaml").is_file():
            yield path


def _overlay_path(value: str) -> Path:
    raw_overlay = Path(value).expanduser()
    if not raw_overlay.is_absolute():
        raise PrivateOverlayError("private overlay must be an absolute path")
    if raw_overlay.is_symlink() or _contains_symlink(raw_overlay):
        raise PrivateOverlayError("symlink traversal is refused")
    overlay = raw_overlay.resolve()
    if not overlay.is_dir():
        raise PrivateOverlayError("private overlay directory is missing")
    if _contains_symlink(overlay):
        raise PrivateOverlayError("symlink traversal is refused")
    checkout = Path.cwd().resolve()
    if checkout == overlay or checkout in overlay.parents:
        allowed = checkout / "cases" / "private"
        if allowed != overlay and allowed not in overlay.parents:
            raise PrivateOverlayError("private overlay must not be inside checkout")
    return overlay


def load_cases(
    root: str | Path,
    *,
    public_only: bool = False,
    allow_private: bool = True,
) -> list[ReviewCase]:
    raw_root = Path(root)
    if raw_root.is_symlink():
        raise CaseLoadError("symlink traversal is refused")
    root_path = raw_root.resolve()
    if not root_path.exists():
        raise FileNotFoundError(root_path)
    if not root_path.is_dir():
        raise CaseLoadError("case root must be a directory")
    if _contains_symlink(root_path):
        raise CaseLoadError("symlink traversal is refused")
    cases = [load_case(path) for path in _iter_directories(root_path)]
    overlay_name = os.environ.get("REVIEW_LAB_PRIVATE_CASES")
    if overlay_name:
        if public_only or not allow_private:
            raise PrivateOverlayError("public-only runs refuse a configured private overlay")
        overlay = _overlay_path(overlay_name)
        cases.extend(
            case.model_copy(update={"provenance": "private_replay"})
            for path in _iter_directories(overlay)
            for case in [load_case(path)]
        )
    cases = sorted(cases, key=lambda item: item.id)
    ids = [case.id for case in cases]
    if len(ids) != len(set(ids)):
        raise CaseLoadError("case ids must be unique across public and private inputs")
    return cases


def scan_paths(root: str | Path) -> list[str]:
    """Return stable privacy-scan findings without inspecting external systems."""

    base = Path(root)
    if not base.is_dir() or base.is_symlink():
        raise CaseLoadError("privacy-scan root is missing or symlinked")
    if _contains_symlink(base):
        raise CaseLoadError("symlink traversal is refused")
    patterns = [
        re.compile(r"/(?:home|Users)/"),
        re.compile(r"(?i)(?:api[_-]?key|token|password|secret)\s*[:=]"),
        re.compile(r"https?://"),
    ]
    findings: list[str] = []
    for path in sorted(path for path in base.rglob("*") if path.is_file()):
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for pattern in patterns:
            if pattern.search(text):
                findings.append(str(path.relative_to(base)))
                break
    return findings


def case_digest_for(case: ReviewCase) -> str:
    return case_digest(case)
