import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

import coloring
import herdr_api
import space_herder as tool
from herdr_api import HerdrError
from overrides import save_overrides

PALETTE = ["#000001", "#000002", "#000003", "#000004", "#000005", "#000006", "#000007", "#000008"]


def ws(workspace_id, label, number, worktree=None):
    record = {"workspace_id": workspace_id, "label": label, "number": number}
    if worktree is not None:
        record["worktree"] = worktree
    return record


class FakeHerdr:
    """Stands in for the socket: serves workspace.list, applies workspace.report_metadata token
    patches and workspace.move_block like the server.

    `spaces` are labels or `ws()` records. `ignore_moves` answers that many move_block calls with
    the unchanged order (a space was created or closed mid-run); `missing_moves` fails that many
    with workspace_not_found; every method in `failing` fails.
    """

    def __init__(self, spaces, ignore_moves=0, missing_moves=0, failing=()):
        self.spaces = [
            ws("w{}".format(number), space, number) if isinstance(space, str) else dict(space)
            for number, space in enumerate(spaces, 1)
        ]
        self.ignore_moves = ignore_moves
        self.missing_moves = missing_moves
        self.failing = set(failing)
        self.calls = []

    def __call__(self, method, params):
        self.calls.append((method, params))
        if method in self.failing:
            raise HerdrError("{} failed: boom".format(method), "boom")
        if method == "workspace.list":
            return {"type": "workspace_list", "workspaces": [dict(space) for space in self.spaces]}
        if method == "workspace.report_metadata":
            return self.report_metadata(params)
        if method == "workspace.move_block":
            return self.move_block(params)
        raise AssertionError("unexpected method " + method)

    def report_metadata(self, params):
        space = next(space for space in self.spaces if space["workspace_id"] == params["workspace_id"])
        tokens = dict(space.get("tokens") or {})
        for name, value in params["tokens"].items():
            if value:
                tokens[name] = value
            else:
                tokens.pop(name, None)
        if tokens:
            space["tokens"] = tokens
        else:
            space.pop("tokens", None)
        return {"type": "ok"}

    def move_block(self, params):
        if self.missing_moves:
            self.missing_moves -= 1
            raise HerdrError("workspace.move_block failed: workspace_not_found: gone", "workspace_not_found")
        if self.ignore_moves:
            self.ignore_moves -= 1
        else:
            by_id = {space["workspace_id"]: space for space in self.spaces}
            self.spaces = [by_id[workspace_id] for workspace_id in params["workspace_ids"]]
        return {"type": "workspace_list", "workspaces": [dict(space) for space in self.spaces]}

    def methods(self):
        return [method for method, _ in self.calls]

    def reports(self):
        return [params for method, params in self.calls if method == "workspace.report_metadata"]

    def tokens(self):
        return {space["label"]: space.get("tokens", {}) for space in self.spaces}

    def labels(self):
        return [space["label"] for space in self.spaces]


class CliTest(unittest.TestCase):
    """main() runs from detached key bindings and hooks, so failures must reach a Herdr toast."""

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.config = Path(self.directory.name) / "config.json"
        self.configure()
        self.env = mock.patch.dict(
            os.environ, {"HERDR_BIN_PATH": "/opt/herdr", "HERDR_PLUGIN_STATE_DIR": self.directory.name}
        )
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.directory.cleanup()

    def configure(self, **settings):
        self.config.write_text(json.dumps({"palette": PALETTE, **settings}))

    def run_main(self, call, *argv):
        with mock.patch.object(tool, "socket_rpc", return_value=call), mock.patch.object(
            herdr_api.subprocess, "run"
        ) as run, redirect_stdout(io.StringIO()) as out, redirect_stderr(io.StringIO()):
            code = tool.main(["--config", str(self.config)] + list(argv))
        toasts = [call_args.args[0][3:] for call_args in run.call_args_list]
        return code, toasts, out.getvalue()


