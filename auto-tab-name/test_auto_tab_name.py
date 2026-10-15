import io
import json
import os
import subprocess
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

import auto_tab_name as tool
import herdr_api
from herdr_api import HerdrError

HOME = "/home/lumon"
POPUP_ARGV = ["/opt/herdr", "plugin", "pane", "open", "--plugin", "mrbogomips.auto-tab-name", "--entrypoint", "configure"]


def tab(tab_id, name=None, number=1, workspace_id="w1"):
    """A Herdr tab; `name` None means nobody named it, so Herdr shows its position."""
    return {"tab_id": tab_id, "workspace_id": workspace_id, "name": name, "number": number, "focused": False}


def pane(pane_id, tab_id, cwd, focused=False, foreground_cwd=None):
    return {"pane_id": pane_id, "tab_id": tab_id, "focused": focused, "cwd": cwd, "foreground_cwd": foreground_cwd or cwd}


class FakeHerdr:
    """Stands in for the socket: serves tabs and panes and applies tab.rename like the server.

    Like Herdr, a tab nobody named is listed with its 1-based position in its workspace as its
    label, while its `number` never changes. `failures` maps a method to the HerdrError it raises.
    """

    def __init__(self, tabs, panes, failures=None):
        self.tabs = [dict(item) for item in tabs]
        self.panes = list(panes)
        self.failures = dict(failures or {})
        self.calls = []

    def __call__(self, method, params):
        self.calls.append((method, params))
        if method in self.failures:
            raise self.failures[method]
        if method == "tab.list":
            return {"type": "tab_list", "tabs": self.listed()}
        if method == "pane.list":
            return {"type": "pane_list", "panes": list(self.panes)}
        if method == "tab.rename":
            for item in self.tabs:
                if item["tab_id"] == params["tab_id"]:
                    item["name"] = params["label"]
                    return {"type": "tab_info", "tab": self.info(params["tab_id"])}
            raise HerdrError("tab.rename failed: tab_not_found: gone", "tab_not_found")
        raise AssertionError("unexpected method " + method)

    def listed(self):
        positions = {}
        listed = []
        for item in self.tabs:
            workspace_id = item["workspace_id"]
            positions[workspace_id] = positions.get(workspace_id, 0) + 1
            info = {key: value for key, value in item.items() if key != "name"}
            info["label"] = item["name"] if item["name"] is not None else str(positions[workspace_id])
            listed.append(info)
        return listed

    def info(self, tab_id):
        return next(item for item in self.listed() if item["tab_id"] == tab_id)

    def close(self, tab_id):
        self.tabs = [item for item in self.tabs if item["tab_id"] != tab_id]
        self.panes = [item for item in self.panes if item["tab_id"] != tab_id]

    def methods(self):
        return [method for method, _ in self.calls]

    def label(self, tab_id):
        return self.info(tab_id)["label"]


def toast(title, body=None):
    return ["/opt/herdr", "notification", "show", title] + (["--body", body] if body else [])


class CliTestCase(unittest.TestCase):
    """main() runs from detached hooks and key bindings, so every outcome must be observable."""

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)
        self.config = self.root / "config.json"
        self.env = mock.patch.dict(
            os.environ,
            {
                "HERDR_BIN_PATH": "/opt/herdr",
                "HERDR_PLUGIN_STATE_DIR": self.directory.name,
                "HERDR_SOCKET_PATH": str(self.root / "herdr.sock"),
            },
        )
        self.env.start()
        os.environ.pop("HERDR_TAB_ID", None)
        os.environ.pop("HERDR_PLUGIN_CONTEXT_JSON", None)
        self.home = mock.patch.object(Path, "home", return_value=Path(HOME))
        self.home.start()
        self.argvs = []

    def tearDown(self):
        self.home.stop()
        self.env.stop()
        self.directory.cleanup()

    def run_main(self, argv, herdr=None, popup=None):
        """Run main(); returns (exit code, toast argv lists, stdout, stderr, socket_rpc mock)."""
        popup = popup or subprocess.CompletedProcess(POPUP_ARGV, 0, "", "")
        argvs = []

        def fake_run(command, *args, **kwargs):
            argvs.append(command)
            if command[1:3] == ["plugin", "pane"]:
                return popup
            return subprocess.CompletedProcess(command, 0, "", "")

        with mock.patch.object(tool, "socket_rpc", return_value=herdr) as rpc, mock.patch.object(
            subprocess, "run", side_effect=fake_run
        ), redirect_stdout(io.StringIO()) as out, redirect_stderr(io.StringIO()) as err:
            code = tool.main(["--config", str(self.config)] + list(argv))
        self.argvs = argvs
        toasts = [command for command in argvs if command[1] == "notification"]
        return code, toasts, out.getvalue(), err.getvalue(), rpc

    def write_config(self, **values):
        self.config.write_text(json.dumps(values))

    def state_files(self):
        return list(self.root.glob("tabs-*.json"))

    def one_tab(self, name=None, cwd="/work/acme"):
        return FakeHerdr([tab("t1", name)], [pane("p1", "t1", cwd, focused=True)])

    def three_tabs_after_closing_the_second(self):
        """Herdr then lists t3 as "2", its position, while its number stays 3."""
        herdr = FakeHerdr(
            [tab("t1", number=1), tab("t2", number=2), tab("t3", number=3)],
            [pane("p1", "t1", "/work/acme"), pane("p2", "t2", "/work/lumon"), pane("p3", "t3", "/work/globex")],
        )
        herdr.close("t2")
        return herdr


