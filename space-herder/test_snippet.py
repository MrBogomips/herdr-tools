import re
import unittest

from config import DEFAULTS, SLOT_LIMIT, build_config
from snippet import fingerprint, render_rows


def config(**overrides):
    return build_config({**DEFAULTS, **overrides}, "config.json")


class RenderRowsTest(unittest.TestCase):
    def test_golden_output_for_a_small_config(self):
        cfg = config(palette=["#111111", "#222222"], rules=[{"match": "^~$", "color": None}])

        self.assertEqual(
            render_rows(cfg),
            "# Space Herder sidebar rows: palette custom, 3 slots, fingerprint " + fingerprint(cfg) + ".\n"
            "# In Herdr's config.toml, set `rows` of your [ui.sidebar.spaces] table to the value below\n"
            "# (keep its other keys, such as row_gap; add the table if you have none). Two tables with\n"
            "# the same name make the whole config invalid, so run `herdr config check`, then\n"
            "# `herdr server reload-config`. Generate this again after changing the palette or rule colours.\n"
            "[ui.sidebar.spaces]\n"
            "rows = [\n"
            "  [\n"
            '    "state_icon",\n'
            '    { token = "$spc0", fg = "#111111" },\n'
            '    { token = "$spc1", fg = "#222222" },\n'
            '    "$spc2",\n'
            "  ],\n"
            '  ["branch", "git_status"],\n'
            "]\n",
        )

    def test_every_slot_of_a_preset_appears_once_in_order(self):
        cfg = config(palette="dracula")
        rendered = render_rows(cfg)

        tokens = re.findall(r'token = "\$(spc\d+)", fg = "(#[0-9a-f]{6})"', rendered)
        self.assertEqual(tokens, [("spc{}".format(slot), color) for slot, color in enumerate(cfg.palette)])
        self.assertLessEqual(len(tokens) + 1, SLOT_LIMIT + 1)

    def test_fingerprint_changes_with_the_colors(self):
        self.assertNotEqual(fingerprint(config(palette="dracula")), fingerprint(config(palette="nord")))
        self.assertRegex(fingerprint(config()), r"^[0-9a-f]{8}$")


if __name__ == "__main__":
    unittest.main()