class RecolorTest(CliTest):
    def test_recolor_colors_every_space_by_prefix(self):
        herdr = FakeHerdr(["ACME - api", "ACME - web +", "Globex - etl"])

        code, _, _ = self.run_main(herdr)

        self.assertEqual(code, 0)
        self.assertEqual(
            herdr.tokens(),
            {"ACME - api": {"spc0": "▌ACME - api"}, "ACME - web +": {"spc0": "▌ACME - web +"},
             "Globex - etl": {"spc7": "▌Globex - etl"}},
        )
        self.assertEqual({report["source"] for report in herdr.reports()}, {"mrbogomips.space-herder"})
        self.assertTrue(all("ttl_ms" not in report for report in herdr.reports()))

    def test_manual_recolor_confirms_with_a_toast(self):
        herdr = FakeHerdr(["ACME - api"])

        _, first, _ = self.run_main(herdr, "recolor")
        _, second, _ = self.run_main(herdr, "recolor")

        self.assertEqual(first, [["Colours updated", "--body", "1 space"]])
        self.assertEqual(second, [["Colours already up to date"]])

    def test_recolor_failure_shows_a_toast(self):
        code, toasts, _ = self.run_main(FakeHerdr([], failing=["workspace.list"]), "recolor")

        self.assertEqual(code, 1)
        self.assertEqual(toasts, [["Colouring failed", "--body", "workspace.list failed: boom"]])

    def test_bad_config_fails_before_talking_to_herdr(self):
        self.config.write_text('{"palette": "nope"}')
        herdr = FakeHerdr(["ACME - api"])

        code, toasts, _ = self.run_main(herdr, "recolor")

        self.assertEqual((code, herdr.calls), (1, []))
        self.assertIn("config.json", toasts[0][2])

    def test_clear_removes_only_our_tokens(self):
        herdr = FakeHerdr(["ACME - api"])
        herdr.spaces[0]["tokens"] = {"spc3": "▌ACME - api", "jj_status": "clean"}

        code, toasts, _ = self.run_main(herdr, "clear")

        self.assertEqual(code, 0)
        self.assertEqual(herdr.tokens(), {"ACME - api": {"jj_status": "clean"}})
        self.assertEqual(toasts, [["Colours cleared"]])

    def test_preview_explains_colors_without_writing(self):
        herdr = FakeHerdr(["ACME - api", "Globex - etl"])

        code, toasts, out = self.run_main(herdr, "preview")

        self.assertEqual((code, toasts, herdr.reports()), (0, [], []))
        self.assertRegex(out, r"ACME - api\s+acme\s+spc0\s+#000001\s+hash")
        self.assertRegex(out, r"Globex - etl\s+globex\s+spc7\s+#000008\s+hash")

    def test_recolor_and_preview_use_the_colours_chosen_in_the_dialog(self):
        save_overrides(Path(self.directory.name) / "overrides.json", {"acme": "#000005"})
        herdr = FakeHerdr(["ACME - api", "Globex - etl"])

        self.run_main(herdr, "hook", "focused")
        _, _, out = self.run_main(herdr, "preview")

        self.assertEqual(herdr.tokens()["ACME - api"], {"spc4": "▌ACME - api"})
        self.assertRegex(out, r"ACME - api\s+acme\s+spc4\s+#000005\s+override")

    def use_sticky(self):
        self.configure(assign="sticky")
        return Path(self.directory.name) / "assignments.json"

    def test_sticky_recolor_separates_clashing_customers_and_remembers_them(self):
        state = self.use_sticky()
        herdr = FakeHerdr(["ACME - api", "Umbrella - x"])

        self.run_main(herdr, "hook", "focused")

        self.assertEqual(herdr.tokens(), {"ACME - api": {"spc0": "▌ACME - api"}, "Umbrella - x": {"spc1": "▌Umbrella - x"}})
        self.assertEqual(set(json.loads(state.read_text())["keys"]), {"acme", "umbrella"})

    def test_sticky_state_is_guarded_by_a_lock_shared_by_all_servers(self):
        self.use_sticky()
        taken = []
        real_lock = coloring.plugin_lock

        def recording_lock(plugin_id, **kwargs):
            taken.append(kwargs.get("per_server", True))
            return real_lock(plugin_id, **kwargs)

        with mock.patch.object(coloring, "plugin_lock", side_effect=recording_lock):
            self.run_main(FakeHerdr(["ACME - api"]), "hook", "focused")

        self.assertEqual(taken, [True, False])

    def test_sticky_preview_writes_no_state(self):
        state = self.use_sticky()

        code, _, out = self.run_main(FakeHerdr(["ACME - api", "Umbrella - x"]), "preview")

        self.assertEqual(code, 0)
        self.assertFalse(state.exists())
        self.assertRegex(out, r"Umbrella - x\s+umbrella\s+spc1\s+#000002\s+sticky")

    def test_snippet_prints_the_sidebar_block_without_herdr(self):
        def unreachable(method, params):
            raise AssertionError("snippet must not call Herdr")

        code, toasts, out = self.run_main(unreachable, "snippet")

        self.assertEqual((code, toasts), (0, []))
        self.assertIn('{ token = "$spc7", fg = "#000008" }', out)

    def test_snippet_write_saves_the_block_next_to_the_config(self):
        code, toasts, _ = self.run_main(FakeHerdr([]), "snippet", "--write")

        target = Path(self.directory.name) / "sidebar-rows.toml"
        self.assertEqual(code, 0)
        self.assertIn("[ui.sidebar.spaces]", target.read_text(encoding="utf-8"))
        self.assertEqual(toasts, [["Sidebar rows written", "--body", str(target)]])

    def test_palettes_lists_the_presets(self):
        code, _, out = self.run_main(FakeHerdr([]), "palettes")

        self.assertEqual(code, 0)
        self.assertIn("dracula", out)
        self.assertIn("#ff79c6", out)


