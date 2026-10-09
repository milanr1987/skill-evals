import unittest
from pathlib import Path

from bench.config import SuiteConfig
from bench.evalrun import build_command, config_problem_cases, load_error_cases, parse_version, unconfined_shell_tools, version_ok


def cfg(allow=("Write", "Edit"), ablation="with-without"):
    return SuiteConfig(name="s", sources=(Path("x"),), tags=(), allow_tools=tuple(allow),
                       token_budget=1, max_cost_usd=5.0, ablation=ablation, path_map=())


class EvalRunTests(unittest.TestCase):
    def test_version(self):
        self.assertEqual(parse_version("2.1.292 (Claude Code)"), (2, 1, 292))
        self.assertTrue(version_ok("2.1.269 (Claude Code)"))
        self.assertFalse(version_ok("2.1.268 (Claude Code)"))
        self.assertFalse(version_ok("garbage"))

    def test_build_command_required_flags(self):
        cmd = build_command("claude", Path("suites/s"), cfg(), 3, Path("results/raw/d-s.json"))
        for flag in ("--no-publish", "--trust-plugin", "--scaffold", "--keep-temp"):
            self.assertIn(flag, cmd)
        self.assertEqual(cmd[:3], ["claude", "plugin", "eval"])
        self.assertEqual(cmd[cmd.index("--runs") + 1], "3")
        self.assertEqual(cmd[cmd.index("--max-cost-usd") + 1], "5.0")
        self.assertEqual(cmd[cmd.index("--ablation") + 1], "with-without")
        self.assertEqual(cmd[-3:], ["--allow-tools", "Write", "Edit"])

    def test_build_command_keeps_spaces(self):
        suite = Path("C:/a b/suites/s")
        cmd = build_command("claude", suite, cfg(), 1, Path("o.json"))
        self.assertIn(str(suite), cmd)

    def test_build_command_without_tools(self):
        cmd = build_command("claude", Path("s"), cfg(allow=(), ablation="none"), 1, Path("o.json"))
        self.assertNotIn("--allow-tools", cmd)
        self.assertEqual(cmd[cmd.index("--ablation") + 1], "none")

    def test_config_problem_cases(self):
        out = (
            'Ablation: defaulting...\n'
            '⚠ case "adds-post": grader "exists" cannot pass with the granted tools: ...\n'
            '⚠ case "adds-post": grader "heading" cannot pass with the granted tools: ...\n'
            '⚠ case "other": grader "x" cannot pass with the granted tools\n'
        )
        self.assertEqual(config_problem_cases(out), ["adds-post", "other"])

    def test_unconfined_shell_tools(self):
        c = cfg(allow=("Write", "Bash", "PowerShell(git:*)"))
        self.assertEqual(unconfined_shell_tools(c, "win32"), ["Bash", "PowerShell(git:*)"])
        self.assertEqual(unconfined_shell_tools(c, "linux"), [])
        self.assertEqual(unconfined_shell_tools(cfg(), "win32"), [])

    def test_load_error_cases(self):
        out = (
            "Wrote C:\\x\\r.json\n"
            "✗ C:\\a b\\suites\\s\\evals\\probe-llm\\case.yaml: invalid case.yaml:   graders.0: Unrecognized key(s)\n"
            "✗ /home/u/suites/s/evals/other/prompt.md: missing prompt\n"
            "1 case file(s) failed to load\n"
        )
        self.assertEqual(load_error_cases(out), [
            ["other", "missing prompt"],
            ["probe-llm", "invalid case.yaml:   graders.0: Unrecognized key(s)"],
        ])
        self.assertEqual(load_error_cases("all good\n"), [])


if __name__ == "__main__":
    unittest.main()
