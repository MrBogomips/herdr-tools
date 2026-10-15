"""Tests for the configuration menu: scripted answers in, captured lines out."""
import unittest
from typing import List, Optional

from config import FORMATS, SOURCES, Config
from menu import MENU_TITLE, render, run_menu


def drive(answers: List[str], config: Optional[Config] = None):
    """Run the menu with scripted answers; return (result, written lines, prompts)."""
    remaining = list(answers)
    written: List[str] = []
    prompts: List[str] = []

    def read(prompt: str) -> str:
        prompts.append(prompt)
        if not remaining:
            raise AssertionError("menu asked for more input than scripted")
        answer = remaining.pop(0)
        if isinstance(answer, BaseException):
            raise answer
        return answer

    result = run_menu(config or Config(), read, written.append)
    return result, written, prompts


class RenderTest(unittest.TestCase):
    def test_shows_title_and_every_value(self):
        lines = render(Config(depth=3, max_length=0, home_tilde=False, auto_sync=False))
        text = "\n".join(lines)
        self.assertEqual(lines[0], MENU_TITLE)
        for fragment in ("off", "basename", "3", "0", "foreground_cwd", "no"):
            self.assertIn(fragment, text)

    def test_fits_the_popup(self):
        for line in render(Config()):
            self.assertLessEqual(len(line), 60)


class ChoiceTest(unittest.TestCase):
    def test_save_returns_equal_config(self):
        result, _, _ = drive(["s"])
        self.assertEqual(result, Config())

    def test_quit_returns_none(self):
        self.assertIsNone(drive(["q"])[0])

    def test_eof_returns_none(self):
        self.assertIsNone(drive([EOFError()])[0])

    def test_keyboard_interrupt_returns_none(self):
        self.assertIsNone(drive([KeyboardInterrupt()])[0])

    def test_choice_is_trimmed_and_case_insensitive(self):
        result, _, _ = drive([" 1 ", " S "])
        self.assertEqual(result, Config(auto_sync=False))

    def test_unknown_choice_writes_error_and_continues(self):
        result, written, _ = drive(["zzz", "s"])
        self.assertEqual(result, Config())
        self.assertTrue(any("zzz" in line for line in written))

    def test_superscript_digit_is_an_unknown_choice(self):
        result, written, _ = drive(["²", "s"])
        self.assertEqual(result, Config())
        self.assertTrue(any("²" in line for line in written))


class ToggleAndCycleTest(unittest.TestCase):
    def test_toggle_auto_sync(self):
        self.assertFalse(drive(["1", "s"])[0].auto_sync)
        self.assertTrue(drive(["1", "1", "s"])[0].auto_sync)

    def test_toggle_home_tilde(self):
        self.assertFalse(drive(["6", "s"])[0].home_tilde)

    def test_cycle_format_through_all_and_back(self):
        seen = []
        for count in range(1, len(FORMATS) + 1):
            seen.append(drive(["2"] * count + ["s"])[0].format)
        self.assertEqual(seen, list(FORMATS[1:]) + [FORMATS[0]])

    def test_cycle_source_wraps(self):
        self.assertEqual(drive(["5", "s"])[0].source, SOURCES[1])
        self.assertEqual(drive(["5", "5", "s"])[0].source, SOURCES[0])


class NumberPromptTest(unittest.TestCase):
    def test_depth_valid(self):
        self.assertEqual(drive(["3", "4", "s"])[0].depth, 4)

    def test_depth_empty_keeps(self):
        result, written, _ = drive(["3", "", "s"])
        self.assertEqual(result.depth, 2)
        self.assertFalse(any("must" in line for line in written))

    def test_depth_zero_is_rejected(self):
        result, written, _ = drive(["3", "0", "s"])
        self.assertEqual(result.depth, 2)
        self.assertTrue(any("1 or more" in line for line in written))

    def test_depth_not_a_number_is_rejected(self):
        result, written, _ = drive(["3", "abc", "s"])
        self.assertEqual(result.depth, 2)
        self.assertTrue(any("abc" in line for line in written))

    def test_depth_superscript_digit_is_rejected(self):
        result, written, _ = drive(["3", "²", "s"])
        self.assertEqual(result.depth, 2)
        self.assertTrue(any("²" in line for line in written))

    def test_max_length_zero_accepted(self):
        self.assertEqual(drive(["4", "0", "s"])[0].max_length, 0)

    def test_max_length_negative_rejected(self):
        result, written, _ = drive(["4", "-1", "s"])
        self.assertEqual(result.max_length, 24)
        self.assertTrue(any("-1" in line for line in written))

    def test_prompt_names_the_current_value(self):
        _, _, prompts = drive(["3", "", "s"])
        self.assertEqual(prompts[1], "Depth (1 or more, empty keeps 2): ")

    def test_interrupt_inside_a_prompt_returns_none(self):
        self.assertIsNone(drive(["3", KeyboardInterrupt()])[0])


class RerenderTest(unittest.TestCase):
    def test_menu_shows_new_value_after_change(self):
        _, written, _ = drive(["3", "7", "s"])
        renders = [i for i, line in enumerate(written) if line == MENU_TITLE]
        self.assertEqual(len(renders), 2)
        after = "\n".join(written[renders[1]:])
        self.assertIn("7", after)

    def test_input_config_is_not_mutated(self):
        original = Config()
        result, _, _ = drive(["1", "2", "3", "5", "s"], original)
        self.assertEqual(original, Config())
        self.assertNotEqual(result, original)


if __name__ == "__main__":
    unittest.main()
