"""Build and invoke the claude plugin eval command."""
from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

from bench.config import SuiteConfig

MIN_VERSION = (2, 1, 269)
_VERSION = re.compile(r"(\d+)\.(\d+)\.(\d+)")
_CONFIG_WARNING = re.compile(r'case "([^"]+)": grader "[^"]+" cannot pass')
_LOAD_ERROR = re.compile(r"^✗ .*?([^\\/]+)[\\/](?:case\.yaml|prompt\.md): (.+)$", re.MULTILINE)


def parse_version(text: str) -> tuple[int, int, int] | None:
    m = _VERSION.search(text)
    return tuple(int(g) for g in m.groups()) if m else None


def version_ok(text: str) -> bool:
    v = parse_version(text)
    return v is not None and v >= MIN_VERSION


def build_command(claude_exe: str, suite_dir: Path, cfg: SuiteConfig, runs: int, out_json: Path) -> list[str]:
    cmd = [
        claude_exe, "plugin", "eval", str(suite_dir),
        "--no-publish", "--trust-plugin", "--scaffold", "--keep-temp",
        "--ablation", cfg.ablation,
        "--runs", str(runs),
        "--max-cost-usd", str(cfg.max_cost_usd),
        "--json", str(out_json),
    ]
    if cfg.allow_tools:
        cmd += ["--allow-tools", *cfg.allow_tools]
    return cmd


@dataclass(frozen=True)
class EvalOutcome:
    exit_code: int
    output: str


def invoke_eval(cmd: list[str]) -> EvalOutcome:
    proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    return EvalOutcome(proc.returncode, (proc.stdout or "") + (proc.stderr or ""))


def config_problem_cases(output: str) -> list[str]:
    return sorted(set(_CONFIG_WARNING.findall(output)))


def load_error_cases(output: str) -> list[list[str]]:
    """Cases whose case file failed to load; claude plugin eval skips them without a result."""
    return [list(pair) for pair in sorted({(m.group(1), m.group(2).strip()) for m in _LOAD_ERROR.finditer(output)})]
