import json
import tempfile
import unittest
from pathlib import Path

from bench.config import (
    DEFAULT_MAX_COST_USD,
    DEFAULT_TOKEN_BUDGET,
    ConfigError,
    load_config,
    resolve_source,
)


class ConfigTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def write(self, name, text):
        p = self.tmp / name
        p.write_text(text, encoding="utf-8")
        return p

    def test_single_source_defaults(self):
        cfg = load_config(self.write("s.toml", "[a]\nsource = 'C:\\x\\a'\ntags = ['regression']\n"))
        s = cfg.suites["a"]
        self.assertEqual(s.sources, (Path("C:\\x\\a"),))
        self.assertEqual(s.tags, ("regression",))
        self.assertEqual(s.allow_tools, ("Write", "Edit"))
        self.assertEqual(s.token_budget, DEFAULT_TOKEN_BUDGET)
        self.assertEqual(s.max_cost_usd, DEFAULT_MAX_COST_USD)
        self.assertEqual(s.ablation, "with-without")

    def test_path_map_sorted_longest_first(self):
        text = (
            "[a]\nsource = 'C:\\x\\a'\n"
            "[a.path_map]\n'C:\\m' = 'm'\n'C:\\m\\' = 'm/'\n"
        )
        s = load_config(self.write("s.toml", text)).suites["a"]
        self.assertEqual(s.path_map[0], ("C:\\m\\", "m/"))

    def test_source_and_sources_conflict(self):
        p = self.write("s.toml", "[a]\nsource = 'x'\nsources = ['y']\n")
        with self.assertRaises(ConfigError):
            load_config(p)

    def test_missing_source(self):
        with self.assertRaises(ConfigError):
            load_config(self.write("s.toml", "[a]\ntags = []\n"))

    def test_protect_files_and_dirs(self):
        d = self.tmp / "topics"
        d.mkdir()
        (d / "b.md").write_text("x", encoding="utf-8")
        (d / "a.md").write_text("x", encoding="utf-8")
        (d / "skip.txt").write_text("x", encoding="utf-8")
        text = f"[protect]\nfiles = ['{self.tmp / 'raw.md'}']\ndirs = ['{d}']\n"
        cfg = load_config(self.write("s.toml", text))
        self.assertEqual(cfg.protected, (self.tmp / "raw.md", d / "a.md", d / "b.md"))
        self.assertEqual(cfg.suites, {})

    def test_resolve_plugin_source_prefers_user_scope(self):
        installed = self.write("installed.json", json.dumps({"plugins": {
            "fd@official": [
                {"scope": "project", "installPath": "C:\\p\\old"},
                {"scope": "user", "installPath": "C:\\p\\new"},
            ]}}))
        self.assertEqual(
            resolve_source("plugin:fd@official/frontend-design", installed),
            Path("C:\\p\\new") / "skills" / "frontend-design",
        )

    def test_resolve_plain_path(self):
        self.assertEqual(resolve_source("C:\\s\\x", self.tmp / "none.json"), Path("C:\\s\\x"))

    def test_resolve_unknown_plugin(self):
        installed = self.write("installed.json", json.dumps({"plugins": {}}))
        with self.assertRaises(ConfigError):
            resolve_source("plugin:nope@m/x", installed)

    def test_relative_paths_resolve_against_config_folder(self):
        text = "[protect]\nfiles = ['data/keep.md']\n[a]\nsource = 'skills/a'\n"
        cfg = load_config(self.write("s.toml", text))
        self.assertEqual(cfg.suites["a"].sources, (self.tmp.resolve() / "skills" / "a",))
        self.assertEqual(cfg.protected, (self.tmp.resolve() / "data" / "keep.md",))


if __name__ == "__main__":
    unittest.main()
