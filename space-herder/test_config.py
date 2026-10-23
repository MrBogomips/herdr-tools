import tempfile
import unittest
from pathlib import Path

from config import DEFAULTS, SLOT_LIMIT, build_config, load_config
from herdr_api import ConfigError
from palettes import PRESETS


def build(**overrides):
    return build_config({**DEFAULTS, **overrides}, "config.json")


class DefaultsTest(unittest.TestCase):
    def test_defaults_color_by_prefix_with_the_catppuccin_palette(self):
        config = build()

        self.assertEqual(config.palette, PRESETS["catppuccin"])
        self.assertEqual(config.palette_name, "catppuccin")
        self.assertEqual((config.key_mode, config.separator), ("prefix", " -"))
        self.assertEqual(config.marker, "▌")
        self.assertEqual(config.ignore_suffixes, (" +", " -"))
        self.assertTrue(config.ignore_case)
        self.assertTrue(config.worktrees_follow_parent)
        self.assertEqual(config.slots, PRESETS["catppuccin"])
        self.assertEqual(config.rules, ())

    def test_assigns_by_hash_unless_sticky_is_asked(self):
        self.assertEqual(build().assign, "hash")
        self.assertEqual(build(assign="sticky").assign, "sticky")

    def test_palette_size_keeps_the_first_colors(self):
        config = build(palette="catppuccin", palette_size=8)

        self.assertEqual(config.palette, PRESETS["catppuccin"][:8])
        self.assertEqual(config.slots, PRESETS["catppuccin"][:8])

    def test_custom_palette_is_named_custom(self):
        config = build(palette=["#f00", "#0f0"])

        self.assertEqual((config.palette, config.palette_name), (("#ff0000", "#00ff00"), "custom"))


class ValidationTest(unittest.TestCase):
    def assert_rejected(self, pattern, **overrides):
        with self.assertRaisesRegex(ConfigError, r"config\.json: .*" + pattern):
            build(**overrides)

    def test_rejects_an_unknown_key_mode(self):
        self.assert_rejected("key", key="middle")

    def test_rejects_an_empty_separator(self):
        self.assert_rejected("separator", separator="")

    def test_rejects_non_boolean_switches(self):
        self.assert_rejected("ignore_case", ignore_case="yes")
        self.assert_rejected("worktrees_follow_parent", worktrees_follow_parent=1)

    def test_rejects_a_marker_that_is_not_text(self):
        self.assert_rejected("marker", marker=None)

    def test_rejects_bad_ignore_suffixes(self):
        self.assert_rejected("ignore_suffixes", ignore_suffixes=" +")
        self.assert_rejected("ignore_suffixes", ignore_suffixes=[""])

    def test_rejects_a_bad_palette(self):
        self.assert_rejected("palette", palette="draculaa")

    def test_rejects_an_unknown_assign_mode(self):
        self.assert_rejected("assign", assign="random")

    def test_rejects_a_palette_size_outside_the_palette(self):
        for size in (0, 16, True, "8"):
            with self.subTest(size=size):
                self.assert_rejected("palette_size", palette="catppuccin", palette_size=size)

    def test_a_full_palette_suggests_palette_size_for_rule_colors(self):
        self.assert_rejected("palette_size", palette="catppuccin", rules=[{"match": "^~$", "color": None}])


class AutoSortTest(unittest.TestCase):
    def test_autosort_is_off_by_default(self):
        self.assertEqual(build().auto_sort, "off")

    def test_accepts_each_setting(self):
        for setting in ("off", "created", "renamed", "both"):
            with self.subTest(setting=setting):
                self.assertEqual(build(auto_sort=setting).auto_sort, setting)

    def test_rejects_an_unknown_setting(self):
        with self.assertRaisesRegex(ConfigError, r"config\.json: auto_sort.*always"):
            build(auto_sort="always")

    def test_rejects_a_setting_that_is_not_text(self):
        with self.assertRaisesRegex(ConfigError, r"config\.json: auto_sort"):
            build(auto_sort=["created", "renamed"])


