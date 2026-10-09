import tempfile
import unittest
from pathlib import Path

from bench.tokens import cleanup_run_dir, collect_tokens, read_result, record_total
from tests.helpers import make_result, make_trace, run_entry

USAGE = {"input_tokens": 8, "output_tokens": 432, "cache_creation_input_tokens": 6005, "cache_read_input_tokens": 39923}


class TokenTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())

    def test_read_result_uses_result_line_only(self):
        trace = make_trace(self.root / "claude-eval-a", USAGE)
        usage, models = read_result(trace)
        self.assertEqual(usage, USAGE)
        self.assertEqual(models, ["claude-opus-5-5"])

    def test_read_result_without_result_line(self):
        trace = make_trace(self.root / "claude-eval-a", None)
        self.assertIsNone(read_result(trace))

    def test_read_result_missing_file(self):
        self.assertIsNone(read_result(self.root / "nope" / "out" / "trace.jsonl"))

    def test_read_result_skips_garbage_lines(self):
        trace = make_trace(self.root / "claude-eval-a", USAGE)
        with open(trace, "a", encoding="utf-8") as fh:
            fh.write("not json\n")
        self.assertEqual(read_result(trace)[0], USAGE)

    def test_cleanup_only_prefixed_dirs_inside_temp_root(self):
        good = make_trace(self.root / "claude-eval-x", USAGE)
        self.assertTrue(cleanup_run_dir(good, self.root))
        self.assertFalse((self.root / "claude-eval-x").exists())

        bad_name = make_trace(self.root / "important", USAGE)
        self.assertFalse(cleanup_run_dir(bad_name, self.root))
        self.assertTrue((self.root / "important").exists())

        outside = Path(tempfile.mkdtemp()) / "claude-eval-y"
        trace = make_trace(outside, USAGE)
        self.assertFalse(cleanup_run_dir(trace, self.root))
        self.assertTrue(outside.exists())

    def test_collect_tokens_and_cleanup(self):
        t1 = make_trace(self.root / "claude-eval-1", USAGE)
        t2 = make_trace(self.root / "claude-eval-2", None)
        result = make_result([{"name": "c1", "arms": {"with": [run_entry(t1)], "without": [run_entry(t2, 0, False)]}}])
        records = collect_tokens(result, self.root)
        self.assertEqual(records[0], {"case": "c1", "arm": "with", "index": 0, "usage": USAGE, "models": ["claude-opus-5-5"]})
        self.assertEqual(records[1]["usage"], None)
        self.assertEqual(record_total(records[0]), 46368)
        self.assertIsNone(record_total(records[1]))
        self.assertFalse((self.root / "claude-eval-1").exists())
        self.assertFalse((self.root / "claude-eval-2").exists())

    def test_collect_tokens_no_cleanup(self):
        t1 = make_trace(self.root / "claude-eval-1", USAGE)
        result = make_result([{"name": "c1", "arms": {"with": [run_entry(t1)]}}])
        collect_tokens(result, self.root, cleanup=False)
        self.assertTrue((self.root / "claude-eval-1").exists())


if __name__ == "__main__":
    unittest.main()
