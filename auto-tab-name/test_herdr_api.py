import io
import json
import os
import socket
import tempfile
import threading
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from unittest import mock

import herdr_api
from herdr_api import (
    ConfigError,
    HerdrError,
    LockTimeout,
    config_path,
    list_workspaces,
    load_json_config,
    notify,
    parent_of,
    plugin_lock,
    report_failure,
    socket_path,
    socket_rpc,
    state_dir,
    worktree_parents,
)


class OneShotServer:
    """A Unix socket server that answers one request line with a canned response."""

    def __init__(self, response):
        self.directory = tempfile.mkdtemp(prefix="ha")
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
            result = socket_rpc(server.path, "tool")("workspace.list", {})
        finally:
            server.close()

        self.assertEqual(result, {"type": "workspace_list", "workspaces": []})
        self.assertEqual(server.request["id"], "tool:workspace.list")
        self.assertEqual(server.request["method"], "workspace.list")
        self.assertEqual(server.request["params"], {})

    def test_raises_on_an_error_response_and_keeps_the_code(self):
        server = OneShotServer({"id": "x", "error": {"code": "workspace_not_found", "message": "no w9"}})
        try:
            with self.assertRaisesRegex(HerdrError, "workspace_not_found: no w9") as raised:
                socket_rpc(server.path, "tool")("workspace.move_block", {"workspace_ids": ["w9"]})
        finally:
            server.close()

        self.assertEqual(raised.exception.code, "workspace_not_found")

    def test_raises_on_a_response_that_is_not_an_object(self):
        server = OneShotServer(["not", "an", "object"])
        try:
            with self.assertRaises(HerdrError):
                socket_rpc(server.path, "tool")("workspace.list", {})
        finally:
            server.close()


class ListWorkspacesTest(unittest.TestCase):
    def test_returns_spaces_without_optional_tokens_or_worktree(self):
        spaces = [{"workspace_id": "w1", "label": "a", "number": 1}]

        self.assertEqual(list_workspaces(lambda method, params: {"workspaces": spaces}), spaces)

    def test_rejects_a_space_without_an_id(self):
        with self.assertRaises(HerdrError):
            list_workspaces(lambda method, params: {"workspaces": [{"label": "a", "number": 1}]})

    def test_rejects_a_result_without_a_list(self):
        with self.assertRaises(HerdrError):
            list_workspaces(lambda method, params: {"type": "oops"})


def ws(workspace_id, label, worktree=None):
    record = {"workspace_id": workspace_id, "label": label, "number": 1}
    if worktree is not None:
        record["worktree"] = worktree
    return record


class WorktreeParentsTest(unittest.TestCase):
    def setUp(self):
        self.parent = ws("p", "ACME - api", {"repo_key": "r", "is_linked_worktree": False})
        self.child = ws("c", "feature-x", {"repo_key": "r", "is_linked_worktree": True})
        self.orphan = ws("o", "lost", {"repo_key": "gone", "is_linked_worktree": True})
        self.parents = worktree_parents([self.parent, self.child, self.orphan, ws("x", "plain")])

    def test_maps_repo_keys_to_their_main_checkout(self):
        self.assertEqual(self.parents, {"r": self.parent})

    def test_linked_worktree_finds_its_parent(self):
        self.assertIs(parent_of(self.child, self.parents), self.parent)

    def test_orphans_and_plain_spaces_have_no_parent(self):
        self.assertIsNone(parent_of(self.orphan, self.parents))
        self.assertIsNone(parent_of(self.parent, self.parents))
        self.assertIsNone(parent_of(ws("x", "plain"), self.parents))


class LoadJsonConfigTest(unittest.TestCase):
    DEFAULTS = {"mode": "off", "count": 3}

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.path = Path(self.directory.name) / "config.json"

    def tearDown(self):
        self.directory.cleanup()

    def test_missing_file_gives_the_defaults(self):
        self.assertEqual(load_json_config(self.path, self.DEFAULTS), self.DEFAULTS)

    def test_file_values_override_the_defaults(self):
        self.path.write_text('{"mode": "both"}')

        self.assertEqual(load_json_config(self.path, self.DEFAULTS), {"mode": "both", "count": 3})

    def test_unknown_key_names_the_file_and_the_key(self):
        self.path.write_text('{"mood": "both"}')

        with self.assertRaisesRegex(ConfigError, r"config\.json.*mood"):
            load_json_config(self.path, self.DEFAULTS)

    def test_invalid_json_names_the_file(self):
        self.path.write_text("{mode: both}")

        with self.assertRaisesRegex(ConfigError, r"config\.json"):
            load_json_config(self.path, self.DEFAULTS)

    def test_top_level_must_be_an_object(self):
        self.path.write_text("[]")

        with self.assertRaisesRegex(ConfigError, "object"):
            load_json_config(self.path, self.DEFAULTS)