class ReconcileHookTest(CliTestCase):
    def test_hook_renames_a_new_tab_without_a_toast(self):
        herdr = self.one_tab()

        code, toasts, out, _, _ = self.run_main(["reconcile", "--hook"], herdr)

        self.assertEqual(code, 0)
        self.assertEqual(toasts, [])
        self.assertEqual(herdr.label("t1"), "acme")
        self.assertIn("renamed t1: 1 -> acme", out)
        self.assertEqual(len(self.state_files()), 1)

    def test_hook_names_a_tab_whose_number_is_not_its_position(self):
        herdr = self.three_tabs_after_closing_the_second()

        code, _, _, _, _ = self.run_main(["reconcile", "--hook"], herdr)

        self.assertEqual(code, 0)
        self.assertEqual((herdr.label("t1"), herdr.label("t3")), ("acme", "globex"))

    def test_second_hook_run_changes_nothing_and_writes_no_state(self):
        herdr = self.one_tab()
        self.run_main(["reconcile", "--hook"], herdr)
        herdr.calls.clear()

        with mock.patch.object(tool, "save_states") as save:
            code, toasts, _, _, _ = self.run_main(["reconcile", "--hook"], herdr)

        self.assertEqual(code, 0)
        self.assertEqual(toasts, [])
        self.assertNotIn("tab.rename", herdr.methods())
        save.assert_not_called()

    def test_hook_with_auto_sync_off_never_opens_the_socket(self):
        self.write_config(auto_sync=False)

        code, toasts, _, _, rpc = self.run_main(["reconcile", "--hook"], self.one_tab())

        self.assertEqual(code, 0)
        self.assertEqual(toasts, [])
        rpc.assert_not_called()
        self.assertEqual(self.state_files(), [])

    def test_hook_failure_toasts_once_then_stays_quiet(self):
        herdr = FakeHerdr([], [], failures={"tab.list": HerdrError("socket gone", "socket")})

        first = self.run_main(["reconcile", "--hook"], herdr)
        second = self.run_main(["reconcile", "--hook"], herdr)

        self.assertEqual((first[0], second[0]), (1, 1))
        self.assertEqual(len(first[1]), 1)
        self.assertEqual(first[1][0][3], "Tab names not updated")
        self.assertEqual(second[1], [])

    def test_direct_reconcile_failure_toasts_every_time(self):
        herdr = FakeHerdr([], [], failures={"tab.list": HerdrError("socket gone", "socket")})

        first = self.run_main(["reconcile"], herdr)
        second = self.run_main(["reconcile"], herdr)

        self.assertEqual((len(first[1]), len(second[1])), (1, 1))

    def test_bad_config_toast_names_the_config_file(self):
        self.config.write_text('{"depth": 0}')

        code, toasts, _, _, _ = self.run_main(["reconcile", "--hook"], self.one_tab())

        self.assertEqual(code, 1)
        self.assertEqual(len(toasts), 1)
        self.assertIn(str(self.config), " ".join(toasts[0]))

    def two_tabs(self):
        return FakeHerdr(
            [tab("t1", number=1), tab("t2", number=2)],
            [pane("p1", "t1", "/work/acme"), pane("p2", "t2", "/work/globex")],
        )

    def test_rename_failure_stops_the_batch_exits_1_toasts_and_saves_no_state(self):
        herdr = self.two_tabs()
        herdr.failures["tab.rename"] = HerdrError("tab.rename failed: boom", "boom")

        code, toasts, _, _, _ = self.run_main(["reconcile", "--hook"], herdr)

        self.assertEqual(code, 1)
        self.assertEqual(len(toasts), 1)
        self.assertEqual(herdr.methods().count("tab.rename"), 1)
        self.assertEqual(self.state_files(), [])

    def test_a_tab_closed_before_its_rename_is_skipped_and_dropped(self):
        herdr = self.two_tabs()

        def closing_t1_first(method, params):
            if method == "tab.rename" and params["tab_id"] == "t1":
                herdr.close("t1")  # closed between tab.list and its rename
            return herdr(method, params)

        code, toasts, out, _, _ = self.run_main(["reconcile", "--hook"], closing_t1_first)

        self.assertEqual((code, toasts), (0, []))
        self.assertEqual(herdr.label("t2"), "globex")
        self.assertIn("skipped t1", out)
        states = json.loads(self.state_files()[0].read_text())["tabs"]
        self.assertEqual(set(states), {"t2"})

    def test_malformed_list_result_is_a_bad_result_failure(self):
        def malformed(method, params):
            return {"type": "tab_list", "tabs": None}

        code, toasts, _, err, _ = self.run_main(["reconcile", "--hook"], malformed)

        self.assertEqual(code, 1)
        self.assertIn("unexpected tab.list result", err)
        self.assertEqual(len(toasts), 1)

    def test_malformed_tab_list_is_a_bad_result_failure(self):
        good = FakeHerdr([tab("t1")], []).info("t1")
        shapes = {
            "missing tab_id": {k: v for k, v in good.items() if k != "tab_id"},
            "missing workspace_id": {k: v for k, v in good.items() if k != "workspace_id"},
            "label not text": dict(good, label=7),
        }
        for name, bad in shapes.items():
            with self.subTest(name):

                def answer(method, params, bad=bad):
                    return {"type": "tab_list", "tabs": [bad]}

                code, _, _, err, _ = self.run_main(["reconcile"], answer)

                self.assertEqual(code, 1)
                self.assertIn("unexpected tab.list result", err)

    def test_malformed_pane_list_is_a_bad_result_failure(self):
        good = pane("p1", "t1", "/work/acme", focused=True)
        shapes = {
            "not a list": None,
            "missing focused": {k: v for k, v in good.items() if k != "focused"},
            "missing pane_id": {k: v for k, v in good.items() if k != "pane_id"},
            "missing tab_id": {k: v for k, v in good.items() if k != "tab_id"},
            "focused not a bool": dict(good, focused="yes"),
            "cwd not text": dict(good, cwd=7),
            "foreground_cwd not text": dict(good, foreground_cwd=["x"]),
        }
        for name, bad in shapes.items():
            with self.subTest(name):
                herdr = self.one_tab()

                def answer(method, params, bad=bad):
                    if method == "pane.list":
                        return {"type": "pane_list", "panes": bad if bad is None else [bad]}
                    return herdr(method, params)

                code, toasts, _, err, _ = self.run_main(["reconcile"], answer)  # unthrottled: every shape toasts

                self.assertEqual(code, 1)
                self.assertIn("unexpected pane.list result", err)
                self.assertIn("unexpected pane.list result", toasts[0][5])

    def test_reconcile_without_hook_honours_auto_sync_off(self):
        self.write_config(auto_sync=False)

        code, toasts, _, _, rpc = self.run_main(["reconcile"], self.one_tab())

        self.assertEqual(code, 0)
        self.assertEqual(toasts, [])
        rpc.assert_not_called()

    def test_damaged_state_file_warns_on_stderr_and_recovers(self):
        herdr = self.one_tab()
        self.run_main(["reconcile", "--hook"], herdr)
        self.state_files()[0].write_text("not json")

        code, _, _, err, _ = self.run_main(["reconcile", "--hook"], herdr)

        self.assertEqual(code, 0)
        self.assertIn("tabs-", err)


