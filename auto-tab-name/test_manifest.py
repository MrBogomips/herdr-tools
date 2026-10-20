"""Sanity checks on herdr-plugin.toml (Python 3.9 has no tomllib, so plain regexes)."""
import json
import re
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
MANIFEST = (HERE / "herdr-plugin.toml").read_text(encoding="utf-8")


def values(key):
    return re.findall(r'^{} = "([^"]*)"'.format(key), MANIFEST, re.MULTILINE)


class ManifestTest(unittest.TestCase):
    def test_declares_the_required_metadata(self):
        for key in ("id", "name", "version", "min_herdr_version"):
            with self.subTest(key=key):
                self.assertEqual(len(values(key)[:1]), 1)
        self.assertTrue(values("id")[0].startswith("mrbogomips."))
        self.assertRegex(values("version")[0], r"^\d+\.\d+\.\d+$")

    def test_every_command_runs_a_script_of_this_plugin(self):
        commands = [json.loads(line) for line in re.findall(r"^command = (\[.*\])$", MANIFEST, re.MULTILINE)]
        self.assertTrue(commands)
        for command in commands:
            with self.subTest(command=command):
                self.assertEqual(command[0], "python3")
                self.assertTrue((HERE / command[1]).is_file())

    def test_local_ids_have_no_dots(self):
        local_ids = values("id")[1:]
        self.assertTrue(local_ids)
        for local_id in local_ids:
            self.assertNotIn(".", local_id)

    def test_an_agent_changing_state_refreshes_the_names(self):
        # An agent that moves to a worktree fires no focus event: its state change is the first hook.
        hooks = {event: json.loads(command) for event, command in
                 re.findall(r'^\[\[events\]\]\non = "([^"]*)"\ncommand = (\[.*\])$', MANIFEST, re.MULTILINE)}
        self.assertEqual(hooks.get("pane.agent_status_changed"),
                         ["python3", "auto_tab_name.py", "reconcile", "--hook"])

    def test_the_config_example_is_valid_json(self):
        self.assertIsInstance(json.loads((HERE / "config.example.json").read_text(encoding="utf-8")), dict)


if __name__ == "__main__":
    unittest.main()
