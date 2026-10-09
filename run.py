#!/usr/bin/env python3
"""Skill Eval Bench CLI: sync | test | report."""
from __future__ import annotations

import argparse
import datetime
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bench.config import BenchConfig, ConfigError, load_config  # noqa: E402
from bench.evalrun import version_ok  # noqa: E402
from bench.report import build_report  # noqa: E402
from bench.sync import SyncError, sync_suite  # noqa: E402
from bench.testcmd import run_tests  # noqa: E402


def claude_version(exe: str) -> str:
    proc = subprocess.run([exe, "--version"], capture_output=True, text=True, encoding="utf-8", errors="replace")
    return proc.stdout or ""


def select_suites(config: BenchConfig, suite: str | None, tag: str | None) -> list[str]:
    if suite:
        if suite not in config.suites:
            raise SystemExit(f"unknown suite: {suite}")
        return [suite]
    tag = tag or "regression"
    names = [n for n, c in config.suites.items() if tag in c.tags]
    if not names:
        raise SystemExit(f"no suite has tag '{tag}'")
    return names


def config_path(root: Path) -> Path:
    local = root / "skills.local.toml"
    return local if local.is_file() else root / "skills.toml"


def _today() -> str:
    return datetime.date.today().isoformat()


def main(argv: list[str] | None = None, root: Path = ROOT) -> int:
    parser = argparse.ArgumentParser(prog="run.py", description="Skill Eval Bench")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_sync = sub.add_parser("sync", help="copy skills into their wrapper plugins (no model calls)")
    p_sync.add_argument("suite", nargs="?")
    p_test = sub.add_parser("test", help="run evals (uses Claude usage)")
    p_test.add_argument("suite", nargs="?")
    p_test.add_argument("--tag")
    p_test.add_argument("--runs", type=int, default=3)
    p_test.add_argument("--token-budget", type=int)
    p_report = sub.add_parser("report", help="build the report for a date")
    p_report.add_argument("--date", default=_today())
    args = parser.parse_args(argv)

    cfg_path = config_path(root)
    try:
        config = load_config(cfg_path)
    except ConfigError as exc:
        print(f"error in {cfg_path.name}: {exc}")
        return 1
    suites_dir = root / "suites"
    raw_dir = root / "results" / "raw"

    if args.cmd == "sync":
        names = [args.suite] if args.suite else list(config.suites)
        code = 0
        for name in names:
            try:
                hashes = sync_suite(config.suites[name], suites_dir)
                print(f"{name}: ok {hashes}")
            except SyncError as exc:
                print(f"{name}: ERROR {exc}")
                code = 1
        return code

    if args.cmd == "report":
        print(build_report(args.date, raw_dir, suites_dir, root / "results"))
        return 0

    exe = shutil.which("claude")
    if not exe:
        print("claude is not on PATH")
        return 2
    version = claude_version(exe)
    if not version_ok(version):
        print(f"Claude Code >= 2.1.269 required, found: {version.strip() or '?'}")
        return 2
    names = select_suites(config, args.suite, args.tag)
    budget = args.token_budget or sum(config.suites[n].token_budget for n in names)
    date = _today()
    print(f"running {', '.join(names)} (runs={args.runs}, token budget={budget}); uses Claude usage")
    runs = run_tests(config, names, suites_dir, raw_dir, date, args.runs, budget, exe, Path(tempfile.gettempdir()))
    report = build_report(date, raw_dir, suites_dir, root / "results")
    for r in runs:
        print(f"{r.suite}: {r.status} {r.reason} tokens={r.tokens_total}")
    print(f"report: {report}")
    return 1 if any(r.status == "invalid" for r in runs) else 0


if __name__ == "__main__":
    sys.exit(main())
