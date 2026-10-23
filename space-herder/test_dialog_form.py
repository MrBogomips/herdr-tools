import unittest
from datetime import date

from config import DEFAULTS, build_config
from dialog_form import Outcome, Setup, colour_lock, effective_label, handle, initial_form, type_text
from folders import Suggestion
from groups import BOTTOM, DEFAULT, HEAD, HOME

PALETTE = ["#000001", "#000002", "#000003", "#000004", "#000005", "#000006", "#000007", "#000008"]
HOME_DIR = "/home/ann"
TREE = {
    "/home/ann": ["git", "Documents"],
    "/home/ann/git": ["acme-api", "acme-web", "globex"],
    "/home/ann/git/acme-api": [],
    "/home/ann/git/acme-web": [],
    "/home/ann/git/globex": [],
    "/home/ann/Documents": [],
}


def config(**overrides):
    return build_config({**DEFAULTS, "palette": PALETTE, **overrides}, "config.json")


def ws(workspace_id, label, number, worktree=None):
    record = {"workspace_id": workspace_id, "label": label, "number": number}
    if worktree is not None:
        record["worktree"] = worktree
    return record


SPACES = (ws("w1", "~", 1), ws("w2", "LUMON +", 2), ws("w3", "ACME - web", 3), ws("w4", "SYS -", 4))


def setup(mode="new", target_id=None, cfg=None, overrides=None, spaces=SPACES, suggestions=()):
    return Setup(
        mode=mode,
        home=HOME_DIR,
        cwd="/home/ann/git/acme-api",
        workspaces=tuple(spaces),
        config=cfg or config(),
        overrides=overrides or {},
        stored={},
        today=date(2026, 10, 23),
        target_id=target_id,
        suggestions=tuple(suggestions),
        list_dirs=lambda path: TREE.get(path.rstrip("/"), []),
        is_dir=lambda path: path.rstrip("/") in TREE,
    )


def press(form, context, *keys):
    for key in keys:
        form = handle(form, key, context)
    return form


class InitialFormTest(unittest.TestCase):
    def test_new_starts_in_the_folder_of_the_focused_pane(self):
        form = initial_form(setup())

        self.assertEqual((form.field, form.folder, form.name, form.group), ("folder", "~/git/acme-api", "", DEFAULT))

    def test_rename_starts_from_the_current_name_and_group(self):
        form = initial_form(setup("rename", "w2"))

        self.assertEqual((form.field, form.name, form.group), ("name", "LUMON", HEAD))


class TypingTest(unittest.TestCase):
    def test_typing_a_name_and_a_suffix_picks_the_group(self):
        context = setup()
        form = type_text(press(initial_form(context), context, "tab"), "Globex -", context)

        self.assertEqual(effective_label(form, context), "Globex -")
        form = press(form, context, "tab")
        self.assertEqual((form.name, form.group, form.field), ("Globex", BOTTOM, "group"))

    def test_a_dash_inside_the_name_is_not_a_suffix_once_typing_goes_on(self):
        context = setup()
        form = type_text(press(initial_form(context), context, "tab"), "ACME - api", context)

        self.assertEqual(effective_label(form, context), "ACME - api")

    def test_group_keys_cycle_and_add_the_suffix(self):
        context = setup()
        form = type_text(press(initial_form(context), context, "tab"), "LAB", context)
        form = press(form, context, "tab", "left")

        self.assertEqual(effective_label(form, context), "LAB +")
        self.assertEqual(effective_label(press(form, context, "right", "right"), context), "LAB -")
        self.assertEqual(effective_label(press(form, context, "+"), context), "LAB +")

    def test_the_home_name_ignores_the_group(self):
        context = setup()
        form = type_text(press(initial_form(context), context, "tab"), "~", context)

        self.assertEqual(effective_label(press(form, context, "tab", "left"), context), "~")
        self.assertEqual(press(form, context, "tab", "left").group, HOME)

    def test_backspace_and_ctrl_keys_edit_the_text(self):
        context = setup("rename", "w3")
        form = initial_form(context)

        self.assertEqual(press(form, context, "backspace").name, "ACME - we")
        self.assertEqual(press(form, context, "ctrl-w").name, "ACME - ")
        self.assertEqual(press(form, context, "ctrl-u").name, "")

    def test_without_a_name_a_new_space_is_named_after_its_folder(self):
        context = setup()

        self.assertEqual(effective_label(initial_form(context), context), "acme-api")
        form = press(initial_form(context), context, "tab", "tab", "left")
        self.assertEqual(effective_label(form, context), "acme-api +")


