"""Run suites: sync, protection, eval, tokens, budget."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

from bench import evalrun
from bench.config import BenchConfig
from bench.protect import changed, snapshot
from bench.sync import SyncError, sync_suite
from bench.tokens import collect_tokens, record_total


@dataclass
class SuiteRun:
    suite: str
    status: str
    reason: str = ""
    exit_code: int | None = None
    partial: bool = False
    tokens_total: int = 0
    config_problems: list[str] = field(default_factory=list)
    source_hashes: dict[str, str] = field(default_factory=dict)


def _write_json(path: Path, data) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _load(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def run_tests(config: BenchConfig, names: list[str], suites_dir: Path, raw_dir: Path, date: str,
              runs: int, token_budget: int, claude_exe: str, temp_root: Path, invoke=None) -> list[SuiteRun]:
    invoke = invoke or evalrun.invoke_eval
    raw_dir.mkdir(parents=True, exist_ok=True)
    spent = 0
    results: list[SuiteRun] = []
    for name in names:
        cfg = config.suites[name]
        prefix = raw_dir / f"{date}-{name}"
        out_json = prefix.with_name(prefix.name + ".json")
        run = SuiteRun(suite=name, status="not-run")
        if spent >= token_budget:
            run.reason = "token budget"
        else:
            try:
                run.source_hashes = sync_suite(cfg, suites_dir)
            except SyncError as exc:
                run.reason = str(exc)
            else:
                if out_json.exists():
                    out_json.unlink()
                before = snapshot(config.protected)
                cmd = evalrun.build_command(claude_exe, suites_dir / name, cfg, runs, out_json)
                outcome = invoke(cmd)
                after = snapshot(config.protected)
                prefix.with_name(prefix.name + ".log").write_text(outcome.output, encoding="utf-8")
                run.exit_code = outcome.exit_code
                run.config_problems = evalrun.config_problem_cases(outcome.output)
                result = _load(out_json)
                records = collect_tokens(result, temp_root) if result else []
                _write_json(prefix.with_name(prefix.name + ".tokens.json"), records)
                run.tokens_total = sum(t for t in (record_total(r) for r in records) if t is not None)
                spent += run.tokens_total
                run.partial = outcome.exit_code == 2 or bool(result and result.get("partial"))
                diff = changed(before, after)
                if diff:
                    run.status = "invalid"
                    run.reason = "protected files changed: " + ", ".join(diff)
                elif result is None:
                    run.reason = f"no JSON output (exit {outcome.exit_code})"
                else:
                    run.status = "ok"
        _write_json(prefix.with_name(prefix.name + ".meta.json"), asdict(run))
        results.append(run)
    return results
