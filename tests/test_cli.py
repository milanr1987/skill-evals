import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from bench.evalrun import EvalOutcome
from tests.helpers import make_result, make_trace, run_entry

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("run_cli", ROOT / "run.py")
run_cli = importlib.util.module_from_spec(spec)
spec.loader.exec_module(run_cli)

USAGE = {"input_tokens": 1, "output_tokens": 2, "cache_creation_input_tokens": 3, "cache_read_input_tokens": 4}


class CliTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        src = self.root / "src" / "sk"
        src.mkdir(parents=True)
        (src / "SKILL.md").write_text("x\n", encoding="utf-8")
        (self.root / "skills.toml").write_text(
            f"[a]\nsource = '{src}'\ntags = ['regression']\n[d]\nsource = '{src}'\ntags = ['delta']\n",
            encoding="utf-8",
        )
        case = self.root / "suites" / "a" / "evals" / "c1"
        case.mkdir(parents=True)
        (case / "case.yaml").write_text('name: c1\ntags: [happy]\n', encoding="utf-8")

    def fake_invoke(self, cmd):
        out = Path(cmd[cmd.index("--json") + 1])
        trace = make_trace(Path(tempfile.mkdtemp(prefix="claude-eval-")), USAGE)
        out.write_text(json.dumps(make_result([{"name": "c1", "arms": {"with": [run_entry(trace)]}}])), encoding="utf-8")
        return EvalOutcome(0, "")

    def test_select_suites(self):
        cfg = run_cli.load_config(self.root / "skills.toml")
        self.assertEqual(run_cli.select_suites(cfg, None, None), ["a"])
        self.assertEqual(run_cli.select_suites(cfg, None, "delta"), ["d"])
        self.assertEqual(run_cli.select_suites(cfg, "d", None), ["d"])
        with self.assertRaises(SystemExit):
            run_cli.select_suites(cfg, "nope", None)

    def test_sync_command(self):
        self.assertEqual(run_cli.main(["sync", "a"], root=self.root), 0)
        self.assertTrue((self.root / "suites" / "a" / "skills" / "sk" / "SKILL.md").is_file())

    def test_test_command_end_to_end(self):
        with mock.patch.object(run_cli.shutil, "which", return_value="claude"), \
             mock.patch.object(run_cli, "claude_version", return_value="2.1.292 (Claude Code)"), \
             mock.patch("bench.evalrun.invoke_eval", side_effect=self.fake_invoke):
            code = run_cli.main(["test", "--runs", "1"], root=self.root)
        self.assertEqual(code, 0)
        reports = list((self.root / "results").glob("*.md"))
        self.assertEqual(len(reports), 1)
        self.assertIn("| a | c1 | happy | 1/1 |", reports[0].read_text(encoding="utf-8"))

    def test_old_version_stops(self):
        with mock.patch.object(run_cli.shutil, "which", return_value="claude"), \
             mock.patch.object(run_cli, "claude_version", return_value="2.1.200 (Claude Code)"), \
             mock.patch("bench.evalrun.invoke_eval") as inv:
            self.assertEqual(run_cli.main(["test"], root=self.root), 2)
            inv.assert_not_called()

    def test_missing_claude_stops(self):
        with mock.patch.object(run_cli.shutil, "which", return_value=None):
            self.assertEqual(run_cli.main(["test"], root=self.root), 2)

    def test_local_config_preferred(self):
        self.assertEqual(run_cli.config_path(self.root), self.root / "skills.toml")
        (self.root / "skills.local.toml").write_text("", encoding="utf-8")
        self.assertEqual(run_cli.config_path(self.root), self.root / "skills.local.toml")


if __name__ == "__main__":
    unittest.main()
