import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

import herdr_api
import space_dialog as tool
from dialog_form import handle, initial_form, type_text
from herdr_api import HerdrError
from overrides import load_overrides, save_overrides
from test_space_colors import FakeHerdr as ColourHerdr

PALETTE = ["#000001", "#000002", "#000003", "#000004", "#000005", "#000006", "#000007", "#000008"]


class FakeHerdr(ColourHerdr):
    """Adds the pane, popup and workspace calls the dialogs make."""

    def __init__(self, labels, cwds=()):
        super().__init__(labels)
        self.cwds = list(cwds)

    def __call__(self, method, params):
        if method == "pane.list":
            self.calls.append((method, params))
            return {"type": "pane_list", "panes": [{"pane_id": "p", "cwd": cwd} for cwd in self.cwds]}
        if method == "plugin.pane.open":
            self.calls.append((method, params))
            return {"type": "ok"}
        if method == "workspace.create":
            self.calls.append((method, params))
            number = len(self.spaces) + 1
            self.spaces.append({"workspace_id": "w{}".format(number), "label": params.get("label") or "folder", "number": number})
            return {"type": "workspace_created"}
        if method == "workspace.rename":
            self.calls.append((method, params))
            next(space for space in self.spaces if space["workspace_id"] == params["workspace_id"])["label"] = params["label"]
            return {"type": "ok"}
        return super().__call__(method, params)

    def methods(self):
        return [method for method, _ in self.calls]


def keys_then(*steps):
    """A stand-in for the terminal loop: presses each key name, types each ("text",), returns the form."""

    def run_dialog(setup, fd, out):
        form = initial_form(setup)
        for step in steps:
            form = type_text(form, step[0], setup) if isinstance(step, tuple) else handle(form, step, setup)
        return form

    return run_dialog


class SpaceDialogTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        root = Path(self.directory.name)
        self.state = root / "state"
        self.folder = root / "projects" / "acme-api"
        self.folder.mkdir(parents=True)
        self.config = root / "config.json"
        self.config.write_text(json.dumps({"palette": PALETTE}))
        self.env = mock.patch.dict(os.environ, {
            "HERDR_BIN_PATH": "/opt/herdr",
            "HERDR_PLUGIN_STATE_DIR": str(self.state),
            "HERDR_WORKSPACE_ID": "w2",
            "HERDR_PLUGIN_CONTEXT_JSON": json.dumps({"workspace_id": "w2", "focused_pane_cwd": str(self.folder)}),
            "SPACE_COLORS_WORKSPACE_ID": "w2",
            "SPACE_COLORS_CWD": str(self.folder),
        })
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.directory.cleanup()

    def run_main(self, call, *argv, dialog=None):
        with mock.patch.object(tool, "socket_rpc", return_value=call), mock.patch.object(
            herdr_api.subprocess, "run"
        ) as run, mock.patch.object(tool, "run_dialog", dialog or keys_then("esc")), mock.patch.object(
            tool, "zoxide_folders", return_value=[]
        ), redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()) as err:
            code = tool.main(list(argv) + ["--config", str(self.config)])
        toasts = [call_args.args[0][3:] for call_args in run.call_args_list]
        return code, toasts, err.getvalue()

    def test_open_starts_the_popup_with_the_context(self):
        herdr = FakeHerdr(["ACME - web"])

        code, toasts, _ = self.run_main(herdr, "open", "rename")

        self.assertEqual((code, toasts), (0, []))
        method, params = herdr.calls[0]
        self.assertEqual(method, "plugin.pane.open")
        self.assertEqual(params["entrypoint"], "rename-space")
        self.assertEqual(params["placement"], "popup")
        self.assertEqual(params["env"], {"SPACE_COLORS_WORKSPACE_ID": "w2", "SPACE_COLORS_CWD": str(self.folder)})

    def test_open_reports_a_busy_herdr(self):
        def busy(method, params):
            raise HerdrError("plugin.pane.open failed: ui_busy: a modal is open", "ui_busy")

        code, toasts, _ = self.run_main(busy, "open", "new")

        self.assertEqual(code, 1)
        self.assertEqual(toasts[0][0], "Space dialog failed")

    def test_new_creates_the_space_remembers_the_folder_and_colours_it(self):
        herdr = FakeHerdr(["~", "ACME - web"], cwds=["/srv/open"])
        dialog = keys_then("tab", ("ACME - api",), "shift-tab", "shift-tab", "right", "right", "enter")

        code, _, _ = self.run_main(herdr, "run", "new", dialog=dialog)

        self.assertEqual(code, 0)
        create = next(params for method, params in herdr.calls if method == "workspace.create")
        self.assertEqual(create, {"cwd": str(self.folder), "label": "ACME - api", "focus": True})
        self.assertEqual(load_overrides(self.state / "overrides.json"), {"acme": "#000002"})
        self.assertEqual(json.loads((self.state / "recent.json").read_text())["folders"], [str(self.folder)])
        self.assertEqual(herdr.tokens()["ACME - api"], {"spc1": "▌ACME - api"})
        self.assertEqual(herdr.tokens()["ACME - web"], {"spc1": "▌ACME - web"})

    def test_new_without_a_name_lets_herdr_name_the_space(self):
        herdr = FakeHerdr(["~"])

        self.run_main(herdr, "run", "new", dialog=keys_then("enter"))

        create = next(params for method, params in herdr.calls if method == "workspace.create")
        self.assertEqual(create, {"cwd": str(self.folder), "focus": True})

    def test_cancel_changes_nothing(self):
        herdr = FakeHerdr(["~", "ACME - web"])

        code, toasts, _ = self.run_main(herdr, "run", "new")

        self.assertEqual((code, toasts), (0, []))
        self.assertNotIn("workspace.create", herdr.methods())
        self.assertFalse((self.state / "overrides.json").exists())

    def test_rename_moves_the_group_and_clears_the_colour(self):
        save_overrides(self.state / "overrides.json", {"acme": "#000005", "globex": "#000003"})
        herdr = FakeHerdr(["~", "ACME - web"])
        dialog = keys_then("tab", "left", "tab", "a", "enter")

        code, _, _ = self.run_main(herdr, "run", "rename", dialog=dialog)

        self.assertEqual(code, 0)
        self.assertIn(("workspace.rename", {"workspace_id": "w2", "label": "ACME - web +"}), herdr.calls)
        self.assertEqual(load_overrides(self.state / "overrides.json"), {"globex": "#000003"})
        self.assertEqual(herdr.tokens()["ACME - web +"], {"spc0": "▌ACME - web +"})

    def test_a_colour_change_alone_recolours_without_renaming(self):
        herdr = FakeHerdr(["~", "ACME - web"])
        dialog = keys_then("shift-tab", "right", "right", "right", "enter")

        self.run_main(herdr, "run", "rename", dialog=dialog)

        self.assertNotIn("workspace.rename", herdr.methods())
        self.assertEqual(herdr.tokens()["ACME - web"], {"spc2": "▌ACME - web"})

    def test_a_failed_create_saves_no_colour(self):
        class Refusing(FakeHerdr):
            def __call__(self, method, params):
                if method == "workspace.create":
                    raise HerdrError("workspace.create failed: no such folder")
                return super().__call__(method, params)

        dialog = keys_then("tab", ("ACME - api",), "shift-tab", "shift-tab", "right", "enter")

        code, toasts, _ = self.run_main(Refusing(["~"]), "run", "new", dialog=dialog)

        self.assertEqual(code, 1)
        self.assertIn("no such folder", toasts[0][2])
        self.assertFalse((self.state / "overrides.json").exists())

    def test_rename_of_a_closed_space_fails_with_a_toast(self):
        herdr = FakeHerdr(["~"])

        code, toasts, _ = self.run_main(herdr, "run", "rename")

        self.assertEqual(code, 1)
        self.assertIn("w2", toasts[0][2])


if __name__ == "__main__":
    unittest.main()