class SyncTest(CliTestCase):
    def test_sync_renames_even_with_auto_sync_off_and_toasts(self):
        self.write_config(auto_sync=False)
        herdr = self.one_tab()

        code, toasts, _, _, _ = self.run_main(["sync"], herdr)

        self.assertEqual(code, 0)
        self.assertEqual(herdr.label("t1"), "acme")
        self.assertEqual(toasts, [toast("Tab names synced", "Renamed 1 tab(s)")])

    def test_sync_with_nothing_to_do_says_up_to_date(self):
        herdr = self.one_tab()
        self.run_main(["sync"], herdr)

        _, toasts, _, _, _ = self.run_main(["sync"], herdr)

        self.assertEqual(toasts, [toast("Tab names already up to date")])


class ToggleTest(CliTestCase):
    def test_toggle_off_rewrites_config_and_skips_the_socket(self):
        code, toasts, _, _, rpc = self.run_main(["toggle"], self.one_tab())

        self.assertEqual(code, 0)
        self.assertFalse(json.loads(self.config.read_text())["auto_sync"])
        self.assertEqual(toasts, [toast("Auto tab names off")])
        rpc.assert_not_called()

    def test_toggle_on_reconciles_and_reports_renames(self):
        self.write_config(auto_sync=False)
        herdr = self.one_tab()

        code, toasts, _, _, _ = self.run_main(["toggle"], herdr)

        self.assertEqual(code, 0)
        self.assertTrue(json.loads(self.config.read_text())["auto_sync"])
        self.assertEqual(herdr.label("t1"), "acme")
        self.assertEqual(toasts, [toast("Auto tab names on", "Renamed 1 tab(s)")])

    def test_toggle_on_with_nothing_to_rename_has_no_body(self):
        self.write_config(auto_sync=False)

        _, toasts, _, _, _ = self.run_main(["toggle"], FakeHerdr([], []))

        self.assertEqual(toasts, [toast("Auto tab names on")])

    def test_toggle_with_a_bad_config_fails_and_keeps_the_file(self):
        self.config.write_text('{"format": "nope"}')

        code, toasts, _, _, _ = self.run_main(["toggle"], self.one_tab())

        self.assertEqual(code, 1)
        self.assertEqual(toasts[0][3], "Auto tab names not toggled")
        self.assertEqual(self.config.read_text(), '{"format": "nope"}')

    def test_a_failed_sync_after_turning_on_says_the_switch_holds(self):
        self.write_config(auto_sync=False)
        herdr = FakeHerdr([], [], failures={"tab.list": HerdrError("socket gone", "socket")})

        code, toasts, _, _, _ = self.run_main(["toggle"], herdr)

        self.assertEqual(code, 1)
        self.assertTrue(json.loads(self.config.read_text())["auto_sync"])
        self.assertEqual(toasts, [toast("Auto tab names on; names not updated", "socket gone")])


