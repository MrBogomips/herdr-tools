import io
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

import herdr_api
import sort_spaces as tool
from herdr_api import ConfigError, HerdrError
from sort_spaces import autosort_enabled, load_settings, plan_order, sort_spaces


def ws(workspace_id, label, number, worktree=None):
    record = {"workspace_id": workspace_id, "label": label, "number": number}
    if worktree is not None:
        record["worktree"] = worktree
    return record


def worktree(repo_key, linked):
    return {"repo_key": repo_key, "is_linked_worktree": linked}


class PlanOrderTest(unittest.TestCase):
    def test_sorts_labels_ignoring_case(self):
        spaces = [ws("w1", "lumon", 1), ws("w2", "Globex", 2), ws("w3", "acme", 3), ws("w4", "LAB", 4)]

        self.assertEqual(plan_order(spaces), ["w3", "w2", "w4", "w1"])

    def test_pins_home_space_first(self):
        spaces = [ws("w1", "beta", 1), ws("w2", "~", 2), ws("w3", "alpha", 3)]

        self.assertEqual(plan_order(spaces), ["w2", "w3", "w1"])

    def test_keeps_current_order_for_equal_labels(self):
        spaces = [ws("w1", "zeta", 1), ws("w2", "Same", 2), ws("w3", "same", 3)]

        self.assertEqual(plan_order(spaces), ["w2", "w3", "w1"])

    def test_already_sorted_list_is_unchanged(self):
        spaces = [ws("w1", "~", 1), ws("w2", "alpha", 2), ws("w3", "Beta", 3)]

        self.assertEqual(plan_order(spaces), ["w1", "w2", "w3"])

    def test_worktree_children_follow_their_parent(self):
        spaces = [
            ws("w1", "zz-feature", 1, worktree("repo-m", True)),
            ws("w2", "beta", 2),
            ws("w3", "main-repo", 3, worktree("repo-m", False)),
            ws("w4", "aa-fix", 4, worktree("repo-m", True)),
        ]

        self.assertEqual(plan_order(spaces), ["w2", "w3", "w4", "w1"])

    def test_worktree_groups_with_equal_parent_labels_stay_together(self):
        spaces = [
            ws("A", "api", 1, worktree("ra", False)),
            ws("B", "api", 2, worktree("rb", False)),
            ws("a1", "feat-a", 3, worktree("ra", True)),
            ws("b1", "feat-b", 4, worktree("rb", True)),
        ]

        self.assertEqual(plan_order(spaces), ["A", "a1", "B", "b1"])

    def test_worktree_child_stays_under_parent_when_another_space_has_the_same_label(self):
        spaces = [
            ws("P", "Beta", 1, worktree("rp", False)),
            ws("X", "beta", 2),
            ws("c", "child", 3, worktree("rp", True)),
        ]

        self.assertEqual(plan_order(spaces), ["P", "c", "X"])

    def test_suffix_markers_order_head_default_bottom(self):
        spaces = [ws("w1", "SYS -", 1), ws("w2", "beta", 2), ws("w3", "LAB +", 3), ws("w4", "alpha", 4)]

        self.assertEqual(plan_order(spaces), ["w3", "w4", "w2", "w1"])

    def test_sorts_by_name_without_marker_inside_a_group(self):
        spaces = [
            ws("w1", "personal +", 1),
            ws("w2", "b -", 2),
            ws("w3", "LUMON +", 3),
            ws("w4", "A -", 4),
        ]

        self.assertEqual(plan_order(spaces), ["w3", "w1", "w4", "w2"])

    def test_home_space_comes_before_the_head_group(self):
        spaces = [ws("w1", "AAA +", 1), ws("w2", "~", 2)]

        self.assertEqual(plan_order(spaces), ["w2", "w1"])

    def test_marker_needs_a_space_before_it(self):
        spaces = [
            ws("w1", "aa -", 1),
            ws("w2", "C++", 2),
            ws("w3", "b-", 3),
            ws("w4", "ACME - API", 4),
            ws("w5", "+", 5),
        ]

        self.assertEqual(plan_order(spaces), ["w5", "w4", "w3", "w2", "w1"])

    def test_tolerates_whitespace_after_the_marker(self):
        spaces = [ws("w1", "beta", 1), ws("w2", "LAB + ", 2)]

        self.assertEqual(plan_order(spaces), ["w2", "w1"])

    def test_worktree_child_inherits_its_parent_group(self):
        spaces = [
            ws("w1", "alpha", 1),
            ws("w2", "aa-repo -", 2, worktree("rm", False)),
            ws("w3", "aa-child +", 3, worktree("rm", True)),
            ws("w4", "beta", 4),
        ]

        self.assertEqual(plan_order(spaces), ["w1", "w4", "w2", "w3"])

    def test_orphan_worktree_child_sorts_by_its_own_label(self):
        spaces = [ws("w1", "beta", 1), ws("w2", "alpha", 2, worktree("repo-x", True))]

        self.assertEqual(plan_order(spaces), ["w2", "w1"])




