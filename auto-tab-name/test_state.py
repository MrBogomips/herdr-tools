import hashlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from state import TabState, load_states, save_states, state_file

PLUGIN_ID = "mrbogomips.auto-tab-name"


class StateFileTest(unittest.TestCase):
    def setUp(self) -> None:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.dir = directory.name

    def name_for(self, socket: str) -> Path:
        env = {"HERDR_PLUGIN_STATE_DIR": self.dir, "HERDR_SOCKET_PATH": socket}
        with mock.patch.dict(os.environ, env):
            return state_file(PLUGIN_ID)

    def test_lives_in_the_state_dir_with_a_per_server_name(self) -> None:
        path = self.name_for("/run/acme.sock")
        digest = hashlib.sha256("/run/acme.sock".encode()).hexdigest()[:12]
        self.assertEqual(path.parent, Path(self.dir))
        self.assertEqual(path.name, "tabs-{}.json".format(digest))
        self.assertRegex(path.name, r"^tabs-[0-9a-f]{12}\.json$")

    def test_two_servers_get_two_files(self) -> None:
        self.assertNotEqual(self.name_for("/run/acme.sock"), self.name_for("/run/globex.sock"))


class StatesTest(unittest.TestCase):
    def setUp(self) -> None:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.dir = Path(directory.name)
        self.path = self.dir / "tabs.json"

    def write(self, content: object) -> None:
        text = content if isinstance(content, str) else json.dumps(content)
        self.path.write_text(text, encoding="utf-8")

    def assert_damaged(self, content: object) -> None:
        self.write(content)
        states, warning = load_states(self.path)
        self.assertEqual(states, {})
        self.assertIsNotNone(warning)
        self.assertTrue(warning.startswith(str(self.path)), warning)

    def test_missing_file_is_empty_without_warning(self) -> None:
        self.assertEqual(load_states(self.path), ({}, None))

    def test_round_trip(self) -> None:
        states = {
            "wA:t1": TabState(True, "ACME", "ACME", "wA:p1"),
            "wA:t2": TabState(False),
            "wB:t1": TabState(True, written="Globex", seen=None, pane=None),
        }
        save_states(self.path, states)
        self.assertEqual(load_states(self.path), (states, None))

    def test_save_writes_version_and_creates_parents(self) -> None:
        path = self.dir / "deep" / "er" / "tabs.json"
        save_states(path, {"wA:t1": TabState(True, "Initech")})
        data = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(data["version"], 1)
        self.assertEqual(data["tabs"]["wA:t1"]["follow"], True)

    def test_save_leaves_no_temp_file(self) -> None:
        save_states(self.path, {"wA:t1": TabState(True)})
        self.assertEqual(os.listdir(str(self.dir)), ["tabs.json"])

    def test_damaged_files_give_empty_state_and_a_warning(self) -> None:
        entry = {"follow": True}
        cases = {
            "bad json": "{not json",
            "top level list": [],
            "missing tabs": {"version": 1},
            "tabs not an object": {"version": 1, "tabs": []},
            "entry without follow": {"version": 1, "tabs": {"wA:t1": {"written": "ACME"}}},
            "follow not a bool": {"version": 1, "tabs": {"wA:t1": {"follow": 1}}},
            "written a number": {"version": 1, "tabs": {"wA:t1": {"follow": True, "written": 3}}},
            "entry not an object": {"version": 1, "tabs": {"wA:t1": True}},
            "unknown version": {"version": 2, "tabs": {"wA:t1": entry}},
            "no version": {"tabs": {"wA:t1": entry}},
        }
        for label, content in cases.items():
            with self.subTest(label):
                self.assert_damaged(content)

    def test_warning_names_the_reason(self) -> None:
        self.write({"version": 7, "tabs": {}})
        _, warning = load_states(self.path)
        self.assertIn("version", warning)


if __name__ == "__main__":
    unittest.main()
