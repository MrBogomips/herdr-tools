import json
import tempfile
import unittest
from pathlib import Path

from herdr_api import ConfigError
from overrides import load_overrides, save_overrides, with_override


class OverridesFileTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.path = Path(self.directory.name) / "state" / "overrides.json"

    def tearDown(self):
        self.directory.cleanup()

    def test_a_missing_file_has_no_overrides(self):
        self.assertEqual(load_overrides(self.path), {})

    def test_saved_overrides_load_back(self):
        save_overrides(self.path, {"acme": "#ff5555", "globex": "#50fa7b"})

        self.assertEqual(load_overrides(self.path), {"acme": "#ff5555", "globex": "#50fa7b"})
        self.assertEqual(json.loads(self.path.read_text())["version"], 1)

    def test_saving_leaves_no_temporary_files(self):
        save_overrides(self.path, {"acme": "#ff5555"})

        self.assertEqual([entry.name for entry in self.path.parent.iterdir()], ["overrides.json"])

    def test_a_damaged_file_is_an_error_that_names_it(self):
        for content in ("{not json", '{"keys": []}', '{"keys": {"acme": {"color": 3}}}', '{"keys": {"acme": "#fff"}}'):
            with self.subTest(content=content):
                self.path.parent.mkdir(parents=True, exist_ok=True)
                self.path.write_text(content)

                with self.assertRaisesRegex(ConfigError, "overrides.json"):
                    load_overrides(self.path)


class WithOverrideTest(unittest.TestCase):
    def test_sets_a_key_without_touching_the_original(self):
        original = {"acme": "#ff5555"}

        updated = with_override(original, "globex", "#50fa7b")

        self.assertEqual(updated, {"acme": "#ff5555", "globex": "#50fa7b"})
        self.assertEqual(original, {"acme": "#ff5555"})

    def test_none_removes_the_key(self):
        self.assertEqual(with_override({"acme": "#ff5555"}, "acme", None), {})
        self.assertEqual(with_override({}, "acme", None), {})


if __name__ == "__main__":
    unittest.main()
