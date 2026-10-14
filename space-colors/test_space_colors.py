import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

import herdr_api
import space_colors as tool
from herdr_api import HerdrError


class FakeHerdr:
    """Serves workspace.list and applies workspace.report_metadata token patches like the server."""

    def __init__(self, labels):
        self.spaces = [
            {"workspace_id": "w{}".format(number), "label": label, "number": number}
            for number, label in enumerate(labels, 1)
        ]
        self.calls = []

    def __call__(self, method, params):
        self.calls.append((method, params))
        if method == "workspace.list":
            return {"type": "workspace_list", "workspaces": [dict(space) for space in self.spaces]}
        if method == "workspace.report_metadata":
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
        raise AssertionError("unexpected method " + method)

    def reports(self):
        return [params for method, params in self.calls if method == "workspace.report_metadata"]

    def tokens(self):
        return {space["label"]: space.get("tokens", {}) for space in self.spaces}


class MainTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.config = Path(self.directory.name) / "config.json"
        self.config.write_text('{"palette": ["#000001", "#000002", "#000003", "#000004", '
                               '"#000005", "#000006", "#000007", "#000008"]}')
        self.env = mock.patch.dict(
            os.environ, {"HERDR_BIN_PATH": "/opt/herdr", "HERDR_PLUGIN_STATE_DIR": self.directory.name}
        )
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.directory.cleanup()

    def run_main(self, call, *argv):
        with mock.patch.object(tool, "socket_rpc", return_value=call), mock.patch.object(
            herdr_api.subprocess, "run"
        ) as run, redirect_stdout(io.StringIO()) as out, redirect_stderr(io.StringIO()):
            code = tool.main(["--config", str(self.config)] + list(argv))
        toasts = [call_args.args[0][3:] for call_args in run.call_args_list]
        return code, toasts, out.getvalue()

    def test_reconcile_colors_every_space_by_prefix(self):
        herdr = FakeHerdr(["ACME - api", "ACME - web +", "Globex - etl"])

        code, _, _ = self.run_main(herdr)

        self.assertEqual(code, 0)
        self.assertEqual(
            herdr.tokens(),
            {"ACME - api": {"spc0": "▌ACME - api"}, "ACME - web +": {"spc0": "▌ACME - web +"},
             "Globex - etl": {"spc7": "▌Globex - etl"}},
        )
        self.assertEqual({report["source"] for report in herdr.reports()}, {"mrbogomips.space-colors"})
        self.assertTrue(all("ttl_ms" not in report for report in herdr.reports()))

    def test_a_second_run_reports_nothing(self):
        herdr = FakeHerdr(["ACME - api", "Globex - etl"])
        self.run_main(herdr, "reconcile", "--hook")
        herdr.calls.clear()

        self.run_main(herdr, "reconcile", "--hook")

        self.assertEqual([method for method, _ in herdr.calls], ["workspace.list"])

    def test_manual_reconcile_confirms_with_a_toast(self):
        herdr = FakeHerdr(["ACME - api"])

        _, first, _ = self.run_main(herdr, "reconcile")
        _, second, _ = self.run_main(herdr, "reconcile")

        self.assertEqual(first, [["Space colours updated", "--body", "1 space"]])
        self.assertEqual(second, [["Space colours already up to date"]])

    def test_hook_is_silent_on_success(self):
        code, toasts, _ = self.run_main(FakeHerdr(["ACME - api"]), "reconcile", "--hook")

        self.assertEqual((code, toasts), (0, []))

    def test_hook_failure_shows_a_toast(self):
        def failing(method, params):
            raise HerdrError("workspace.list failed: boom")

        code, toasts, _ = self.run_main(failing, "reconcile", "--hook")

        self.assertEqual(code, 1)
        self.assertEqual(toasts, [["Space colours failed", "--body", "workspace.list failed: boom"]])

    def test_a_lasting_hook_failure_toasts_once(self):
        self.config.write_text('{"palette": "nope"}')

        first = self.run_main(FakeHerdr(["ACME - api"]), "reconcile", "--hook")
        second = self.run_main(FakeHerdr(["ACME - api"]), "reconcile", "--hook")

        self.assertEqual((first[0], second[0]), (1, 1))
        self.assertEqual((len(first[1]), len(second[1])), (1, 0))

    def test_bad_config_fails_before_talking_to_herdr(self):
        self.config.write_text('{"palette": "nope"}')
        herdr = FakeHerdr(["ACME - api"])

        code, toasts, _ = self.run_main(herdr, "reconcile", "--hook")

        self.assertEqual((code, herdr.calls), (1, []))
        self.assertIn("config.json", toasts[0][2])

    def test_clear_removes_only_our_tokens(self):
        herdr = FakeHerdr(["ACME - api"])
        herdr.spaces[0]["tokens"] = {"spc3": "▌ACME - api", "jj_status": "clean"}

        code, toasts, _ = self.run_main(herdr, "clear")

        self.assertEqual(code, 0)
        self.assertEqual(herdr.tokens(), {"ACME - api": {"jj_status": "clean"}})
        self.assertEqual(toasts, [["Space colours cleared"]])

    def test_preview_explains_colors_without_writing(self):
        herdr = FakeHerdr(["ACME - api", "Globex - etl"])

        code, toasts, out = self.run_main(herdr, "preview")

        self.assertEqual((code, toasts, herdr.reports()), (0, [], []))
        self.assertRegex(out, r"ACME - api\s+acme\s+spc0\s+#000001\s+hash")
        self.assertRegex(out, r"Globex - etl\s+globex\s+spc7\s+#000008\s+hash")

    def use_sticky(self):
        self.config.write_text('{"assign": "sticky", "palette": ["#000001", "#000002", "#000003", "#000004", '
                               '"#000005", "#000006", "#000007", "#000008"]}')
        return Path(self.directory.name) / "assignments.json"

    def test_sticky_reconcile_separates_clashing_customers_and_remembers_them(self):
        state = self.use_sticky()
        herdr = FakeHerdr(["ACME - api", "Umbrella - x"])

        self.run_main(herdr, "reconcile", "--hook")

        self.assertEqual(herdr.tokens(), {"ACME - api": {"spc0": "▌ACME - api"}, "Umbrella - x": {"spc1": "▌Umbrella - x"}})
        self.assertEqual(set(json.loads(state.read_text())["keys"]), {"acme", "umbrella"})

    def test_sticky_state_is_guarded_by_a_lock_shared_by_all_servers(self):
        self.use_sticky()
        taken = []
        real_lock = tool.plugin_lock

        def recording_lock(plugin_id, **kwargs):
            taken.append(kwargs.get("per_server", True))
            return real_lock(plugin_id, **kwargs)

        with mock.patch.object(tool, "plugin_lock", side_effect=recording_lock):
            self.run_main(FakeHerdr(["ACME - api"]), "reconcile", "--hook")

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


if __name__ == "__main__":
    unittest.main()
