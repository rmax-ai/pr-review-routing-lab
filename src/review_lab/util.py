"""Small deterministic utilities."""

import json
import os
import re
import selectors
import shutil
import subprocess
import tempfile
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, NamedTuple


def now() -> datetime:
    value = os.environ.get("REVIEW_LAB_NOW")
    if value:
        return datetime.fromisoformat(value)
    return datetime.now(UTC)


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode()


def read_yaml(path: str | Path) -> Any:
    import yaml

    try:
        with Path(path).open(encoding="utf-8") as handle:
            return yaml.safe_load(handle) or {}
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        raise ValueError(f"invalid YAML input: {path}") from exc


def write_json(path: str | Path, value: Any) -> None:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    payload = canonical_bytes(value) + b"\n"
    temporary: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=destination.parent,
            prefix=f".{destination.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary = handle.name
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, destination)
        directory_fd = os.open(destination.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    except OSError:
        if temporary is not None:
            try:
                os.unlink(temporary)
            except FileNotFoundError:
                pass
        raise


def scrub_text(value: str, limit: int = 2000) -> str:
    value = re.sub(
        r"(?i)\b(token|password|secret|api[_-]?key|authorization|bearer)"
        r"\s*[:=]\s*(?:bearer\s+)?\S+",
        r"\1=[scrubbed]",
        value,
    )
    value = re.sub(r"(?i)\b[A-Z]:\\(?:[^\s\"'`;,)]*\\)*[^\s\"'`;,)]*", r"[path]", value)
    value = re.sub(r"(?<![:\w])/(?!/)[^\s\"'`;,)]*", "/[path]", value)
    value = re.sub(r"(?i)\b[\w.+-]+@[\w.-]+\.[a-z]{2,}\b", "[email]", value)
    return value[:limit]


def copy_tree_readonly(source: Path, destination: Path) -> None:
    if destination.exists():
        raise FileExistsError(destination)
    shutil.copytree(source, destination)
    for path in destination.rglob("*"):
        if path.is_file():
            path.chmod(0o444)


def is_path_under(path: str | Path, root: str | Path) -> bool:
    """Return whether a path resolves inside or equal to a root."""

    try:
        Path(path).resolve().relative_to(Path(root).resolve())
    except ValueError:
        return False
    return True


class BoundedProcessResult(NamedTuple):
    stdout: bytes
    stderr: bytes
    timed_out: bool
    output_limited: bool


def communicate_bounded(
    process: subprocess.Popen[bytes],
    *,
    timeout_s: float,
    max_output_bytes: int,
    kill: Callable[[], None],
) -> BoundedProcessResult:
    """Read subprocess pipes with timeout and per-stream byte limits."""

    selector = selectors.DefaultSelector()
    buffers = {"stdout": bytearray(), "stderr": bytearray()}
    streams = {
        "stdout": process.stdout,
        "stderr": process.stderr,
    }
    for name, stream in streams.items():
        if stream is not None:
            selector.register(stream, selectors.EVENT_READ, name)

    timed_out = False
    output_limited = False
    killed = False
    deadline = time.monotonic() + max(timeout_s, 0.01)
    drain_deadline: float | None = None

    def stop_process() -> None:
        nonlocal killed, drain_deadline
        if not killed:
            kill()
            killed = True
            drain_deadline = time.monotonic() + 1.0

    try:
        while selector.get_map():
            now_value = time.monotonic()
            current_deadline = drain_deadline if killed else deadline
            if current_deadline is not None and now_value >= current_deadline:
                if not killed:
                    timed_out = True
                    stop_process()
                    continue
                break
            wait = min(0.1, max(0.0, current_deadline - now_value))
            events = selector.select(wait)
            if not events:
                continue
            for key, _ in events:
                name = str(key.data)
                try:
                    chunk = os.read(key.fileobj.fileno(), 64 * 1024)
                except (BlockingIOError, OSError):
                    chunk = b""
                if not chunk:
                    try:
                        selector.unregister(key.fileobj)
                    except (KeyError, ValueError):
                        pass
                    continue
                room = max_output_bytes - len(buffers[name])
                if room > 0:
                    buffers[name].extend(chunk[:room])
                if len(chunk) > max(room, 0):
                    output_limited = True
                    stop_process()
    finally:
        selector.close()
        for stream in streams.values():
            if stream is not None:
                stream.close()
        try:
            process.wait(timeout=1.0)
        except subprocess.TimeoutExpired:
            timed_out = True
            stop_process()
            try:
                process.wait(timeout=1.0)
            except subprocess.TimeoutExpired:
                pass

    return BoundedProcessResult(
        bytes(buffers["stdout"]),
        bytes(buffers["stderr"]),
        timed_out,
        output_limited,
    )
