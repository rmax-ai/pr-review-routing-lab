"""Canonical SHA-256 digests used by the benchmark.

Digests are integrity and deduplication identifiers, not signatures.  The three
families are intentionally separate:

* invocation: inputs fixed before a provider or fixture is called;
* decision: semantic routing and finding outcomes;
* observation: timing and usage observations.

Volatile exclusions are registered by model class name.  No name-pattern
heuristics are used because silently excluding a new field would undermine the
determinism contract.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from hashlib import sha256
from pathlib import Path
from typing import Any

from .util import canonical_bytes


def digest_bytes(value: bytes) -> str:
    return sha256(value).hexdigest()


def digest_obj(value: Any) -> str:
    return digest_bytes(canonical_bytes(value))


def _json_value(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if isinstance(value, Mapping):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    return value


# These are explicit per-model registries, as opposed to broad "anything with
# time/path/usage in its name" filtering.
VOLATILE_FIELDS_BY_MODEL: dict[str, frozenset[str]] = {
    "StageRecord": frozenset({"started_at", "ended_at", "duration_ms"}),
    "ReviewVerdict": frozenset(
        {
            "usage",
            "latency_ms",
            "model",
            "effort",
            "harness",
            "fixture_provenance",
        }
    ),
    "RunRecord": frozenset(
        {
            "run_id",
            "usage",
            "invocations",
            "prompt_digests",
            "model_ids",
            "decision_digest",
            "observation_digest",
            "invocation_digest",
        }
    ),
    "Observation": frozenset({"timestamps", "durations", "usage"}),
    "Report": frozenset({"generated_at"}),
}

# Public registry: callers can inspect the exclusions for each serialized model.
VOLATILE_FIELDS = VOLATILE_FIELDS_BY_MODEL


def _without_registered_volatile(value: Any, model_name: str | None = None) -> Any:
    if hasattr(value, "model_dump"):
        current_name = value.__class__.__name__
        fields = getattr(type(value), "model_fields", {})
        return {
            str(key): _without_registered_volatile(getattr(value, key))
            for key in fields
            if key not in VOLATILE_FIELDS_BY_MODEL.get(current_name, frozenset())
        }
    if isinstance(value, Mapping):
        excluded = VOLATILE_FIELDS_BY_MODEL.get(model_name or "", frozenset())
        return {
            str(key): _without_registered_volatile(item)
            for key, item in value.items()
            if str(key) not in excluded
        }
    if isinstance(value, (list, tuple)):
        return [_without_registered_volatile(item) for item in value]
    return value


def digest_model(model: Any, *, exclude: Iterable[str] = ()) -> str:
    """Digest a model with only its registered volatile fields removed."""

    value = _without_registered_volatile(model)
    excluded = set(exclude)
    if isinstance(value, dict) and excluded:
        value = {key: item for key, item in value.items() if key not in excluded}
    return digest_obj(value)


def file_digest(path: str | Path) -> str:
    source = Path(path)
    if source.is_symlink():
        raise ValueError(f"symlink file is refused: {source}")
    return digest_bytes(source.read_bytes())


def file_set_digest(root: str | Path) -> str:
    """Digest a contained file set by relative path and byte digest."""

    base = Path(root)
    if not base.is_dir():
        raise ValueError(f"missing directory: {base}")
    if base.is_symlink():
        raise ValueError(f"symlink root is refused: {base}")
    paths = list(base.rglob("*"))
    if any(path.is_symlink() for path in paths):
        raise ValueError(f"symlink entry is refused: {base}")
    rows = [
        {"relative_path": str(path.relative_to(base)), "sha256": file_digest(path)}
        for path in sorted(path for path in paths if path.is_file() and ".git" not in path.parts)
    ]
    return digest_obj(rows)


def tree_digest(root: str | Path) -> str:
    """Compatibility alias for the applied-head file-set digest."""

    return file_set_digest(root)


def manifest_digest(entries: Iterable[Any]) -> str:
    rows = [
        {
            "relative_path": str(_json_value(entry)["relative_path"]),
            "sha256": str(_json_value(entry)["sha256"]),
            "role": str(_json_value(entry)["role"]),
        }
        for entry in entries
    ]
    return digest_obj(sorted(rows, key=lambda row: (row["relative_path"], row["role"])))


def case_digest(case: Any) -> str:
    """Digest canonical case metadata plus its canonical file manifest."""

    if hasattr(case, "model_dump"):
        value = case.model_dump(mode="json")
    else:
        value = dict(case)
    # These fields are derived from the input location and must not change the
    # identity of the same case when it is copied to another checkout.
    for key in ("case_ref", "case_dir", "head_digest", "case_digest", "gold"):
        value.pop(key, None)
    manifest = value.pop("case_manifest", [])
    if hasattr(manifest, "model_dump"):
        manifest = manifest.model_dump(mode="json")
    manifest_values = []
    for item in manifest:
        serialized = _json_value(item)
        if str(serialized.get("relative_path", "")) != "case.yaml":
            manifest_values.append(serialized)
    value["manifest"] = sorted(
        manifest_values,
        key=lambda item: (str(item.get("relative_path", "")), str(item.get("role", ""))),
    )
    return digest_obj(value)


def head_digest(head: str | Path) -> str:
    return file_set_digest(head)


def packet_digest(files: Mapping[str, str], template_digest: str = "") -> str:
    rows = [{"relative_path": key, "sha256": value} for key, value in sorted(files.items())]
    return digest_obj({"files": rows, "prompt_template_digest": template_digest})


def invocation_digest(
    *,
    case_digest_value: str,
    head_digest_value: str,
    packet_digest_value: str,
    prompt_digest: str,
    config_digest: str,
    backend: str,
    model: str,
    fixture_version: str,
) -> str:
    return digest_obj(
        {
            "case_digest": case_digest_value,
            "head_digest": head_digest_value,
            "packet_digest": packet_digest_value,
            "prompt_digest": prompt_digest,
            "config_digest": config_digest,
            "backend": backend,
            "model": model,
            "fixture_version": fixture_version,
        }
    )


def decision_digest(record: Any) -> str:
    """Digest semantic routing fields, excluding registered observations."""

    if record.__class__.__name__ == "RunRecord":
        value = _json_value(record)
        value["stages"] = [
            {
                "name": stage.get("name"),
                "data": {
                    key: item
                    for key, item in stage.get("data", {}).items()
                    if key not in {"invocation_digest", "prompt_digest", "packet", "harness"}
                },
            }
            for stage in value.get("stages", [])
        ]
        for key in (
            "run_id",
            "usage",
            "invocations",
            "prompt_digests",
            "model_ids",
            "backend",
            "artifacts",
            "decision_digest",
            "observation_digest",
            "invocation_digest",
        ):
            value.pop(key, None)
        return digest_obj(value)
    return digest_model(record)


def observation_digest(record: Any) -> str:
    """Digest timing/usage observations separately from routing semantics."""

    value = _json_value(record)
    if record.__class__.__name__ == "RunRecord" and isinstance(value, dict):
        value = {
            "usage": value.get("usage", []),
            "stages": [
                {key: stage.get(key) for key in ("name", "started_at", "ended_at", "duration_ms")}
                for stage in value.get("stages", [])
            ],
        }
    if isinstance(value, dict):
        keep = {
            "usage",
            "stages",
            "latency_ms",
            "duration_ms",
            "timestamps",
            "started_at",
            "ended_at",
        }
        value = {key: item for key, item in value.items() if key in keep}
    return digest_obj(value)


def verdict_digest(verdict: Any) -> str:
    return digest_model(verdict)


def canonical_json(value: Any) -> str:
    """Return canonical JSON text for sidecar and prompt hashing tests."""

    return canonical_bytes(_json_value(value)).decode("utf-8")


def canonical_json_bytes(value: Any) -> bytes:
    return canonical_bytes(_json_value(value))
