"""Daily Markdown report and state for comparison."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from bench.tokens import TOKEN_KEYS

KINDS = ("happy", "edge", "near-miss", "gate", "held-out")
TOKEN_LABELS = dict(zip(TOKEN_KEYS, ("input", "output", "cache write", "cache read")))
_TAGS = re.compile(r"^tags:\s*\[([^\]]*)\]", re.MULTILINE)


def case_kind(case_dir: Path) -> str:
    for fname in ("case.yaml", "prompt.md"):
        f = case_dir / fname
        if f.is_file():
            m = _TAGS.search(f.read_text(encoding="utf-8"))
            if m:
                tags = [t.strip().strip("'\"") for t in m.group(1).split(",")]
                for kind in KINDS:
                    if kind in tags:
                        return kind
    return "?"


@dataclass
class CaseRow:
    suite: str
    case: str
    kind: str
    status: str
    passed_runs: int
    total_runs: int
    mean: float | None
    delta: float | None
    out_tokens: int | None
    total_tokens: int | None
    regression: bool = False
    reason: str = ""


def _run_error(case: dict) -> str:
    """First agent error in either arm. Graders still score an errored run against the untouched scaffold."""
    for runs in (case.get("arms") or {}).values():
        for r in runs or []:
            if r.get("error"):
                text = " ".join(str(r["error"]).split())
                return text if len(text) <= 160 else text[:157] + "..."
    return ""


def _case_tokens(records: list[dict], case: str) -> tuple[int | None, int | None]:
    rs = [r for r in records if r.get("case") == case]
    if not rs or any(r.get("usage") is None for r in rs):
        return None, None
    out = sum(r["usage"]["output_tokens"] for r in rs if r.get("arm") == "with")
    total = sum(sum(r["usage"].values()) for r in rs)
    return out, total


def case_rows(suite: str, result: dict, records: list[dict], suite_dir: Path, config_problems: set[str]) -> list[CaseRow]:
    rows = []
    for case in result.get("cases", []):
        name = case.get("name", "?")
        runs = (case.get("arms") or {}).get("with") or []
        scores = [r["score"] for r in runs if isinstance(r.get("score"), (int, float))]
        passed = sum(1 for r in runs if r.get("passed") is True)
        error = _run_error(case)
        if name in config_problems or not scores or error:
            status = "not-run"
        elif passed == len(runs):
            status = "pass"
        else:
            status = "fail"
        out, total = _case_tokens(records, name)
        rows.append(CaseRow(
            suite=suite, case=name, kind=case_kind(suite_dir / "evals" / name), status=status,
            passed_runs=passed, total_runs=len(runs),
            mean=sum(scores) / len(scores) if scores else None,
            delta=(case.get("aggregates") or {}).get("delta"),
            out_tokens=out, total_tokens=total,
            reason=f"agent run failed: {error}" if error else "",
        ))
    return rows


def _load(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _previous_state(results_dir: Path, date: str) -> dict:
    states = sorted(p for p in results_dir.glob("*.state.json") if p.name.split(".")[0] < date)
    prev = _load(states[-1]) if states else None
    return prev or {"cases": {}, "source_hashes": {}}


def _num(v, digits: int = 2) -> str:
    if v is None:
        return "-"
    if isinstance(v, float):
        return f"{v:.{digits}f}"
    return str(v)


def _row_line(r: CaseRow) -> str:
    flag = " REGRESSION" if r.regression else ""
    return (f"| {r.suite} | {r.case} | {r.kind} | {r.passed_runs}/{r.total_runs} | {_num(r.mean)} | "
            f"{_num(r.delta)} | {_num(r.out_tokens)} | {_num(r.total_tokens)} | {r.status}{flag} |")


def build_report(date: str, raw_dir: Path, suites_dir: Path, results_dir: Path) -> Path:
    metas = [m for m in (_load(p) for p in sorted(raw_dir.glob(f"{date}-*.meta.json"))) if m]
    prev = _previous_state(results_dir, date)
    rows: list[CaseRow] = []
    not_run: list[tuple[str, str, str]] = []
    versions: set[str] = set()
    models: set[str] = set()
    totals = {k: 0 for k in TOKEN_KEYS}
    incomplete = False
    suite_tokens: dict[str, int] = {}

    for meta in metas:
        suite = meta["suite"]
        if meta["status"] == "not-run":
            not_run.append((suite, "(whole suite)", meta.get("reason", "")))
            continue
        not_run += [(suite, case, f"case file failed to load: {why}") for case, why in meta.get("load_errors", [])]
        result = _load(raw_dir / f"{date}-{suite}.json") or {}
        records = _load(raw_dir / f"{date}-{suite}.tokens.json") or []
        if result.get("claudeVersion"):
            versions.add(result["claudeVersion"])
        suite_tokens[suite] = 0
        for r in records:
            models.update(r.get("models") or [])
            if r.get("usage") is None:
                incomplete = True
                continue
            for k in TOKEN_KEYS:
                totals[k] += r["usage"].get(k, 0)
            suite_tokens[suite] += sum(r["usage"].values())
        for row in case_rows(suite, result, records, suites_dir / suite, set(meta.get("config_problems", []))):
            if meta["status"] == "invalid":
                row.status = "invalid"
            row.regression = prev["cases"].get(f"{suite}/{row.case}") == "pass" and row.status == "fail"
            if row.status == "not-run":
                not_run.append((suite, row.case, row.reason or "config problem or interrupted"))
            rows.append(row)

    partial = [m["suite"] for m in metas if m.get("partial")]
    invalid = [m["suite"] for m in metas if m["status"] == "invalid"]
    regressions = [r for r in rows if r.regression]
    token_line = " / ".join(f"{TOKEN_LABELS[k]} {totals[k]}" for k in TOKEN_KEYS)

    lines = [f"# Skill Eval Bench: {date}", ""]
    lines.append(f"- Claude Code: {', '.join(sorted(versions)) or '-'}")
    lines.append(f"- Models: {', '.join(sorted(models)) or '-'}")
    lines.append(f"- Tokens total: {token_line}{' (incomplete)' if incomplete else ''}")
    lines.append(f"- Regressions: {len(regressions)}")
    if partial:
        lines.append(f"- PARTIAL: {', '.join(partial)}")
    if invalid:
        lines.append(f"- INVALID: {', '.join(invalid)} (protected files changed, results not valid)")
    lines += ["", "## Per skill", "",
              "| skill | changed | cases | pass^N | mean | Δ | tokens | status |",
              "|---|---|---|---|---|---|---|---|"]
    for meta in metas:
        suite = meta["suite"]
        srows = [r for r in rows if r.suite == suite]
        counted = [r for r in srows if r.status in ("pass", "fail")]
        means = [r.mean for r in counted if r.mean is not None]
        deltas = [r.delta for r in counted if isinstance(r.delta, (int, float))]
        old = prev["source_hashes"].get(suite)
        changed_flag = "first run" if old is None else ("yes" if old != meta.get("source_hashes") else "no")
        lines.append(
            f"| {suite} | {changed_flag} | {len(srows)} | {sum(r.status == 'pass' for r in counted)}/{len(counted)} | "
            f"{_num(sum(means) / len(means) if means else None)} | {_num(sum(deltas) / len(deltas) if deltas else None)} | "
            f"{_num(suite_tokens.get(suite))} | {meta['status']}{' PARTIAL' if meta.get('partial') else ''} |"
        )
    header = ["| skill | case | kind | pass^N | mean | Δ | output tokens | total tokens | status |",
              "|---|---|---|---|---|---|---|---|---|"]
    lines += ["", "## Per case", ""] + header
    lines += [_row_line(r) for r in rows if r.kind != "held-out"]
    lines += ["", "## Held-out", ""] + header
    lines += [_row_line(r) for r in rows if r.kind == "held-out"]
    lines += ["", "## Not run", "", "| skill | case | reason |", "|---|---|---|"]
    lines += [f"| {s} | {c} | {why} |" for s, c, why in not_run]

    results_dir.mkdir(parents=True, exist_ok=True)
    md_path = results_dir / f"{date}.md"
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    state = {
        "cases": {f"{r.suite}/{r.case}": r.status for r in rows},
        "source_hashes": {m["suite"]: m.get("source_hashes", {}) for m in metas if m["status"] != "not-run"},
    }
    (results_dir / f"{date}.state.json").write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return md_path
