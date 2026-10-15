"""auto-tab-name configuration menu: a line-based screen for a Herdr terminal popup."""
from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any, Callable, List, Optional, Tuple

from config import FORMATS, SOURCES, Config

MENU_TITLE = "Auto Tab Name · configuration"
SAVE_KEY = "s"
QUIT_KEY = "q"
PROMPT = "> "
LABEL_WIDTH = 20
MIN_DEPTH = 1
MIN_MAX_LENGTH = 0

Reader = Callable[[str], str]
Writer = Callable[[str], None]


@dataclass(frozen=True)
class Item:
    """One menu line: `kind` is "bool", "choice" or "int"."""
    label: str
    field: str
    kind: str
    choices: Tuple[Any, ...] = ()
    minimum: int = 0
    words: Tuple[str, str] = ("on", "off")   # shown for True / False
    note: str = ""
    prompt: str = ""                          # int items: what the question calls the value


# One table drives both the rendering and the handling; the position is the menu number.
ITEMS = (
    Item("Auto sync", "auto_sync", "bool"),
    Item("Format", "format", "choice", choices=FORMATS),
    Item("Depth (last_n)", "depth", "int", minimum=MIN_DEPTH, prompt="Depth"),
    Item("Max length", "max_length", "int", minimum=MIN_MAX_LENGTH, note="  (0 = no limit)",
         prompt="Max length"),
    Item("Source", "source", "choice", choices=SOURCES),
    Item("Show ~ for home", "home_tilde", "bool", words=("yes", "no")),
)


def _show(item: Item, value: Any) -> str:
    if item.kind == "bool":
        return item.words[0] if value else item.words[1]
    return str(value)


def render(config: Config) -> List[str]:
    """The menu as lines of at most 60 columns."""
    lines = [MENU_TITLE, ""]
    for number, item in enumerate(ITEMS, 1):
        value = _show(item, getattr(config, item.field))
        lines.append("  {}) {}{}{}".format(number, item.label.ljust(LABEL_WIDTH), value, item.note))
    lines += ["", "  {}) save   {}) quit without saving".format(SAVE_KEY, QUIT_KEY)]
    return lines


def _cycle(item: Item, config: Config) -> Config:
    current = getattr(config, item.field)
    following = item.choices[(item.choices.index(current) + 1) % len(item.choices)]
    return replace(config, **{item.field: following})


def _ask_int(item: Item, config: Config, read: Reader, write: Writer) -> Config:
    current = getattr(config, item.field)
    answer = read("{} ({} or more, empty keeps {}): ".format(item.prompt, item.minimum, current)).strip()
    if not answer:
        return config
    try:
        number = int(answer)
    except ValueError:
        number = None
    if number is None or number < item.minimum:
        write("{} must be a whole number of {} or more, not {!r}.".format(item.prompt, item.minimum, answer))
        return config
    return replace(config, **{item.field: number})


def _edit(item: Item, config: Config, read: Reader, write: Writer) -> Config:
    if item.kind == "bool":
        return replace(config, **{item.field: not getattr(config, item.field)})
    if item.kind == "choice":
        return _cycle(item, config)
    return _ask_int(item, config, read, write)


def _item_for(choice: str) -> Optional[Item]:
    if choice.isdecimal() and 1 <= int(choice) <= len(ITEMS):  # isdigit() lets "²" through to int()
        return ITEMS[int(choice) - 1]
    return None


def run_menu(config: Config, read: Reader, write: Writer) -> Optional[Config]:
    """Edit `config` interactively: the edited copy on save, None on quit or end of input."""
    while True:
        for line in render(config):
            write(line)
        try:
            choice = read(PROMPT).strip().lower()
            item = _item_for(choice)
            if item is not None:
                config = _edit(item, config, read, write)
            elif choice == SAVE_KEY:
                return config
            elif choice == QUIT_KEY:
                return None
            else:
                write("Unknown choice {!r}: pick 1-{}, {} or {}.".format(choice, len(ITEMS), SAVE_KEY, QUIT_KEY))
        except (EOFError, KeyboardInterrupt):
            return None
