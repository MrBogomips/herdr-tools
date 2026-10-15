import dataclasses
import json
import tempfile
import unittest
from pathlib import Path

from config import DEFAULTS, Config, build_config, config_to_dict, load_config, save_config
from herdr_api import ConfigError


class ConfigTestCase(unittest.TestCase):
    def setUp(self) -> None:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.dir = Path(directory.name)
        self.path = self.dir / "config.json"

    def write(self, content: object) -> None:
        text = content if isinstance(content, str) else json.dumps(content)
        self.path.write_text(text, encoding="utf-8")

    def assert_rejected(self, content: object, key: str) -> None:
        self.write(content)
        with self.assertRaises(ConfigError) as caught:
            load_config(self.path)
        message = str(caught.exception)
        self.assertTrue(message.startswith("{}: ".format(self.path)), message)
        self.assertIn(key, message)


class LoadConfigTests(ConfigTestCase):
    def test_missing_file_gives_defaults(self) -> None:
        self.assertEqual(load_config(self.path), Config())

    def test_full_file_gives_its_values(self) -> None:
        self.write(
            {
                "auto_sync": False,
                "format": "repo_branch",
                "depth": 3,
                "max_length": 0,
                "source": "cwd",
                "home_tilde": False,
            }
        )
        self.assertEqual(
            load_config(self.path),
            Config(auto_sync=False, format="repo_branch", depth=3, max_length=0, source="cwd", home_tilde=False),
        )

    def test_partial_file_keeps_other_defaults(self) -> None:
        self.write({"depth": 5})
        self.assertEqual(load_config(self.path), Config(depth=5))

    def test_unknown_key(self) -> None:
        self.assert_rejected({"colour": "red"}, "colour")

    def test_bad_json(self) -> None:
        self.write("{not json")
        with self.assertRaises(ConfigError) as caught:
            load_config(self.path)
        self.assertTrue(str(caught.exception).startswith("{}: ".format(self.path)))

    def test_top_level_not_an_object(self) -> None:
        self.write("[1, 2]")
        with self.assertRaises(ConfigError) as caught:
            load_config(self.path)
        self.assertTrue(str(caught.exception).startswith("{}: ".format(self.path)))

    def test_bool_keys_reject_non_bools(self) -> None:
        self.assert_rejected({"auto_sync": 1}, "auto_sync")
        self.assert_rejected({"home_tilde": "yes"}, "home_tilde")

    def test_int_keys_reject_non_ints(self) -> None:
        self.assert_rejected({"depth": True}, "depth")
        self.assert_rejected({"depth": 2.5}, "depth")
        self.assert_rejected({"max_length": False}, "max_length")

    def test_int_ranges(self) -> None:
        self.assert_rejected({"depth": 0}, "depth")
        self.assert_rejected({"max_length": -1}, "max_length")

    def test_choice_keys(self) -> None:
        self.assert_rejected({"format": "nope"}, "format")
        self.assert_rejected({"source": "nope"}, "source")


class BuildConfigTests(unittest.TestCase):
    def test_origin_prefixes_the_message(self) -> None:
        with self.assertRaises(ConfigError) as caught:
            build_config({**DEFAULTS, "depth": 0}, "the-origin")
        self.assertTrue(str(caught.exception).startswith("the-origin: "))

    def test_defaults_build_the_default_config(self) -> None:
        self.assertEqual(build_config(DEFAULTS, "x"), Config())


class SaveConfigTests(ConfigTestCase):
    def test_config_to_dict_follows_defaults_order(self) -> None:
        data = config_to_dict(Config(depth=4))
        self.assertEqual(list(data), list(DEFAULTS))
        self.assertEqual(data["depth"], 4)

    def test_round_trip(self) -> None:
        config = dataclasses.replace(Config(), format="last_n", depth=4, home_tilde=False)
        save_config(self.path, config)
        self.assertEqual(load_config(self.path), config)

    def test_creates_missing_parent_dirs(self) -> None:
        target = self.dir / "a" / "b" / "config.json"
        save_config(target, Config())
        self.assertTrue(target.is_file())

    def test_output_is_indented_json_in_defaults_order(self) -> None:
        save_config(self.path, Config())
        text = self.path.read_text(encoding="utf-8")
        self.assertEqual(text, json.dumps(dict(DEFAULTS), indent=2) + "\n")

    def test_leaves_no_temp_file_behind(self) -> None:
        save_config(self.path, Config())
        self.assertEqual([entry.name for entry in self.dir.iterdir()], ["config.json"])

    def test_input_is_unchanged(self) -> None:
        config = Config(depth=3)
        save_config(self.path, config)
        self.assertEqual(config, Config(depth=3))
        with self.assertRaises(dataclasses.FrozenInstanceError):
            config.depth = 9  # type: ignore[misc]


if __name__ == "__main__":
    unittest.main()