class ConfigPathTest(unittest.TestCase):
    def test_explicit_path_wins(self):
        with mock.patch.dict(os.environ, {"HERDR_PLUGIN_CONFIG_DIR": "/plugin/config"}):
            self.assertEqual(config_path("me.tool", "/tmp/x.json"), Path("/tmp/x.json"))

    def test_uses_the_plugin_config_dir_from_herdr(self):
        with mock.patch.dict(os.environ, {"HERDR_PLUGIN_CONFIG_DIR": "/plugin/config"}):
            self.assertEqual(config_path("me.tool", None), Path("/plugin/config/config.json"))

    def test_falls_back_to_herdr_default_config_dir(self):
        with mock.patch.dict(os.environ, {}, clear=True), mock.patch.object(
            herdr_api.Path, "home", return_value=Path("/home/u")
        ):
            self.assertEqual(
                config_path("me.tool", None), Path("/home/u/.config/herdr/plugins/config/me.tool/config.json")
            )

    def test_falls_back_to_the_xdg_config_home_like_herdr(self):
        with mock.patch.dict(os.environ, {"XDG_CONFIG_HOME": "/xdg/config"}, clear=True):
            self.assertEqual(
                config_path("me.tool", None), Path("/xdg/config/herdr/plugins/config/me.tool/config.json")
            )


