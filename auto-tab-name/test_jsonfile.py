import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from jsonfile import write_json_atomic


class WriteJsonAtomicTest(unittest.TestCase):
    def setUp(self) -> None:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.dir = Path(directory.name)
        self.path = self.dir / "data.json"

    def test_writes_indented_json_with_trailing_newline_in_key_order(self) -> None:
        write_json_atomic(self.path, {"zeta": 1, "alpha": {"acme": True}})
        text = self.path.read_text(encoding="utf-8")
        self.assertEqual(text, '{\n  "zeta": 1,\n  "alpha": {\n    "acme": true\n  }\n}\n')
        self.assertEqual(list(json.loads(text)), ["zeta", "alpha"])

    def test_creates_parent_directories(self) -> None:
        path = self.dir / "deep" / "er" / "data.json"
        write_json_atomic(path, [1])
        self.assertEqual(json.loads(path.read_text(encoding="utf-8")), [1])

    def test_replaces_an_existing_file_and_leaves_no_temp_file(self) -> None:
        write_json_atomic(self.path, {"v": 1})
        write_json_atomic(self.path, {"v": 2})
        self.assertEqual(json.loads(self.path.read_text(encoding="utf-8")), {"v": 2})
        self.assertEqual(os.listdir(str(self.dir)), ["data.json"])

    def test_failure_keeps_the_original_error_and_the_old_file(self) -> None:
        write_json_atomic(self.path, {"v": 1})
        with mock.patch("jsonfile.os.replace", side_effect=OSError("disk gone")):
            with self.assertRaisesRegex(OSError, "disk gone"):
                write_json_atomic(self.path, {"v": 2})
        self.assertEqual(json.loads(self.path.read_text(encoding="utf-8")), {"v": 1})
        self.assertEqual(os.listdir(str(self.dir)), ["data.json"])

    def test_unserialisable_data_leaves_nothing_behind(self) -> None:
        with self.assertRaises(TypeError):
            write_json_atomic(self.path, {"bad": object()})
        self.assertEqual(os.listdir(str(self.dir)), [])

    def test_a_failing_cleanup_does_not_mask_the_original_error(self) -> None:
        with mock.patch("jsonfile.os.replace", side_effect=OSError("disk gone")), \
                mock.patch("jsonfile.os.unlink", side_effect=OSError("cannot unlink")):
            with self.assertRaisesRegex(OSError, "disk gone"):
                write_json_atomic(self.path, {"v": 1})


if __name__ == "__main__":
    unittest.main()