class FakeHerdr:
    """Stands in for the socket: serves a workspace list and applies move_block like the server.

    `ignore_moves` answers that many move_block calls with the unchanged order (a space was
    created or closed mid-run); `missing_moves` fails that many with workspace_not_found.
    """

    def __init__(self, spaces, ignore_moves=0, missing_moves=0):
        self.spaces = list(spaces)
        self.ignore_moves = ignore_moves
        self.missing_moves = missing_moves
        self.calls = []

    def __call__(self, method, params):
        self.calls.append((method, params))
        if method == "workspace.list":
            return {"type": "workspace_list", "workspaces": list(self.spaces)}
        if method == "workspace.move_block":
            if self.missing_moves:
                self.missing_moves -= 1
                raise HerdrError("workspace.move_block failed: workspace_not_found: gone", "workspace_not_found")
            if self.ignore_moves:
                self.ignore_moves -= 1
            else:
                by_id = {space["workspace_id"]: space for space in self.spaces}
                self.spaces = [by_id[workspace_id] for workspace_id in params["workspace_ids"]]
            return {"type": "workspace_list", "workspaces": list(self.spaces)}
        raise AssertionError("unexpected method " + method)

    def methods(self):
        return [method for method, _ in self.calls]


class SortSpacesTest(unittest.TestCase):
    def test_moves_all_spaces_as_one_block_in_sorted_order(self):
        herdr = FakeHerdr([ws("w1", "beta", 1), ws("w2", "~", 2), ws("w3", "alpha", 3)])

        changed, labels = sort_spaces(herdr)

        self.assertTrue(changed)
        self.assertEqual(labels, ["~", "alpha", "beta"])
        self.assertEqual(herdr.calls[-1], ("workspace.move_block", {"workspace_ids": ["w2", "w3", "w1"]}))

    def test_skips_the_move_when_already_sorted(self):
        herdr = FakeHerdr([ws("w1", "~", 1), ws("w2", "alpha", 2)])

        changed, labels = sort_spaces(herdr)

        self.assertFalse(changed)
        self.assertEqual(labels, ["~", "alpha"])
        self.assertEqual(herdr.methods(), ["workspace.list"])

    def test_retries_when_the_server_order_does_not_match_once(self):
        herdr = FakeHerdr([ws("w1", "beta", 1), ws("w2", "alpha", 2)], ignore_moves=1)

        changed, labels = sort_spaces(herdr)

        self.assertTrue(changed)
        self.assertEqual(labels, ["alpha", "beta"])
        self.assertEqual(herdr.methods().count("workspace.move_block"), 2)

    def test_retries_when_a_space_disappeared_mid_run(self):
        herdr = FakeHerdr([ws("w1", "beta", 1), ws("w2", "alpha", 2)], missing_moves=1)

        changed, _ = sort_spaces(herdr)

        self.assertTrue(changed)

    def test_fails_when_the_server_order_never_matches(self):
        herdr = FakeHerdr([ws("w1", "beta", 1), ws("w2", "alpha", 2)], ignore_moves=3)

        with self.assertRaises(HerdrError):
            sort_spaces(herdr)

        self.assertEqual(herdr.methods().count("workspace.move_block"), 3)

    def test_other_errors_are_not_retried(self):
        calls = []

        def broken(method, params):
            calls.append(method)
            raise HerdrError("workspace.list failed: boom", "boom")

        with self.assertRaises(HerdrError):
            sort_spaces(broken)

        self.assertEqual(calls, ["workspace.list"])


class AutosortTest(unittest.TestCase):
    def test_each_setting_enables_its_events(self):
        cases = {
            "off": (False, False),
            "created": (True, False),
            "renamed": (False, True),
            "both": (True, True),
        }
        for setting, (on_create, on_rename) in cases.items():
            with self.subTest(setting=setting):
                self.assertEqual(autosort_enabled(setting, "created"), on_create)
                self.assertEqual(autosort_enabled(setting, "renamed"), on_rename)


class LoadSettingsTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.path = Path(self.directory.name) / "config.json"

    def tearDown(self):
        self.directory.cleanup()

    def test_autosort_is_off_without_a_config_file(self):
        self.assertEqual(load_settings(self.path)["auto_sort"], "off")

    def test_reads_the_autosort_setting(self):
        self.path.write_text('{"auto_sort": "both"}')

        self.assertEqual(load_settings(self.path)["auto_sort"], "both")

    def test_rejects_an_unknown_autosort_value(self):
        self.path.write_text('{"auto_sort": "always"}')

        with self.assertRaisesRegex(ConfigError, r"config\.json.*auto_sort.*always"):
            load_settings(self.path)

    def test_rejects_an_autosort_value_that_is_not_text(self):
        self.path.write_text('{"auto_sort": ["created", "renamed"]}')

        with self.assertRaisesRegex(ConfigError, r"config\.json.*auto_sort"):
            load_settings(self.path)


