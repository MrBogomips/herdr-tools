import unittest

from config import DEFAULTS, build_config
from keys import color_index, derive_key


def config(**overrides):
    return build_config({**DEFAULTS, **overrides}, "config.json")


class DeriveKeyTest(unittest.TestCase):
    def assert_keys(self, cfg, cases):
        for label, expected in cases.items():
            with self.subTest(label=label):
                self.assertEqual(derive_key(label, cfg), expected)

    def test_prefix_is_the_text_before_the_first_separator(self):
        self.assert_keys(config(), {"ACME - api": "acme", "ACME - api - v2": "acme", "Globex": "globex"})

    def test_suffix_is_the_text_after_the_last_separator(self):
        self.assert_keys(config(key="suffix"), {"api - ACME": "acme", "A - B - C": "c", "Globex": "globex"})

    def test_whole_uses_the_full_name(self):
        self.assert_keys(config(key="whole"), {"ACME - api": "acme - api"})

    def test_an_empty_side_falls_back_to_the_whole_name(self):
        self.assert_keys(config(separator="/"), {"/api": "/api"})
        self.assert_keys(config(separator="/", key="suffix"), {"acme/": "acme/"})

    def test_sort_markers_do_not_change_the_key(self):
        self.assert_keys(
            config(),
            {"ACME +": "acme", "ACME -": "acme", "ACME - api -": "acme", "ACME - api + ": "acme", "C++": "c++"},
        )

    def test_a_lone_marker_is_kept(self):
        self.assert_keys(config(), {"+": "+", "~": "~"})

    def test_whitespace_runs_count_as_one_space(self):
        self.assert_keys(config(), {"  ACME  -  api ": "acme", "ACME\t- api": "acme"})

    def test_case_is_kept_when_ignore_case_is_off(self):
        self.assert_keys(config(ignore_case=False), {"ACME - api": "ACME"})

    def test_composed_and_decomposed_accents_match(self):
        self.assertEqual(derive_key("Café - x", config()), derive_key("Café - y", config()))


class ColorIndexTest(unittest.TestCase):
    def test_is_the_sha256_prefix_modulo_the_palette_size(self):
        # Golden values: changing them recolours every user's spaces.
        cases = {("acme", 8): 0, ("acme", 10): 2, ("globex", 8): 7, ("globex", 10): 9, ("initech", 8): 3, ("~", 10): 1}
        for (key, size), expected in cases.items():
            with self.subTest(key=key, size=size):
                self.assertEqual(color_index(key, size), expected)


if __name__ == "__main__":
    unittest.main()
