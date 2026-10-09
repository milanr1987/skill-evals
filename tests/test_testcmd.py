import json
import tempfile
import unittest
from pathlib import Path

from bench.config import BenchConfig, SuiteConfig
from bench.evalrun import EvalOutcome
from bench.testcmd import run_tests
from tests.helpers import make_result, make_trace, run_entry

USAGE = {"input_tokens": 10, "output_tokens": 20, "cache_creation_input_tokens": 30, "cache_read_input_tokens": 40}


class FakeEval:
    """Fake claude plugin eval: writes JSON to the --json path and a trace under temp_root."""

    def __init__(self, temp_root, exit_code=0, write_json=True, touch=None, output=""):
        self.temp_root = temp_root
        self.exit_code = exit_code
        self.write_json = write_json
        self.touch = touch
        self.output = output
        self.calls = []

    def __call__(self, cmd):
        self.calls.append(cmd)
        out = Path(cmd[cmd.index("--json") + 1])
        if self.write_json:
            trace = make_trace(self.temp_root / f"claude-eval-{len(self.calls)}", USAGE)
            result = make_result([{"name": "c1", "arms": {"with": [run_entry(trace)]}, "aggregates": {"delta": 1}}])
            out.write_text(json.dumps(result), encoding="utf-8")
        if self.touch:
            self.touch.write_text("changed", encoding="utf-8")
        return EvalOutcome(self.exit_code, self.output)


class TestCmdTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.temp_root = Path(tempfile.mkdtemp())
        self.raw = self.tmp / "raw"
        self.raw.mkdir()
        self.suites = self.tmp / "suites"
        self.protected = self.tmp / "raw.md"
        self.protected.write_text("orig", encoding="utf-8")
        src = self.tmp / "skills" / "sk"
        src.mkdir(parents=True)
        (src / "SKILL.md").write_text("x\n", encoding="utf-8")
        mk = lambda n, s: SuiteConfig(n, (s,), ("regression",), ("Write",), 100, 1.0, "with-without", ())
        self.config = BenchConfig(
            suites={"a": mk("a", src), "b": mk("b", src), "broken": mk("broken", self.tmp / "missing")},
            protected=(self.protected,),
        )

    def run_names(self, names, fake, budget=10_000):
        return run_tests(self.config, names, self.suites, self.raw, "2026-10-08", 1, budget,
                         "claude", self.temp_root, invoke=fake)

    def meta(self, suite):
        return json.loads((self.raw / f"2026-10-08-{suite}.meta.json").read_text(encoding="utf-8"))

    def test_ok_run_writes_files_and_tokens(self):
        runs = self.run_names(["a"], FakeEval(self.temp_root))
        self.assertEqual(runs[0].status, "ok")
        self.assertEqual(runs[0].tokens_total, 100)
        tokens = json.loads((self.raw / "2026-10-08-a.tokens.json").read_text(encoding="utf-8"))
        self.assertEqual(tokens[0]["usage"], USAGE)
        self.assertEqual(list(self.meta("a")["source_hashes"]), ["sk"])
        self.assertFalse(any(self.temp_root.iterdir()))

    def test_protected_change_is_invalid(self):
        runs = self.run_names(["a"], FakeEval(self.temp_root, touch=self.protected))
        self.assertEqual(runs[0].status, "invalid")
        self.assertIn(str(self.protected), runs[0].reason)

    def test_missing_json_is_not_run(self):
        runs = self.run_names(["a"], FakeEval(self.temp_root, exit_code=1, write_json=False))
        self.assertEqual(runs[0].status, "not-run")
        self.assertIn("exit 1", runs[0].reason)

    def test_stale_json_removed(self):
        (self.raw / "2026-10-08-a.json").write_text(json.dumps(make_result([])), encoding="utf-8")
        runs = self.run_names(["a"], FakeEval(self.temp_root, write_json=False))
        self.assertEqual(runs[0].status, "not-run")

    def test_sync_error_is_not_run(self):
        fake = FakeEval(self.temp_root)
        runs = self.run_names(["broken", "a"], fake)
        self.assertEqual(runs[0].status, "not-run")
        self.assertIn("SKILL.md", runs[0].reason)
        self.assertEqual(runs[1].status, "ok")
        self.assertEqual(len(fake.calls), 1)

    def test_token_budget_stops_later_suites(self):
        fake = FakeEval(self.temp_root)
        runs = self.run_names(["a", "b"], fake, budget=50)
        self.assertEqual(runs[0].status, "ok")
        self.assertEqual(runs[1].status, "not-run")
        self.assertEqual(runs[1].reason, "token budget")
        self.assertEqual(len(fake.calls), 1)

    def test_partial_and_config_problems(self):
        out = '⚠ case "c1": grader "g" cannot pass with the granted tools'
        runs = self.run_names(["a"], FakeEval(self.temp_root, exit_code=2, output=out))
        self.assertTrue(runs[0].partial)
        self.assertEqual(self.meta("a")["config_problems"], ["c1"])
        self.assertTrue((self.raw / "2026-10-08-a.log").read_text(encoding="utf-8").startswith("⚠"))


if __name__ == "__main__":
    unittest.main()