class RulesTest(unittest.TestCase):
    PALETTE = ["#111111", "#222222"]

    def rules(self, *rules):
        return build(palette=self.PALETTE, rules=list(rules))

    def test_extra_rule_colors_get_slots_after_the_palette(self):
        config = self.rules({"match": "a", "color": "#333"}, {"match": "b", "color": "#444444"})

        self.assertEqual(config.slots, ("#111111", "#222222", "#333333", "#444444"))
        self.assertEqual([rule.slot for rule in config.rules], [2, 3])

    def test_a_repeated_extra_color_shares_one_slot(self):
        config = self.rules({"match": "a", "color": "#333333"}, {"match": "b", "color": "#333333"})

        self.assertEqual(len(config.slots), 3)
        self.assertEqual([rule.slot for rule in config.rules], [2, 2])

    def test_a_palette_color_reuses_the_palette_slot(self):
        config = self.rules({"match": "a", "color": "#222222"})

        self.assertEqual(config.slots, ("#111111", "#222222"))
        self.assertEqual(config.rules[0].slot, 1)

    def test_a_palette_index_selects_that_slot(self):
        self.assertEqual(self.rules({"match": "a", "color": 1}).rules[0].slot, 1)

    def test_null_color_uses_one_unstyled_slot_after_all_colors(self):
        config = self.rules({"match": "a", "color": None}, {"match": "b", "color": "#333333"}, {"match": "c", "color": None})

        self.assertEqual(config.slots, ("#111111", "#222222", "#333333", None))
        self.assertEqual([rule.slot for rule in config.rules], [3, 2, 3])

    def test_rule_patterns_follow_ignore_case(self):
        self.assertTrue(self.rules({"match": "^acme", "color": 0}).rules[0].pattern.search("ACME - api"))
        no_case = build(palette=self.PALETTE, ignore_case=False, rules=[{"match": "^acme", "color": 0}])
        self.assertIsNone(no_case.rules[0].pattern.search("ACME - api"))

    def test_rejects_bad_rules_naming_the_rule(self):
        bad_rules = [
            ({"match": "(", "color": 0}, "rule 1"),
            ({"color": 0}, "rule 1.*match"),
            ({"match": "a", "color": 2}, "rule 1.*color"),
            ({"match": "a", "color": True}, "rule 1.*color"),
            ({"match": "a", "color": "red"}, "rule 1.*color"),
            ({"match": "a", "color": 0, "bold": True}, "rule 1.*bold"),
            ("a", "rule 1"),
        ]
        for rule, pattern in bad_rules:
            with self.subTest(rule=rule), self.assertRaisesRegex(ConfigError, pattern):
                self.rules(rule)

    def test_rules_must_be_a_list(self):
        with self.assertRaisesRegex(ConfigError, "rules"):
            build(rules={"match": "a"})

    def test_rejects_more_slots_than_a_sidebar_row_can_hold(self):
        extra = [{"match": str(index), "color": "#0000{:02x}".format(index)} for index in range(SLOT_LIMIT)]

        with self.assertRaisesRegex(ConfigError, "slots"):
            build(palette=self.PALETTE, rules=extra)

    def test_too_many_rule_colors_alone_ask_for_fewer_rule_colors(self):
        extra = [{"match": str(index), "color": "#0000{:02x}".format(index)} for index in range(SLOT_LIMIT)]

        with self.assertRaisesRegex(ConfigError, "fewer distinct rule colours") as raised:
            build(palette=self.PALETTE, rules=extra)
        self.assertNotIn("palette_size to", str(raised.exception))


class LoadConfigTest(unittest.TestCase):
    def test_reads_and_validates_the_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            path.write_text('{"palette": "dracula", "key": "whole"}')

            config = load_config(path)

        self.assertEqual((config.palette_name, config.key_mode), ("dracula", "whole"))

    def test_missing_file_gives_the_defaults(self):
        self.assertEqual(load_config(Path("/nonexistent/config.json")), build())

    def test_the_shipped_example_is_valid(self):
        config = load_config(Path(__file__).resolve().parent / "config.example.json")

        self.assertEqual((config.palette_name, config.auto_sort), ("dracula", "both"))
        self.assertTrue(config.rules)


if __name__ == "__main__":
    unittest.main()
