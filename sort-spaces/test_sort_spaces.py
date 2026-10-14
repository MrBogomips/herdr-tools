import io
import json
import os
import socket
import tempfile
import threading
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest import mock

import sort_spaces as tool
from sort_spaces import HerdrError, plan_order, socket_rpc, sort_spaces


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
    """Stands in for the socket: serves a workspace list and applies move_block like the server."""

    def __init__(self, spaces, ignore_moves=False):
        self.spaces = list(spaces)
        self.ignore_moves = ignore_moves
        self.calls = []

    def __call__(self, method, params):
        self.calls.append((method, params))
        if method == "workspace.list":
            return {"type": "workspace_list", "workspaces": list(self.spaces)}
        if method == "workspace.move_block":
            if not self.ignore_moves:
                by_id = {space["workspace_id"]: space for space in self.spaces}
                self.spaces = [by_id[workspace_id] for workspace_id in params["workspace_ids"]]
            return {"type": "workspace_list", "workspaces": list(self.spaces)}
        raise AssertionError("unexpected method " + method)


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
        self.assertEqual([method for method, _ in herdr.calls], ["workspace.list"])

    def test_fails_when_server_order_does_not_match(self):
        herdr = FakeHerdr([ws("w1", "beta", 1), ws("w2", "alpha", 2)], ignore_moves=True)

        with self.assertRaises(HerdrError):
            sort_spaces(herdr)


class OneShotServer:
    """A Unix socket server that answers one request line with a canned response."""

    def __init__(self, response):
        self.directory = tempfile.mkdtemp(prefix="ss")
        self.path = os.path.join(self.directory, "s.sock")
        self.request = None
        self.server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.server.bind(self.path)
        self.server.listen(1)
        self.thread = threading.Thread(target=self._serve, args=(response,))
        self.thread.start()

    def _serve(self, response):
        connection, _ = self.server.accept()
        with connection:
            self.request = json.loads(connection.makefile().readline())
            connection.sendall((json.dumps(response) + "\n").encode())

    def close(self):
        self.thread.join(timeout=5)
        self.server.close()
        os.unlink(self.path)
        os.rmdir(self.directory)


class SocketRpcTest(unittest.TestCase):
    def test_sends_one_json_line_and_returns_the_result(self):
        server = OneShotServer({"id": "x", "result": {"type": "workspace_list", "workspaces": []}})
        try:
            result = socket_rpc(server.path)("workspace.list", {})
        finally:
            server.close()

        self.assertEqual(result, {"type": "workspace_list", "workspaces": []})
        self.assertEqual(server.request["method"], "workspace.list")
        self.assertEqual(server.request["params"], {})

    def test_raises_on_an_error_response(self):
        server = OneShotServer({"id": "x", "error": {"code": "workspace_not_found", "message": "no w9"}})
        try:
            with self.assertRaisesRegex(HerdrError, "workspace_not_found: no w9"):
                socket_rpc(server.path)("workspace.move_block", {"workspace_ids": ["w9"]})
        finally:
            server.close()

    def test_raises_on_a_response_that_is_not_an_object(self):
        server = OneShotServer(["not", "an", "object"])
        try:
            with self.assertRaises(HerdrError):
                socket_rpc(server.path)("workspace.list", {})
        finally:
            server.close()


class MainTest(unittest.TestCase):
    """main() runs from a detached key binding, so every outcome must reach a Herdr toast."""

    def run_main(self, call, argv=()):
        with mock.patch.object(tool, "socket_rpc", return_value=call), mock.patch.object(
            tool.subprocess, "run"
        ) as run, mock.patch.dict(os.environ, {"HERDR_BIN_PATH": "/opt/herdr"}), redirect_stdout(
            io.StringIO()
        ) as out, redirect_stderr(io.StringIO()):
            code = tool.main(list(argv))
        toasts = [call_args.args[0] for call_args in run.call_args_list]
        return code, toasts, out.getvalue()

    def test_sorting_shows_spaces_sorted(self):
        code, toasts, _ = self.run_main(FakeHerdr([ws("w1", "beta", 1), ws("w2", "alpha", 2)]))

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
        herdr = FakeHerdr([ws("w1", "beta", 1), ws("w2", "alpha", 2)])

        code, toasts, out = self.run_main(herdr, ["--dry-run"])

        self.assertEqual(code, 0)
        self.assertEqual(toasts, [])
        self.assertEqual([method for method, _ in herdr.calls], ["workspace.list"])
        self.assertIn("target:  alpha, beta", out)


if __name__ == "__main__":
    unittest.main()
