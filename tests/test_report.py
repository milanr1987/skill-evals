import json
import tempfile
import unittest
from pathlib import Path

from bench.report import build_report, case_kind

USAGE = {"input_tokens": 1, "output_tokens": 10, "cache_creation_input_tokens": 100, "cache_read_input_tokens": 1000}


def run(score, passed):
    return {"score": score, "passed": passed, "tracePath": "x"}


class ReportTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.raw = self.tmp / "results" / "raw"
        self.raw.mkdir(parents=True)
        self.results = self.tmp / "results"
        self.suites = self.tmp / "suites"
        for case, tag in (("c-pass", "happy"), ("c-fail", "edge"), ("c-held", "held-out"), ("c-cfg", "gate")):
            d = self.suites / "s" / "evals" / case
            d.mkdir(parents=True)
            (d / "case.yaml").write_text(f'schema_version: "1.1"\nname: {case}\ntags: [{tag}]\n', encoding="utf-8")

    def write_day(self, date, cases, status="ok", partial=False, hashes=None, problems=(), records=None):
        meta = {"suite": "s", "status": status, "reason": "", "exit_code": 0, "partial": partial,
                "tokens_total": 0, "config_problems": list(problems), "source_hashes": hashes or {"s": "h1"}}
        (self.raw / f"{date}-s.meta.json").write_text(json.dumps(meta), encoding="utf-8")
        result = {"claudeVersion": "2.1.292", "partial": partial, "cases": cases}
        (self.raw / f"{date}-s.json").write_text(json.dumps(result), encoding="utf-8")
        (self.raw / f"{date}-s.tokens.json").write_text(json.dumps(records or []), encoding="utf-8")

    def case(self, name, runs, delta=0.5):
        return {"name": name, "arms": {"with": runs, "without": [run(0, False)]}, "aggregates": {"delta": delta}}

    def test_case_kind(self):
        self.assertEqual(case_kind(self.suites / "s" / "evals" / "c-held"), "held-out")
        self.assertEqual(case_kind(self.tmp / "nope"), "?")

    def test_regression_held_out_tokens_and_state(self):
        self.write_day("2026-10-08", [self.case("c-pass", [run(1, True)] * 3), self.case("c-fail", [run(1, True)] * 3)])
        build_report("2026-10-08", self.raw, self.suites, self.results)
        records = [
            {"case": "c-fail", "arm": "with", "index": 0, "usage": USAGE, "models": ["claude-opus-5-5"]},
            {"case": "c-fail", "arm": "without", "index": 0, "usage": USAGE, "models": ["claude-opus-5-5"]},
        ]
        self.write_day(
            "2026-10-09",
            [self.case("c-pass", [run(1, True)] * 3),
             self.case("c-fail", [run(1, True), run(0, False), run(1, True)]),
             self.case("c-held", [run(1, True)] * 3),
             self.case("c-cfg", [run(0, False)])],
            hashes={"s": "h2"}, problems=["c-cfg"], records=records,
        )
        md = build_report("2026-10-09", self.raw, self.suites, self.results).read_text(encoding="utf-8")
        self.assertIn("REGRESSION", md)
        self.assertIn("| s | c-fail | edge | 2/3 |", md)
        self.assertIn("## Held-out", md)
        self.assertIn("| s | c-held | held-out | 3/3 |", md)
        self.assertIn("| s | c-cfg | config problem or interrupted |", md)
        self.assertIn("claude-opus-5-5", md)
        self.assertIn("output 20", md)
        self.assertIn("| s | yes | 4 |", md)  # skill changed (h1 -> h2), 4 cases
        self.assertNotIn("costUsd", md)
        state = json.loads((self.results / "2026-10-09.state.json").read_text(encoding="utf-8"))
        self.assertEqual(state["cases"]["s/c-fail"], "fail")
        self.assertEqual(state["cases"]["s/c-cfg"], "not-run")

    def test_missing_delta_and_without_arm(self):
        self.write_day("2026-10-08", [{"name": "c-pass", "arms": {"with": [run(1, True)]}}])
        md = build_report("2026-10-08", self.raw, self.suites, self.results).read_text(encoding="utf-8")
        self.assertIn("| s | c-pass | happy | 1/1 | 1.00 | - |", md)

    def test_partial_invalid_and_not_run_suite(self):
        self.write_day("2026-10-08", [self.case("c-pass", [run(1, True)])], status="invalid", partial=True)
        meta = {"suite": "t", "status": "not-run", "reason": "token budget", "exit_code": None, "partial": False,
                "tokens_total": 0, "config_problems": [], "source_hashes": {}}
        (self.raw / "2026-10-08-t.meta.json").write_text(json.dumps(meta), encoding="utf-8")
        md = build_report("2026-10-08", self.raw, self.suites, self.results).read_text(encoding="utf-8")
        self.assertIn("PARTIAL: s", md)
        self.assertIn("INVALID: s", md)
        self.assertIn("| t | (whole suite) | token budget |", md)

    def test_unknown_tokens_marked_incomplete(self):
        records = [{"case": "c-pass", "arm": "with", "index": 0, "usage": None, "models": []}]
        self.write_day("2026-10-08", [self.case("c-pass", [run(1, True)])], records=records)
        md = build_report("2026-10-08", self.raw, self.suites, self.results).read_text(encoding="utf-8")
        self.assertIn("(incomplete)", md)


if __name__ == "__main__":
    unittest.main()