class FollowTest(CliTestCase):
    def test_follow_renames_a_hand_named_tab_and_toasts(self):
        herdr = self.one_tab(name="Notes")
        os.environ["HERDR_TAB_ID"] = "t1"

        code, toasts, _, _, _ = self.run_main(["follow"], herdr)

        self.assertEqual(code, 0)
        self.assertEqual(herdr.label("t1"), "acme")
        self.assertEqual(toasts, [toast("Tab follows its folder", "acme")])

    def test_unfollow_keeps_the_label_and_hooks_leave_it_alone(self):
        herdr = self.one_tab()
        self.run_main(["reconcile", "--hook"], herdr)
        os.environ["HERDR_TAB_ID"] = "t1"

        code, toasts, _, _, _ = self.run_main(["unfollow"], herdr)
        herdr.panes = [pane("p1", "t1", "/work/globex", focused=True)]
        herdr.calls.clear()
        self.run_main(["reconcile", "--hook"], herdr)

        self.assertEqual(code, 0)
        self.assertEqual(toasts, [toast("Tab name kept", "acme")])
        self.assertEqual(herdr.label("t1"), "acme")
        self.assertNotIn("tab.rename", herdr.methods())
        states = json.loads(self.state_files()[0].read_text())["tabs"]
        self.assertFalse(states["t1"]["follow"])

    def test_follow_and_unfollow_need_a_current_tab(self):
        for command in ("follow", "unfollow"):
            with self.subTest(command=command):
                code, toasts, _, _, _ = self.run_main([command], self.one_tab())

                self.assertEqual(code, 1)
                self.assertEqual(len(toasts), 1)
                self.assertIn("no current tab", toasts[0][5])

    def test_context_json_is_the_fallback_for_the_current_tab(self):
        herdr = self.one_tab(name="Notes")
        os.environ["HERDR_PLUGIN_CONTEXT_JSON"] = json.dumps({"tab_id": "t1"})

        code, _, _, _, _ = self.run_main(["follow"], herdr)

        self.assertEqual(code, 0)
        self.assertEqual(herdr.label("t1"), "acme")

    def test_bad_context_json_is_ignored(self):
        os.environ["HERDR_PLUGIN_CONTEXT_JSON"] = "{nope"

        code, toasts, _, _, _ = self.run_main(["follow"], self.one_tab())

        self.assertEqual(code, 1)
        self.assertIn("no current tab", toasts[0][5])

    def test_unknown_tab_is_a_failure(self):
        os.environ["HERDR_TAB_ID"] = "t9"

        code, toasts, _, _, _ = self.run_main(["follow"], self.one_tab())

        self.assertEqual(code, 1)
        self.assertEqual(toasts[0][3], "Tab not followed")

    def test_a_failed_rename_after_following_says_the_tab_follows(self):
        herdr = self.one_tab(name="Notes")
        herdr.failures["tab.rename"] = HerdrError("tab.rename failed: boom", "boom")
        os.environ["HERDR_TAB_ID"] = "t1"

        code, toasts, _, _, _ = self.run_main(["follow"], herdr)

        self.assertEqual(code, 1)
        self.assertEqual(toasts, [toast("Tab followed; name not updated", "tab.rename failed: boom")])
        states = json.loads(self.state_files()[0].read_text())["tabs"]
        self.assertTrue(states["t1"]["follow"])

    def test_follow_with_auto_sync_off_renames_only_that_tab(self):
        self.write_config(auto_sync=False)
        herdr = FakeHerdr(
            [tab("t1", "Notes", 1), tab("t2", number=2)],
            [pane("p1", "t1", "/work/acme"), pane("p2", "t2", "/work/globex")],
        )
        os.environ["HERDR_TAB_ID"] = "t1"

        self.run_main(["follow"], herdr)

        self.assertEqual(herdr.label("t1"), "acme")
        self.assertEqual(herdr.label("t2"), "2")

    def test_unfollow_pins_an_automatic_tab_against_position_shifts(self):
        herdr = self.three_tabs_after_closing_the_second()
        os.environ["HERDR_TAB_ID"] = "t3"

        code, toasts, _, _, _ = self.run_main(["unfollow"], herdr)

        self.assertEqual(code, 0)
        self.assertIn(("tab.rename", {"tab_id": "t3", "label": "2"}), herdr.calls)
        self.assertEqual(toasts, [toast("Tab name kept", "2")])

        herdr.close("t1")  # t3 moves to position 1 and keeps the pinned "2"
        herdr.calls.clear()
        self.run_main(["reconcile", "--hook"], herdr)

        self.assertNotIn("tab.rename", herdr.methods())
        self.assertEqual(herdr.label("t3"), "2")
        states = json.loads(self.state_files()[0].read_text())["tabs"]
        self.assertFalse(states["t3"]["follow"])


