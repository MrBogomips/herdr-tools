import unittest

from dialog_form import initial_form, type_text
from dialog_view import PreviewRow, colour_hint, group_hint, help_line, preview_rows
from test_dialog_form import config, press, setup, ws


class PreviewTest(unittest.TestCase):
    def test_a_new_space_shows_in_its_sorted_place_and_colour(self):
        context = setup()
        form = type_text(press(initial_form(context), context, "tab"), "ACME - api", context)

        rows = preview_rows(form, context)

        self.assertEqual([row.text for row in rows], ["▌~", "▌LUMON +", "▌ACME - api", "▌ACME - web", "▌SYS -"])
        self.assertEqual(rows[2], PreviewRow("▌ACME - api", "#000001", True))
        self.assertEqual(rows[3].colour, "#000001")

    def test_a_chosen_colour_recolours_every_space_of_the_key(self):
        context = setup()
        form = type_text(press(initial_form(context), context, "tab"), "ACME - api", context)
        form = press(form, context, "tab", "tab", "right", "right")

        colours = {row.text: row.colour for row in preview_rows(form, context)}

        self.assertEqual((colours["▌ACME - api"], colours["▌ACME - web"]), ("#000002", "#000002"))

    def test_rename_moves_the_space_to_its_new_group(self):
        context = setup("rename", "w2")
        form = press(initial_form(context), context, "tab", "right", "right")

        rows = preview_rows(form, context)

        self.assertEqual([row.text for row in rows], ["▌~", "▌ACME - web", "▌LUMON -", "▌SYS -"])
        self.assertEqual([row.target for row in rows], [False, False, True, False])

    def test_no_marker_when_the_config_has_none(self):
        context = setup(cfg=config(marker=""))

        self.assertIn("ACME - web", [row.text for row in preview_rows(initial_form(context), context)])


class HintTest(unittest.TestCase):
    def test_group_hint_explains_the_suffix(self):
        context = setup("rename", "w3")
        form = initial_form(context)

        self.assertIn("no suffix", group_hint(form, context))
        self.assertIn('" +"', group_hint(press(form, context, "tab", "left"), context))
        self.assertIn('" -"', group_hint(press(form, context, "tab", "right"), context))
        self.assertIn("always first", group_hint(type_text(press(form, context, "ctrl-u"), "~", context), context))

    def test_colour_hint_names_the_key_as_typed(self):
        context = setup("rename", "w3")
        form = initial_form(context)

        self.assertEqual(colour_hint(form, context), "auto: every ACME space keeps its automatic colour")
        self.assertEqual(
            colour_hint(press(form, context, "tab", "tab", "right"), context),
            "every ACME space takes this colour",
        )

    def test_colour_hint_explains_a_lock(self):
        context = setup("rename", "w2", cfg=config(rules=[{"match": "^lumon", "color": 2}]))

        self.assertEqual(colour_hint(initial_form(context), context), "colour set by rule ^lumon")

    def test_help_follows_the_field(self):
        context = setup()
        form = initial_form(context)

        self.assertIn("Tab complete", help_line(form, context))
        self.assertIn("Enter create", help_line(form, context))
        self.assertIn("←→ group", help_line(press(form, context, "tab", "tab"), context))
        renaming = setup("rename", "w3")
        self.assertIn("Enter rename", help_line(initial_form(renaming), renaming))

    def test_help_line_for_colour(self):
        context = setup()
        form = press(initial_form(context), context, "shift-tab")

        self.assertIn("a auto", help_line(form, context))


if __name__ == "__main__":
    unittest.main()
