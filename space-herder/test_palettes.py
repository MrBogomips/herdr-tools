import re
import unittest

from palettes import DEFAULT_PALETTE, MIN_PRESET_COLORS, PRESETS, normalize_hex, resolve_palette

HEX = re.compile(r"^#[0-9a-f]{6}$")


class PresetsTest(unittest.TestCase):
    def test_ships_the_popular_theme_palettes(self):
        for name in ("dracula", "catppuccin", "tokyo-night", "nord", "gruvbox", "one-dark", "solarized", "kanagawa"):
            self.assertIn(name, PRESETS)
        self.assertIn(DEFAULT_PALETTE, PRESETS)

    def test_themes_with_extra_shades_fill_a_sidebar_row(self):
        for name in ("catppuccin", "github-dark", "gruvbox", "kanagawa", "tokyo-night"):
            with self.subTest(palette=name):
                self.assertEqual(len(PRESETS[name]), 15)
        self.assertEqual(len(PRESETS["dracula"]), 14)

    def test_every_preset_has_enough_distinct_normalized_colors(self):
        for name, colors in PRESETS.items():
            with self.subTest(palette=name):
                self.assertGreaterEqual(len(colors), MIN_PRESET_COLORS)
                self.assertLessEqual(len(colors), 15)
                self.assertEqual(len(set(colors)), len(colors))
                for color in colors:
                    self.assertRegex(color, HEX)


class NormalizeHexTest(unittest.TestCase):
    def test_lowercases_six_digit_colors(self):
        self.assertEqual(normalize_hex("#A1B2C3"), "#a1b2c3")

    def test_expands_three_digit_colors(self):
        self.assertEqual(normalize_hex("#AbC"), "#aabbcc")

    def test_rejects_anything_else(self):
        for value in ("red", "#12345", "123456", "#ggg000", 0xFF0000, None):
            with self.subTest(value=value), self.assertRaises(ValueError):
                normalize_hex(value)


class ResolvePaletteTest(unittest.TestCase):
    def test_preset_names_ignore_case(self):
        self.assertEqual(resolve_palette("Dracula"), PRESETS["dracula"])

    def test_unknown_preset_lists_the_known_ones(self):
        with self.assertRaisesRegex(ValueError, "dracula"):
            resolve_palette("draculaa")

    def test_custom_palette_is_normalized(self):
        self.assertEqual(resolve_palette(["#F00", "#00ff00"]), ("#ff0000", "#00ff00"))

    def test_custom_palette_must_not_be_empty_or_repeat_colors(self):
        for value in ([], ["#f00", "#FF0000"]):
            with self.subTest(value=value), self.assertRaises(ValueError):
                resolve_palette(value)

    def test_rejects_other_types(self):
        with self.assertRaises(ValueError):
            resolve_palette(8)


if __name__ == "__main__":
    unittest.main()