class MainTest(unittest.TestCase):
    """main() runs from detached key bindings and hooks, so failures must reach a Herdr toast."""

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.config = Path(self.directory.name) / "config.json"
        self.env = mock.patch.dict(
            os.environ, {"HERDR_BIN_PATH": "/opt/herdr", "HERDR_PLUGIN_STATE_DIR": self.directory.name}
        )
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.directory.cleanup()

    def run_main(self, call, argv=(), auto_sort=None):
        if auto_sort is not None:
            self.config.write_text('{"auto_sort": "%s"}' % auto_sort)
        with mock.patch.object(tool, "socket_rpc", return_value=call), mock.patch.object(
            herdr_api.subprocess, "run"
        ) as run, redirect_stdout(io.StringIO()) as out, redirect_stderr(io.StringIO()):
            code = tool.main(["--config", str(self.config)] + list(argv))
        toasts = [call_args.args[0] for call_args in run.call_args_list]
        return code, toasts, out.getvalue()

    def unsorted(self):
        return FakeHerdr([ws("w1", "beta", 1), ws("w2", "alpha", 2)])

    def test_sorting_shows_spaces_sorted(self):
        code, toasts, _ = self.run_main(self.unsorted())

        self.assertEqual(code, 0)
        self.assertEqual(toasts, [["/opt/herdr", "notification", "show", "Spaces sorted"]])

    def test_sorted_list_shows_already_sorted(self):
        code, toasts, _ = self.run_main(FakeHerdr([ws("w1", "alpha", 1), ws("w2", "beta", 2)]))

        self.assertEqual(code, 0)
        self.assertEqual(toasts, [["/opt/herdr", "notification", "show", "Spaces already sorted"]])

    def test_herdr_error_shows_failure_toast_with_reason(self):
        def failing(method, params):
            raise HerdrError("workspace.list failed: boom")

        code, toasts, _ = self.run_main(failing)

        self.assertEqual(code, 1)
        self.assertEqual(
            toasts,
            [["/opt/herdr", "notification", "show", "Space sort failed", "--body", "workspace.list failed: boom"]],
        )

    def test_unexpected_error_still_shows_failure_toast(self):
        def broken(method, params):
            raise KeyError("repo_key")

        code, toasts, _ = self.run_main(broken)

        self.assertEqual(code, 1)
        self.assertEqual(toasts[0][:4], ["/opt/herdr", "notification", "show", "Space sort failed"])
        self.assertIn("KeyError", toasts[0][5])

    def test_dry_run_prints_orders_without_moving_or_toasting(self):
        herdr = self.unsorted()

        code, toasts, out = self.run_main(herdr, ["--dry-run"])

        self.assertEqual(code, 0)
        self.assertEqual(toasts, [])
        self.assertEqual(herdr.methods(), ["workspace.list"])
        self.assertIn("target:  alpha, beta", out)

    def test_hook_does_nothing_while_autosort_is_off(self):
        herdr = self.unsorted()

        code, toasts, _ = self.run_main(herdr, ["--hook", "created"])

        self.assertEqual((code, toasts, herdr.calls), (0, [], []))

    def test_hook_for_a_disabled_event_does_nothing(self):
        herdr = self.unsorted()

        code, toasts, _ = self.run_main(herdr, ["--hook", "renamed"], auto_sort="created")

        self.assertEqual((code, toasts, herdr.calls), (0, [], []))

    def test_enabled_hook_sorts_without_a_toast(self):
        herdr = self.unsorted()

        code, toasts, _ = self.run_main(herdr, ["--hook", "renamed"], auto_sort="both")

        self.assertEqual((code, toasts), (0, []))
        self.assertIn("workspace.move_block", herdr.methods())

    def test_hook_failure_shows_a_toast(self):
        def failing(method, params):
            raise HerdrError("workspace.list failed: boom")

        code, toasts, _ = self.run_main(failing, ["--hook", "created"], auto_sort="created")

        self.assertEqual(code, 1)
        self.assertEqual(toasts[0][3], "Space sort failed")

    def test_a_lasting_hook_failure_toasts_once(self):
        def failing(method, params):
            raise HerdrError("workspace.list failed: boom")

        first = self.run_main(failing, ["--hook", "created"], auto_sort="both")
        second = self.run_main(failing, ["--hook", "renamed"])

        self.assertEqual((first[0], second[0]), (1, 1))
        self.assertEqual((len(first[1]), len(second[1])), (1, 0))

    def test_bad_config_shows_a_toast_naming_the_file(self):
        herdr = self.unsorted()

        code, toasts, _ = self.run_main(herdr, ["--hook", "created"], auto_sort="sometimes")

        self.assertEqual(code, 1)
        self.assertEqual(herdr.calls, [])
        self.assertIn("config.json", toasts[0][5])


if __name__ == "__main__":
    unittest.main()
