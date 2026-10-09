"""Token counts from trace.jsonl and cleanup of temporary run folders."""
from __future__ import annotations

import json
import os
import shutil
import stat
from pathlib import Path

TOKEN_KEYS = ("input_tokens", "output_tokens", "cache_creation_input_tokens", "cache_read_input_tokens")
RUN_DIR_PREFIX = "claude-eval-"


def read_result(trace_path: Path) -> tuple[dict[str, int], list[str]] | None:
    if not trace_path.is_file():
        return None
    found = None
    with open(trace_path, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if obj.get("type") == "result" and isinstance(obj.get("usage"), dict):
                usage = {k: int(obj["usage"].get(k) or 0) for k in TOKEN_KEYS}
                models = sorted((obj.get("modelUsage") or {}).keys())
                found = (usage, models)
    return found


def _force_remove(func, path, _exc):
    try:
        os.chmod(path, stat.S_IWRITE)
        func(path)
    except OSError:
        pass


def cleanup_run_dir(trace_path: Path, temp_root: Path) -> bool:
    run_dir = trace_path.parent.parent
    if not run_dir.name.startswith(RUN_DIR_PREFIX):
        return False
    try:
        run_dir.resolve().relative_to(temp_root.resolve())
    except ValueError:
        return False
    if run_dir.exists():
        shutil.rmtree(run_dir, onexc=_force_remove)
    return True


def collect_tokens(result: dict, temp_root: Path, cleanup: bool = True) -> list[dict]:
    records: list[dict] = []
    for case in result.get("cases", []):
        arms = case.get("arms") or {}
        for arm in ("with", "without"):
            for index, run in enumerate(arms.get(arm) or []):
                usage, models = None, []
                trace_str = run.get("tracePath")
                if trace_str:
                    trace = Path(trace_str)
                    got = read_result(trace)
                    if got:
                        usage, models = got
                    if cleanup:
                        cleanup_run_dir(trace, temp_root)
                records.append({"case": case.get("name", "?"), "arm": arm, "index": index, "usage": usage, "models": models})
    return records


def record_total(record: dict) -> int | None:
    usage = record.get("usage")
    return None if usage is None else sum(usage.values())