class SortTest(CliTest):
    def unsorted(self):
        return FakeHerdr(["beta", "alpha"])

    def test_sorting_shows_spaces_sorted(self):
        herdr = self.unsorted()

        code, toasts, _ = self.run_main(herdr, "sort")

        self.assertEqual(code, 0)
        self.assertEqual(herdr.labels(), ["alpha", "beta"])
        self.assertEqual(toasts, [["Spaces sorted"]])

    def test_sorted_list_shows_already_sorted(self):
        code, toasts, _ = self.run_main(FakeHerdr(["alpha", "beta"]), "sort")

        self.assertEqual(code, 0)
        self.assertEqual(toasts, [["Spaces already sorted"]])

    def test_manual_sort_ignores_auto_sort(self):
        self.configure(auto_sort="off")
        herdr = self.unsorted()

        self.run_main(herdr, "sort")

        self.assertEqual(herdr.labels(), ["alpha", "beta"])

    def test_herdr_error_shows_failure_toast_with_reason(self):
        code, toasts, _ = self.run_main(FakeHerdr([], failing=["workspace.list"]), "sort")

        self.assertEqual(code, 1)
        self.assertEqual(toasts, [["Space sort failed", "--body", "workspace.list failed: boom"]])

    def test_unexpected_error_still_shows_failure_toast(self):
        def broken(method, params):
            raise KeyError("repo_key")

        code, toasts, _ = self.run_main(broken, "sort")

        self.assertEqual(code, 1)
        self.assertEqual(toasts[0][0], "Space sort failed")
        self.assertIn("KeyError", toasts[0][2])

    def test_dry_run_prints_orders_without_moving_or_toasting(self):
        herdr = self.unsorted()

        code, toasts, out = self.run_main(herdr, "sort", "--dry-run")

        self.assertEqual((code, toasts), (0, []))
        self.assertEqual(herdr.methods(), ["workspace.list"])
        self.assertIn("target:  alpha, beta", out)