class SocketPathTest(unittest.TestCase):
    def setUp(self):
        home = mock.patch.object(herdr_api.Path, "home", return_value=Path("/home/u"))
        home.start()
        self.addCleanup(home.stop)

    def test_uses_the_socket_from_herdr(self):
        with mock.patch.dict(os.environ, {"HERDR_SOCKET_PATH": "/run/h.sock", "HERDR_SESSION": "globex"}):
            self.assertEqual(socket_path(), Path("/run/h.sock"))

    def test_falls_back_to_the_default_socket_under_home(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(socket_path(), Path("/home/u/.config/herdr/herdr.sock"))

    def test_follows_the_xdg_config_home_like_herdr(self):
        with mock.patch.dict(os.environ, {"XDG_CONFIG_HOME": "/xdg/config"}, clear=True):
            self.assertEqual(socket_path(), Path("/xdg/config/herdr/herdr.sock"))

    def test_a_named_session_has_its_own_socket(self):
        with mock.patch.dict(os.environ, {"HERDR_SESSION": "globex"}, clear=True):
            self.assertEqual(socket_path(), Path("/home/u/.config/herdr/sessions/globex/herdr.sock"))

    def test_the_session_named_default_is_the_default_socket(self):
        with mock.patch.dict(os.environ, {"HERDR_SESSION": "default"}, clear=True):
            self.assertEqual(socket_path(), Path("/home/u/.config/herdr/herdr.sock"))


class StateDirTest(unittest.TestCase):
    def test_uses_the_plugin_state_dir_from_herdr(self):
        with mock.patch.dict(os.environ, {"HERDR_PLUGIN_STATE_DIR": "/plugin/state"}):
            self.assertEqual(state_dir("me.tool"), Path("/plugin/state"))

    def test_falls_back_to_the_xdg_state_home(self):
        with mock.patch.dict(os.environ, {"XDG_STATE_HOME": "/xdg/state"}, clear=True):
            self.assertEqual(state_dir("me.tool"), Path("/xdg/state/herdr/plugins/me.tool"))

    def test_falls_back_to_local_state_under_home(self):
        with mock.patch.dict(os.environ, {}, clear=True), mock.patch.object(
            herdr_api.Path, "home", return_value=Path("/home/u")
        ):
            self.assertEqual(state_dir("me.tool"), Path("/home/u/.local/state/herdr/plugins/me.tool"))


class PluginLockTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.env = mock.patch.dict(os.environ, {"HERDR_PLUGIN_STATE_DIR": self.directory.name})
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.directory.cleanup()

    def test_second_holder_times_out_while_the_first_holds_the_lock(self):
        with plugin_lock("me.tool", timeout=1):
            with self.assertRaises(LockTimeout):
                with plugin_lock("me.tool", timeout=0.1):
                    pass

    def test_lock_is_free_again_after_release(self):
        with plugin_lock("me.tool", timeout=1):
            pass
        with plugin_lock("me.tool", timeout=0.1):
            pass

    def test_runs_against_different_servers_do_not_block_each_other(self):
        with mock.patch.dict(os.environ, {"HERDR_SOCKET_PATH": "/run/a.sock"}), plugin_lock("me.tool", timeout=1):
            with mock.patch.dict(os.environ, {"HERDR_SOCKET_PATH": "/run/b.sock"}):
                with plugin_lock("me.tool", timeout=0.1):
                    pass

    def test_a_lock_shared_by_all_servers_blocks_across_servers(self):
        with mock.patch.dict(os.environ, {"HERDR_SOCKET_PATH": "/run/a.sock"}):
            with plugin_lock("me.tool", timeout=1, per_server=False):
                with mock.patch.dict(os.environ, {"HERDR_SOCKET_PATH": "/run/b.sock"}):
                    with self.assertRaises(LockTimeout):
                        with plugin_lock("me.tool", timeout=0.1, per_server=False):
                            pass

    def test_different_plugins_do_not_block_each_other(self):
        with plugin_lock("me.one", timeout=1):
            with plugin_lock("me.two", timeout=0.1):
                pass


class ReportFailureTest(unittest.TestCase):
    """Hooks can fire on every focus change, so a lasting failure must not toast each time."""

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.env = mock.patch.dict(os.environ, {"HERDR_PLUGIN_STATE_DIR": self.directory.name})
        self.env.start()
        self.notify = mock.patch.object(herdr_api, "notify").start()
        self.addCleanup(mock.patch.stopall)

    def tearDown(self):
        self.env.stop()
        self.directory.cleanup()

    def fail(self, message, plugin_id="me.tool", now=1000.0):
        with mock.patch.object(herdr_api.time, "time", return_value=now), redirect_stderr(io.StringIO()) as err:
            code = report_failure("tool", "Tool failed", HerdrError(message), plugin_id)
        self.assertIn(message, err.getvalue())
        return code

    def toasts(self):
        return [call_args.args for call_args in self.notify.call_args_list]

    def test_a_hook_toasts_a_failure_once_while_it_repeats(self):
        self.assertEqual(self.fail("boom"), 1)
        self.fail("boom", now=1000.0 + herdr_api.FAILURE_TOAST_QUIET_SECONDS - 1)

        self.assertEqual(self.toasts(), [("Tool failed", "boom")])

    def test_a_different_failure_toasts_again(self):
        self.fail("boom")
        self.fail("bang")

        self.assertEqual(len(self.toasts()), 2)

    def test_the_same_failure_toasts_again_after_the_quiet_period(self):
        self.fail("boom")
        self.fail("boom", now=1000.0 + herdr_api.FAILURE_TOAST_QUIET_SECONDS + 1)

        self.assertEqual(len(self.toasts()), 2)

    def test_a_stamp_from_the_future_does_not_silence_toasts(self):
        self.fail("boom", now=1000.0 + 3 * 3600)
        self.fail("boom", now=1000.0)

        self.assertEqual(len(self.toasts()), 2)

    def test_a_damaged_stamp_is_ignored(self):
        self.fail("boom")
        stamp = Path(self.directory.name) / herdr_api.FAILURE_STAMP_FILE_NAME
        recorded = json.loads(stamp.read_text())
        for content in (json.dumps({**recorded, "at": "soon"}), "[1, 2]", "{oops"):
            with self.subTest(content=content):
                stamp.write_text(content)
                self.fail("boom")
        self.assertEqual(len(self.toasts()), 4)

    def test_manual_runs_always_toast(self):
        self.fail("boom", plugin_id=None)
        self.fail("boom", plugin_id=None)

        self.assertEqual(len(self.toasts()), 2)

    def test_unexpected_errors_name_their_type(self):
        with redirect_stderr(io.StringIO()):
            report_failure("tool", "Tool failed", KeyError("repo_key"))

        self.assertIn("KeyError", self.toasts()[0][1])


class NotifyTest(unittest.TestCase):
    def test_shows_a_herdr_toast_with_an_optional_body(self):
        with mock.patch.object(herdr_api.subprocess, "run") as run, mock.patch.dict(
            os.environ, {"HERDR_BIN_PATH": "/opt/herdr"}
        ):
            notify("Title", "why")

        self.assertEqual(run.call_args.args[0], ["/opt/herdr", "notification", "show", "Title", "--body", "why"])

    def test_a_missing_binary_is_reported_on_stderr_only(self):
        with mock.patch.object(herdr_api.subprocess, "run", side_effect=OSError("no herdr")), redirect_stderr(
            io.StringIO()
        ) as err:
            notify("Title")

        self.assertIn("no herdr", err.getvalue())


if __name__ == "__main__":
    unittest.main()
