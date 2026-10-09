import tempfile
import unittest
from pathlib import Path

from bench.protect import FileState, changed, sha256_file, snapshot


class ProtectTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.f = self.tmp / "raw.md"
        self.f.write_text("abc", encoding="utf-8")

    def test_sha256_known_value(self):
        self.assertEqual(
            sha256_file(self.f),
            "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad",
        )

    def test_unchanged(self):
        before = snapshot([self.f])
        self.assertEqual(changed(before, snapshot([self.f])), [])

    def test_content_change_detected(self):
        before = snapshot([self.f])
        self.f.write_text("abd", encoding="utf-8")
        self.assertEqual(changed(before, snapshot([self.f])), [str(self.f)])

    def test_missing_file_is_stable(self):
        missing = self.tmp / "nope.md"
        before = snapshot([missing])
        self.assertEqual(before[str(missing)], FileState(None, None))
        self.assertEqual(changed(before, snapshot([missing])), [])

    def test_created_file_detected(self):
        new = self.tmp / "new.md"
        before = snapshot([new])
        new.write_text("x", encoding="utf-8")
        self.assertEqual(changed(before, snapshot([new])), [str(new)])


if __name__ == "__main__":
    unittest.main()
