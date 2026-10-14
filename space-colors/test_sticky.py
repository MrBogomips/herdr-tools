import json
import tempfile
import unittest
from collections import Counter
from datetime import date
from pathlib import Path

from herdr_api import ConfigError
from sticky import FORGET_AFTER_DAYS, assign, load_state, save_state

# Eight colours: by hash, acme and umbrella both land on index 0, globex on 7, initech on 3.
PALETTE = ("#000001", "#000002", "#000003", "#000004", "#000005", "#000006", "#000007", "#000008")
TODAY = date(2026, 10, 14)


def entry(color, seen="2026-10-14"):
    return {"color": color, "seen": seen}


class AssignTest(unittest.TestCase):
    def test_a_new_key_takes_its_hash_color_when_it_is_free(self):
        indices, stored = assign(["acme"], PALETTE, {}, TODAY)

        self.assertEqual(indices, {"acme": 0})
        self.assertEqual(stored, {"acme": entry("#000001")})

    def test_a_clashing_new_key_takes_the_next_free_color(self):
        indices, _ = assign(["acme", "umbrella"], PALETTE, {}, TODAY)

        self.assertEqual(indices, {"acme": 0, "umbrella": 1})

    def test_a_known_key_keeps_its_color_and_is_marked_seen(self):
        indices, stored = assign(["globex"], PALETTE, {"globex": entry("#000002", "2026-01-01")}, TODAY)

        self.assertEqual(indices, {"globex": 1})
        self.assertEqual(stored["globex"], entry("#000002"))

    def test_colors_of_closed_customers_are_avoided_while_others_are_free(self):
        indices, stored = assign(["acme"], PALETTE, {"lumon": entry("#000001")}, TODAY)

        self.assertEqual(indices, {"acme": 1})
        self.assertIn("lumon", stored)

    def test_a_color_no_longer_in_the_palette_is_assigned_again(self):
        indices, stored = assign(["acme"], PALETTE, {"acme": entry("#ffffff")}, TODAY)

        self.assertEqual((indices, stored["acme"]["color"]), ({"acme": 0}, "#000001"))

    def test_keys_unseen_for_too_long_are_forgotten(self):
        stored = {
            "stale": entry("#000005", "2026-07-01"),
            "recent": entry("#000006", "2026-09-01"),
        }

        _, kept = assign([], PALETTE, stored, TODAY)

        self.assertEqual(set(kept), {"recent"})
        self.assertGreater((TODAY - date(2026, 7, 1)).days, FORGET_AFTER_DAYS)

    def test_colors_are_shared_evenly_once_they_run_out(self):
        keys = ["k{}".format(number) for number in range(len(PALETTE) + 1)]

        indices, _ = assign(keys, PALETTE, {}, TODAY)

        self.assertEqual(sorted(Counter(indices.values()).values()), [1] * (len(PALETTE) - 1) + [2])

    def test_does_not_change_its_input(self):
        stored = {"globex": entry("#000002", "2026-01-01")}

        assign(["globex", "acme"], PALETTE, stored, TODAY)

        self.assertEqual(stored, {"globex": entry("#000002", "2026-01-01")})


class StateFileTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.path = Path(self.directory.name) / "state" / "assignments.json"

    def tearDown(self):
        self.directory.cleanup()

    def test_a_missing_file_is_an_empty_state(self):
        self.assertEqual(load_state(self.path), {})

    def test_saved_state_loads_back(self):
        save_state(self.path, {"acme": entry("#000001")})

        self.assertEqual(load_state(self.path), {"acme": entry("#000001")})
        self.assertEqual(json.loads(self.path.read_text())["version"], 1)
        self.assertEqual([item.name for item in self.path.parent.iterdir()], ["assignments.json"])

    def test_a_damaged_file_is_an_error_naming_it(self):
        self.path.parent.mkdir(parents=True)
        for content in ("{oops", '{"version": 1, "keys": {"acme": {"color": 3}}}', "[]"):
            with self.subTest(content=content):
                self.path.write_text(content)
                with self.assertRaisesRegex(ConfigError, "assignments.json"):
                    load_state(self.path)


if __name__ == "__main__":
    unittest.main()
