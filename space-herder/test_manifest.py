"""Sanity checks on herdr-plugin.toml (Python 3.9 has no tomllib, so plain regexes)."""
import json
import os
import re
import subprocess
import sys
import unittest
from pathlib import Path

from space_dialog import ENTRYPOINTS
from space_herder import HOOK_EVENTS, parse_args

HERE = Path(__file__).resolve().parent
MANIFEST = (HERE / "herdr-plugin.toml").read_text(encoding="utf-8")
# Herdr runs the first python3 on its server's PATH: -E ignores the user's PYTHON* variables
# (PYTHONSAFEPATH would hide the plugin's own modules) and -X utf8 keeps the I/O UTF-8 whatever
# the locale.
PYTHON = ["python3", "-E", "-X", "utf8"]
SCRIPT = len(PYTHON)
# The Herdr event each [[events]] hook runs on, and the hook event it hands to space_herder.py.
EVENT_HOOKS = {
    "workspace.created": "created",
    "workspace.renamed": "renamed",
    "pane.focused": "focused",
    "workspace.updated": "updated",
}
ACTIONS = {"sort", "recolor", "snippet", "clear", "new-space", "rename-space"}


def values(key):
    return re.findall(r'^{} = "([^"]*)"'.format(key), MANIFEST, re.MULTILINE)


def commands():
    return [json.loads(line) for line in re.findall(r"^command = (\[.*\])$", MANIFEST, re.MULTILINE)]


class ManifestTest(unittest.TestCase):
    def test_declares_the_required_metadata(self):
        for key in ("id", "name", "version", "min_herdr_version"):
            with self.subTest(key=key):
                self.assertEqual(len(values(key)[:1]), 1)
        self.assertTrue(values("id")[0].startswith("mrbogomips."))
        self.assertRegex(values("version")[0], r"^\d+\.\d+\.\d+$")

    def test_every_command_runs_a_script_of_this_plugin(self):
        self.assertTrue(commands())
        for command in commands():
            with self.subTest(command=command):
                self.assertEqual(command[:SCRIPT], PYTHON)
                self.assertTrue((HERE / command[SCRIPT]).is_file())

    def test_every_script_starts_whatever_the_python_environment(self):
        env = dict(os.environ, PYTHONSAFEPATH="1", LC_ALL="en_US.ISO8859-1", LANG="en_US.ISO8859-1")
        for script in sorted({command[SCRIPT] for command in commands()}):
            with self.subTest(script=script):
                run = subprocess.run([sys.executable] + PYTHON[1:] + [script, "--help"], cwd=HERE, env=env,
                                     stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30)
                self.assertEqual(run.returncode, 0, run.stderr.decode("utf-8", "replace"))

    def test_every_space_herder_command_line_parses(self):
        for command in commands():
            if command[SCRIPT] == "space_herder.py":
                with self.subTest(command=command):
                    parse_args(command[SCRIPT + 1:])

    def test_local_ids_have_no_dots(self):
        local_ids = values("id")[1:]
        self.assertTrue(local_ids)
        for local_id in local_ids:
            self.assertNotIn(".", local_id)

    def test_every_hook_runs_the_hook_command_for_its_event(self):
        events = re.findall(r'^\[\[events\]\]\non = "([^"]+)"\ncommand = (\[.*\])$', MANIFEST, re.MULTILINE)
        startup = re.findall(r"^\[\[startup\]\]\ncommand = (\[.*\])$", MANIFEST, re.MULTILINE)

        self.assertEqual(sorted(on for on, _ in events), sorted(EVENT_HOOKS))
        for on, command in events:
            with self.subTest(on=on):
                self.assertEqual(json.loads(command), PYTHON + ["space_herder.py", "hook", EVENT_HOOKS[on]])
        self.assertEqual([json.loads(command) for command in startup], [PYTHON + ["space_herder.py", "hook", "startup"]])
        self.assertEqual(set(EVENT_HOOKS.values()) | {"startup"}, set(HOOK_EVENTS))

    def test_declares_every_action(self):
        self.assertEqual(set(re.findall(r'^\[\[actions\]\]\nid = "([^"]+)"', MANIFEST, re.MULTILINE)), ACTIONS)

    def test_every_dialog_entrypoint_is_a_popup_pane(self):
        panes = dict(re.findall(r'^\[\[panes\]\]\nid = "([^"]+)"\n(?:.*\n)*?placement = "([^"]+)"', MANIFEST, re.MULTILINE))
        for entrypoint in ENTRYPOINTS.values():
            with self.subTest(entrypoint=entrypoint):
                self.assertEqual(panes.get(entrypoint), "popup")

    def test_the_config_example_is_valid_json(self):
        self.assertIsInstance(json.loads((HERE / "config.example.json").read_text(encoding="utf-8")), dict)


if __name__ == "__main__":
    unittest.main()