class ConfigureTest(CliTestCase):
    def test_success_opens_the_popup_without_a_toast(self):
        code, toasts, _, _, rpc = self.run_main(["configure"])

        self.assertEqual(code, 0)
        self.assertEqual(toasts, [])
        self.assertEqual(self.argvs, [POPUP_ARGV])
        rpc.assert_not_called()

    def test_failures_toast_the_reason_and_the_config_path(self):
        error = json.dumps({"error": {"code": "plugin_not_found", "message": "no such plugin"}})
        cases = {
            "error on stderr": (1, "", error + "\n", "no such plugin"),
            "error on stdout": (1, error, "", "no such plugin"),
            "error with status 0": (0, json.dumps({"error": {"message": "nope"}}), "", "nope"),
            "error without a message": (1, "", '{"error": "denied"}', '{"error": "denied"}'),
            "plain text": (2, "", "boom\n", "herdr exited with status 2: boom"),
            "no output": (2, "", "", "herdr exited with status 2"),
        }
        for name, (status, stdout, stderr, reason) in cases.items():
            with self.subTest(name):
                popup = subprocess.CompletedProcess(POPUP_ARGV, status, stdout, stderr)

                code, toasts, _, _, _ = self.run_main(["configure"], popup=popup)

                self.assertEqual(code, 1)
                self.assertEqual(toasts[0][3], "Configuration popup not opened")
                self.assertEqual(toasts[0][5], "{}; edit {} instead".format(reason, self.config))

    def test_a_timeout_toasts_naming_the_config_path(self):
        with mock.patch.object(subprocess, "run", side_effect=subprocess.TimeoutExpired(POPUP_ARGV, 5)):
            with mock.patch.object(herdr_api, "notify") as notify, redirect_stderr(io.StringIO()):
                code = tool.main(["--config", str(self.config), "configure"])

        self.assertEqual(code, 1)
        self.assertIn(str(self.config), notify.call_args.args[1])