class FolderTest(unittest.TestCase):
    def test_tab_completes_then_moves_on(self):
        context = setup()
        form = press(initial_form(context), context, "ctrl-u")
        form = type_text(form, "~/git/g", context)

        form = press(form, context, "tab")
        self.assertEqual((form.folder, form.field), ("~/git/globex/", "folder"))
        self.assertEqual(press(form, context, "tab").field, "name")

    def test_an_ambiguous_tab_lists_the_matches_first_then_moves_on(self):
        context = setup()
        form = type_text(press(initial_form(context), context, "ctrl-u"), "~/git/acme-", context)

        form = press(form, context, "tab")
        self.assertEqual((form.folder, form.field, form.candidates), ("~/git/acme-", "folder", ("acme-api", "acme-web")))
        self.assertEqual(press(form, context, "tab").field, "name")

    def test_arrows_pick_a_suggestion_without_refiltering(self):
        suggestions = [Suggestion("/home/ann/git/globex", "recent"), Suggestion("/srv/x", "zoxide")]
        context = setup(suggestions=suggestions)
        form = initial_form(context)

        form = press(form, context, "down")
        self.assertEqual((form.folder, form.pick), ("~/git/globex", 0))
        form = press(form, context, "down")
        self.assertEqual((form.folder, form.pick), ("/srv/x", 1))
        self.assertEqual(press(form, context, "down").pick, 1)
        self.assertEqual(press(form, context, "up", "up").folder, "~/git/acme-api")


class ColourTest(unittest.TestCase):
    def go_to_colour(self, context):
        return press(initial_form(context), context, "shift-tab")

    def test_arrows_walk_auto_then_the_palette(self):
        context = setup()
        form = self.go_to_colour(context)

        self.assertEqual(form.field, "colour")
        self.assertEqual(press(form, context, "right").colour, "#000001")
        self.assertEqual(press(form, context, "left").colour, "#000008")
        self.assertIsNone(press(form, context, "right", "a").colour)
        self.assertTrue(press(form, context, "right", "a").colour_touched)

    def test_rename_starts_from_the_keys_override(self):
        context = setup("rename", "w3", overrides={"acme": "#000004"})

        self.assertEqual(initial_form(context).colour, "#000004")

    def test_a_rule_locks_the_colour(self):
        context = setup(cfg=config(rules=[{"match": "^lumon", "color": 2}]))
        form = type_text(press(initial_form(context), context, "tab"), "Lumon - x", context)
        form = press(form, context, "tab", "tab")

        self.assertEqual(colour_lock(form, context), "colour set by rule ^lumon")
        self.assertIsNone(press(form, context, "right").colour)

    def test_a_worktree_child_follows_its_parent(self):
        spaces = SPACES + (
            ws("p", "ACME - api", 5, {"repo_key": "r", "is_linked_worktree": False}),
            ws("c", "feature", 6, {"repo_key": "r", "is_linked_worktree": True}),
        )
        context = setup("rename", "c", spaces=spaces)

        self.assertEqual(colour_lock(initial_form(context), context), "colour follows its parent ACME - api")


class SubmitTest(unittest.TestCase):
    def test_enter_creates_with_folder_label_and_colour(self):
        context = setup(overrides={"acme": "#000002"})
        form = type_text(press(initial_form(context), context, "tab"), "ACME - api", context)
        form = press(form, context, "shift-tab", "shift-tab", "right", "enter")

        self.assertEqual(form.result, "submit")
        self.assertEqual(
            form.outcome(context),
            Outcome("new", None, "/home/ann/git/acme-api", "ACME - api", "acme", True, "#000003"),
        )

    def test_an_untouched_colour_changes_nothing(self):
        context = setup()
        outcome = press(initial_form(context), context, "enter").outcome(context)

        self.assertEqual((outcome.label, outcome.colour_changed), (None, False))

    def test_a_missing_folder_is_refused(self):
        context = setup()
        form = type_text(press(initial_form(context), context, "ctrl-u"), "~/nope", context)

        form = press(form, context, "enter")
        self.assertEqual((form.result, form.message), (None, "No such folder: ~/nope"))
        self.assertEqual(press(form, context, "backspace").message, "")

    def test_rename_needs_a_name(self):
        context = setup("rename", "w3")
        form = press(initial_form(context), context, "ctrl-u", "enter")

        self.assertEqual((form.result, form.message), (None, "Type a name for the space"))

    def test_rename_outcome(self):
        context = setup("rename", "w3")
        form = press(initial_form(context), context, "tab", "left", "enter")

        self.assertEqual(form.outcome(context), Outcome("rename", "w3", None, "ACME - web +", "acme", False, None))

    def test_escape_cancels(self):
        context = setup()

        self.assertEqual(press(initial_form(context), context, "esc").result, "cancel")


if __name__ == "__main__":
    unittest.main()
