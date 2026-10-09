"""Fake claude plugin eval outputs for tests (shape from the 2026-10-07 spike)."""
import json
from pathlib import Path


def make_trace(run_dir: Path, usage, model="claude-opus-5-5"):
    out = run_dir / "out"
    out.mkdir(parents=True, exist_ok=True)
    trace = out / "trace.jsonl"
    lines = [
        {"type": "system"},
        {"type": "assistant", "message": {"usage": {"input_tokens": 1, "output_tokens": 2}}},
    ]
    if usage is not None:
        lines.append({"type": "result", "usage": usage, "modelUsage": {model: {}}})
    trace.write_text("\n".join(json.dumps(x) for x in lines) + "\n", encoding="utf-8")
    return trace


def run_entry(trace, score=1, passed=True):
    return {"score": score, "passed": passed, "turns": 3, "costUsd": 0.06, "tracePath": str(trace)}


def make_result(cases, partial=False, version="2.1.292"):
    return {
        "schemaVersion": 1,
        "claudeVersion": version,
        "costUsd": 0.12,
        "partial": partial,
        "cases": cases,
        "aggregates": {},
    }
