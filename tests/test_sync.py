import json
import tempfile
import unittest
from pathlib import Path

from bench.config import SuiteConfig
from bench.protect import sha256_file
from bench.sync import SyncError, home_path_pattern, sync_suite

MEM = "C:\\Users\\someone\\.claude\\projects\\X\\memory"


def cfg(name, sources, path_map=()):
    return SuiteConfig(
        name=name, sources=tuple(sources), tags=("regression",), allow_tools=("Write",),
        token_budget=1, max_cost_usd=1.0, ablation="with-without",
        path_map=tuple(sorted(path_map, key=lambda kv: len(kv[0]), reverse=True)),
    )


class SyncTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.suites = self.tmp / "suites"
        self.src = self.tmp / "src dir with spaces" / "my-skill"
        self.src.mkdir(parents=True)

    def skill(self, text, newline="\n"):
        p = self.src / "SKILL.md"
        with open(p, "w", encoding="utf-8", newline=newline) as fh:
            fh.write(text)
        return p

    def test_source_path_with_spaces(self):
        self.skill("---\nname: my-skill\n---\nhello\n")
        hashes = sync_suite(cfg("s", [self.src]), self.suites)
        copy = self.suites / "s" / "skills" / "my-skill" / "SKILL.md"
        self.assertTrue(copy.is_file())
        self.assertEqual(hashes, {"my-skill": sha256_file(self.src / "SKILL.md")})
        manifest = json.loads((self.suites / "s" / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["name"], "bench-s")
        stored = json.loads((self.suites / "s" / ".source-hash").read_text(encoding="utf-8"))
        self.assertEqual(stored, hashes)

    def test_path_map_applied_and_source_untouched(self):
        original = f"Write to {MEM}\\raw.md and {MEM}.\n"
        src = self.skill(original)
        before = sha256_file(src)
        sync_suite(cfg("s", [self.src], [(MEM + "\\", "memory/"), (MEM, "memory")]), self.suites)
        copy = (self.suites / "s" / "skills" / "my-skill" / "SKILL.md").read_text(encoding="utf-8")
        self.assertEqual(copy, "Write to memory/raw.md and memory.\n")
        self.assertEqual(sha256_file(src), before)

    def test_forward_slash_variant_mapped(self):
        self.skill("see C:/Users/someone/.claude/projects/X/memory/raw.md\n")
        sync_suite(cfg("s", [self.src], [(MEM + "\\", "memory/")]), self.suites)
        copy = (self.suites / "s" / "skills" / "my-skill" / "SKILL.md").read_text(encoding="utf-8")
        self.assertEqual(copy, "see memory/raw.md\n")

    def test_leftover_user_path_fails(self):
        self.skill(f"line one\nuse {str(Path.home()).lower()}/Desktop/x\n")
        with self.assertRaises(SyncError) as ctx:
            sync_suite(cfg("s", [self.src]), self.suites)
        self.assertIn("SKILL.md:2", str(ctx.exception))
        self.assertFalse((self.suites / "s" / "skills").exists())

    def test_crlf_preserved(self):
        self.skill(f"a\r\n{MEM}\\x\r\n", newline="")
        sync_suite(cfg("s", [self.src], [(MEM + "\\", "memory/")]), self.suites)
        raw = (self.suites / "s" / "skills" / "my-skill" / "SKILL.md").read_bytes()
        self.assertEqual(raw, b"a\r\nmemory/x\r\n")

    def test_missing_skill_md(self):
        with self.assertRaises(SyncError):
            sync_suite(cfg("s", [self.src]), self.suites)

    def test_old_copy_replaced(self):
        self.skill("v1\n")
        sync_suite(cfg("s", [self.src]), self.suites)
        (self.src / "SKILL.md").write_text("v2\n", encoding="utf-8")
        stale = self.suites / "s" / "skills" / "my-skill" / "old.md"
        stale.write_text("x", encoding="utf-8")
        sync_suite(cfg("s", [self.src]), self.suites)
        self.assertFalse(stale.exists())
        self.assertEqual((self.suites / "s" / "skills" / "my-skill" / "SKILL.md").read_text(encoding="utf-8"), "v2\n")

    def test_scaffold_assembled_from_fixture_and_extra(self):
        self.skill("x\n")
        suite = self.suites / "s"
        (suite / "evals" / "c1").mkdir(parents=True)
        (suite / "evals" / "c2").mkdir(parents=True)
        (suite / "evals" / "c1" / "case.yaml").write_text("name: c1\n", encoding="utf-8")
        (suite / "evals" / "c2" / "case.yaml").write_text("name: c2\n", encoding="utf-8")
        with open(suite / "evals" / "c2" / "extra.sh", "w", encoding="utf-8", newline="") as fh:
            fh.write("echo extra\r\n")
        with open(suite / "_fixture.sh", "w", encoding="utf-8", newline="") as fh:
            fh.write("#!/usr/bin/env bash\r\necho base\r\n")
        sync_suite(cfg("s", [self.src]), self.suites)
        self.assertEqual((suite / "evals" / "c1" / "scaffold.sh").read_bytes(), b"#!/usr/bin/env bash\necho base\n")
        self.assertEqual(
            (suite / "evals" / "c2" / "scaffold.sh").read_bytes(),
            b"#!/usr/bin/env bash\necho base\n\necho extra\n",
        )

    def test_multiple_sources(self):
        self.skill("a\n")
        other = self.tmp / "other-skill"
        other.mkdir()
        (other / "SKILL.md").write_text("b\n", encoding="utf-8")
        hashes = sync_suite(cfg("s", [self.src, other]), self.suites)
        self.assertEqual(sorted(hashes), ["my-skill", "other-skill"])

    def test_home_pattern_matches_both_separators(self):
        pat = home_path_pattern(Path("C:/Users/someone"))
        self.assertTrue(pat.search("c:\\users\\someone\\x"))
        self.assertTrue(pat.search("C:/Users/someone/x"))
        self.assertFalse(pat.search("C:/Users/someone2/x"))


if __name__ == "__main__":
    unittest.main()