class HookTest(CliTest):
    def test_every_hook_recolours_without_a_toast(self):
        for event in tool.HOOK_EVENTS:
            with self.subTest(event=event):
                herdr = FakeHerdr(["ACME - api"])

                code, toasts, _ = self.run_main(herdr, "hook", event)

                self.assertEqual((code, toasts), (0, []))
                self.assertEqual(herdr.tokens(), {"ACME - api": {"spc0": "▌ACME - api"}})

    def test_a_second_run_reports_nothing(self):
        herdr = FakeHerdr(["ACME - api", "Globex - etl"])
        self.run_main(herdr, "hook", "focused")
        herdr.calls.clear()

        self.run_main(herdr, "hook", "focused")

        self.assertEqual(herdr.methods(), ["workspace.list"])

    def test_no_hook_sorts_while_autosort_is_off(self):
        for event in tool.HOOK_EVENTS:
            with self.subTest(event=event):
                herdr = FakeHerdr(["beta", "alpha"])

                self.run_main(herdr, "hook", event)

                self.assertNotIn("workspace.move_block", herdr.methods())

    def test_created_and_renamed_sort_without_a_toast_when_autosort_allows(self):
        self.configure(auto_sort="both")
        for event in ("created", "renamed"):
            with self.subTest(event=event):
                herdr = FakeHerdr(["Globex - etl", "ACME - api"])

                code, toasts, _ = self.run_main(herdr, "hook", event)

                self.assertEqual((code, toasts), (0, []))
                self.assertEqual(herdr.labels(), ["ACME - api", "Globex - etl"])
                self.assertEqual(herdr.tokens()["ACME - api"], {"spc0": "▌ACME - api"})

    def test_autosort_sorts_only_after_the_events_it_names(self):
        self.configure(auto_sort="created")
        herdr = FakeHerdr(["beta", "alpha"])

        self.run_main(herdr, "hook", "renamed")

        self.assertNotIn("workspace.move_block", herdr.methods())

    def test_other_events_never_sort(self):
        self.configure(auto_sort="both")
        for event in ("startup", "focused", "updated"):
            with self.subTest(event=event):
                herdr = FakeHerdr(["beta", "alpha"])

                self.run_main(herdr, "hook", event)

                self.assertNotIn("workspace.move_block", herdr.methods())

    def test_a_colour_failure_still_sorts_and_toasts(self):
        self.configure(auto_sort="both")
        herdr = FakeHerdr(["beta", "alpha"], failing=["workspace.report_metadata"])

        code, toasts, _ = self.run_main(herdr, "hook", "created")

        self.assertEqual(code, 1)
        self.assertEqual(herdr.labels(), ["alpha", "beta"])
        self.assertEqual(toasts, [["Colouring failed", "--body", "workspace.report_metadata failed: boom"]])

    def test_a_sort_failure_still_colours_and_toasts(self):
        self.configure(auto_sort="both")
        herdr = FakeHerdr(["Globex - etl", "ACME - api"], failing=["workspace.move_block"])

        code, toasts, _ = self.run_main(herdr, "hook", "renamed")

        self.assertEqual(code, 1)
        self.assertEqual(herdr.tokens()["ACME - api"], {"spc0": "▌ACME - api"})
        self.assertEqual(toasts, [["Space sort failed", "--body", "workspace.move_block failed: boom"]])

    def test_a_lasting_hook_failure_toasts_once(self):
        herdr = FakeHerdr(["ACME - api"], failing=["workspace.list"])

        first = self.run_main(herdr, "hook", "focused")
        second = self.run_main(herdr, "hook", "focused")

        self.assertEqual((first[0], second[0]), (1, 1))
        self.assertEqual((len(first[1]), len(second[1])), (1, 0))

    def test_bad_config_fails_the_hook_before_talking_to_herdr(self):
        self.configure(auto_sort="sometimes")
        herdr = FakeHerdr(["beta", "alpha"])

        code, toasts, _ = self.run_main(herdr, "hook", "created")

        self.assertEqual((code, herdr.calls), (1, []))
        self.assertEqual(toasts[0][0], "Space Herder failed")
        self.assertIn("config.json", toasts[0][2])

    def test_hook_needs_a_known_event_and_only_hook_takes_one(self):
        for argv in (["hook"], ["hook", "closed"], ["recolor", "created"]):
            with self.subTest(argv=argv), self.assertRaises(SystemExit):
                self.run_main(FakeHerdr([]), *argv)

    def test_options_may_sit_between_the_command_and_its_event(self):
        args = tool.parse_args(["hook", "--config", str(self.config), "created"])

        self.assertEqual((args.command, args.event, args.config), ("hook", "created", str(self.config)))


class ParseArgsTest(unittest.TestCase):
    def test_recolor_is_the_default_command(self):
        self.assertEqual(tool.parse_args([]).command, "recolor")

    def test_each_option_belongs_to_its_command(self):
        for argv in (["hook", "created", "--dry-run"], ["recolor", "--dry-run"], ["sort", "--write"], ["clear", "--write"]):
            with self.subTest(argv=argv), self.assertRaises(SystemExit), redirect_stderr(io.StringIO()):
                tool.parse_args(argv)

    def test_accepts_each_option_with_its_command(self):
        self.assertTrue(tool.parse_args(["sort", "--dry-run"]).dry_run)
        self.assertTrue(tool.parse_args(["snippet", "--write"]).write)


if __name__ == "__main__":
    unittest.main()
