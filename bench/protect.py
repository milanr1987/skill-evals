"""Hash protected files before and after a run."""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


@dataclass(frozen=True)
class FileState:
    size: int | None
    sha256: str | None


def _state(path: Path) -> FileState:
    if not path.is_file():
        return FileState(None, None)
    return FileState(path.stat().st_size, sha256_file(path))


def snapshot(paths: Iterable[Path]) -> dict[str, FileState]:
    return {str(p): _state(Path(p)) for p in paths}


def changed(before: dict[str, FileState], after: dict[str, FileState]) -> list[str]:
    return sorted(k for k in before.keys() | after.keys() if before.get(k) != after.get(k))