class MenuTest(CliTestCase):
    def run_menu(self, answers, herdr=None):
        with mock.patch("builtins.input", side_effect=answers):
            return self.run_main(["menu"], herdr)

    def test_saving_writes_the_edited_config(self):
        code, toasts, _, _, _ = self.run_menu(["1", "s"], FakeHerdr([], []))

        self.assertEqual(code, 0)
        self.assertFalse(json.loads(self.config.read_text())["auto_sync"])
        self.assertEqual(toasts, [toast("Auto tab name settings saved")])

    def test_saving_with_auto_sync_on_reconciles(self):
        self.write_config(format="repo", auto_sync=True)
        herdr = self.one_tab()

        code, toasts, _, _, _ = self.run_menu(["s"], herdr)

        self.assertEqual(code, 0)
        self.assertEqual(herdr.label("t1"), "acme")
        self.assertEqual(toasts, [toast("Auto tab name settings saved", "Renamed 1 tab(s)")])

    def test_quitting_leaves_the_file_untouched(self):
        code, toasts, _, _, _ = self.run_menu(["1", "q"])

        self.assertEqual(code, 0)
        self.assertEqual(toasts, [])
        self.assertFalse(self.config.exists())

    def test_bad_config_waits_for_enter_and_exits_1(self):
        self.config.write_text('{"depth": 0}')

        code, _, out, _, _ = self.run_menu([""])

        self.assertEqual(code, 1)
        self.assertIn(str(self.config), out)

    def test_bad_config_survives_end_of_input(self):
        self.config.write_text('{"depth": 0}')

        code, _, _, _, _ = self.run_menu(EOFError())

        self.assertEqual(code, 1)

    def test_a_failed_sync_after_saving_says_the_settings_are_saved(self):
        self.write_config(auto_sync=True)
        herdr = FakeHerdr([], [], failures={"tab.list": HerdrError("socket gone", "socket")})

        code, toasts, _, _, _ = self.run_menu(["4", "30", "s"], herdr)

        self.assertEqual(code, 1)
        self.assertEqual(json.loads(self.config.read_text())["max_length"], 30)
        self.assertEqual(toasts, [toast("Settings saved; names not updated", "socket gone")])

    def test_ctrl_c_closes_the_popup_quietly(self):
        cases = {
            "at the bad config wait": ('{"depth": 0}', KeyboardInterrupt(), 1),
            "at a menu prompt": ("{}", ["4", KeyboardInterrupt()], 0),
        }
        for name, (content, answers, expected) in cases.items():
            with self.subTest(name):
                self.config.write_text(content)

                code, toasts, _, err, _ = self.run_menu(answers)

                self.assertEqual((code, toasts, err), (expected, [], ""))

    def test_ctrl_c_while_saving_closes_the_popup_quietly(self):
        with mock.patch.object(tool, "reconcile_locked", side_effect=KeyboardInterrupt):
            code, toasts, _, err, _ = self.run_menu(["s"], self.one_tab())

        self.assertEqual((code, toasts, err), (0, [], ""))


if __name__ == "__main__":
    unittest.main()
