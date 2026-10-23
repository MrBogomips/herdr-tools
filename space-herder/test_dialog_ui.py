import re
import unittest

from dialog_form import initial_form, type_text
from dialog_ui import Decoder, render, visible_width
from folders import Suggestion
from test_dialog_form import press, setup

ANSI = re.compile(r"\x1b\[[0-9;]*m")


def plain(line):
    return ANSI.sub("", line)


class DecoderTest(unittest.TestCase):
    def test_names_the_keys_the_dialog_uses(self):
        data = b"a\t\x1b[Z\r\x7f\x15\x17\x1b[A\x1b[B\x1b[C\x1b[D\x1bOA\x03"

        self.assertEqual(
            Decoder().feed(data, final=True),
            ["a", "tab", "shift-tab", "enter", "backspace", "ctrl-u", "ctrl-w", "up", "down", "right", "left", "up", "esc"],
        )

    def test_a_lone_escape_waits_for_more_input_unless_final(self):
        decoder = Decoder()

        self.assertEqual(decoder.feed(b"\x1b"), [])
        self.assertEqual(decoder.feed(b"[A"), ["up"])
        self.assertEqual(decoder.feed(b"\x1b", final=True), ["esc"])

    def test_skips_unknown_sequences_and_decodes_split_utf8(self):
        decoder = Decoder()

        self.assertEqual(decoder.feed(b"\x1b[1;2C\xc3"), [])
        self.assertEqual(decoder.feed(b"\xa8"), ["è"])

    def test_option_keys_never_cancel(self):
        self.assertEqual(Decoder().feed(b"\x1bb\x1bf", final=True), ["alt-b", "alt-f"])
        self.assertEqual(Decoder().feed(b"\x1b\x7f", final=True), ["ctrl-w"])
        self.assertEqual(Decoder().feed(b"\x1b\x1b", final=True), ["esc", "esc"])

    def test_pasted_text_is_typed_without_its_newlines(self):
        decoder = Decoder()

        self.assertEqual(decoder.feed(b"\x1b[200~~/git\r\n/x\x1b[20"), ["~", "/", "g", "i", "t", "/", "x"])
        self.assertEqual(decoder.feed(b"1~\r"), ["enter"])


class RenderTest(unittest.TestCase):
    def test_fits_the_popup_and_shows_fields_preview_and_help(self):
        context = setup(suggestions=[Suggestion("/home/ann/git/globex", "recent")])
        form = type_text(press(initial_form(context), context, "tab"), "ACME - api", context)

        lines = render(form, context, 100, 20)
        text = "\n".join(plain(line) for line in lines)

        self.assertLessEqual(len(lines), 20)
        self.assertTrue(all(visible_width(line) <= 100 for line in lines))
        for expected in ("Folder", "~/git/acme-api", "Name", "ACME - api", "Group", "Colour",
                         "Sidebar preview", "▌LUMON +", "◀", "Enter create"):
            self.assertIn(expected, text)

    def test_folder_suggestions_show_while_the_folder_is_focused(self):
        context = setup(suggestions=[Suggestion("/home/ann/git/globex", "recent")])

        text = "\n".join(plain(line) for line in render(initial_form(context), context, 100, 20))

        self.assertIn("~/git/globex", text)
        self.assertIn("recent", text)

    def test_swatches_use_the_palette_colours(self):
        context = setup()

        joined = "".join(render(initial_form(context), context, 100, 20))

        self.assertIn("\x1b[38;2;0;0;1m", joined)

    def test_every_swatch_of_a_full_palette_fits_and_the_pick_stands_out(self):
        from test_dialog_form import config

        palette = ["#0000{:02x}".format(number) for number in range(1, 16)]
        context = setup(cfg=config(palette=palette))
        form = press(initial_form(context), context, "shift-tab", "right", "right")

        colour_line = next(plain(line) for line in render(form, context, 90, 20) if "Colour" in line)

        self.assertEqual(colour_line.count("●") + colour_line.count("◉"), 15)
        self.assertEqual(colour_line.count("◉"), 1)

    def test_the_popup_border_already_names_the_dialog(self):
        context = setup()
        text = "\n".join(plain(line) for line in render(initial_form(context), context, 100, 20))

        self.assertNotIn("New space", text)
        renaming = setup("rename", "w3")
        self.assertIn("current name  ACME - web", "\n".join(
            plain(line) for line in render(initial_form(renaming), renaming, 100, 20)))

    def test_worktree_children_are_indented_under_their_parent(self):
        from test_dialog_form import ws

        spaces = [
            ws("p", "ACME - api", 1, {"repo_key": "r", "is_linked_worktree": False}),
            ws("c", "feature-checkout", 2, {"repo_key": "r", "is_linked_worktree": True}),
        ]
        context = setup(spaces=spaces)

        text = "\n".join(plain(line) for line in render(initial_form(context), context, 100, 20))

        self.assertIn("└ ▌feature-checkout", text)

    def test_an_error_replaces_the_hints(self):
        context = setup()
        form = press(type_text(press(initial_form(context), context, "ctrl-u"), "~/nope", context), context, "enter")

        self.assertIn("No such folder: ~/nope", "\n".join(plain(line) for line in render(form, context, 100, 20)))

    def test_a_tiny_popup_still_renders(self):
        context = setup()

        lines = render(initial_form(context), context, 30, 8)

        self.assertLessEqual(len(lines), 8)
        self.assertTrue(all(visible_width(line) <= 30 for line in lines))

    def test_a_long_sidebar_keeps_the_target_in_view(self):
        from test_dialog_form import ws

        spaces = [ws("w{}".format(number), "Space {:02}".format(number), number) for number in range(40)]
        context = setup(spaces=spaces)
        form = type_text(press(initial_form(context), context, "tab"), "zzz", context)

        text = "\n".join(plain(line) for line in render(form, context, 100, 20))

        self.assertIn("zzz", text)


if __name__ == "__main__":
    unittest.main()
