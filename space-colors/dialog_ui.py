"""Terminal glue for the dialogs: decode key presses, draw the form, run the raw-mode loop.

`Decoder` and `render` are pure and tested; `run_dialog` only wires them to the popup's terminal.
Herdr popups are truecolor terminals (COLORTERM=truecolor), so swatches use 24-bit colour.
"""
from __future__ import annotations

import codecs
import contextlib
import os
import re
import select
import termios
import textwrap
import tty
from dataclasses import replace
from typing import IO, Iterator, List, Optional, Tuple

from dialog_form import (
    NEW,
    Form,
    Setup,
    colour_lock,
    effective_label,
    effective_name_group,
    folder_choices,
    handle,
    initial_form,
    shown_colour,
)
from dialog_view import colour_hint, group_hint, help_line, preview_rows
from folders import shorten
from groups import CHOOSABLE_GROUPS, HOME, SUFFIXES

BOLD, DIM, REVERSE, RED = "1", "2", "7", "31"
LABEL_WIDTH = 8
SUGGESTION_ROWS = 4
PREVIEW_MIN_WIDTH = 50
PREVIEW_MAX_WIDTH = 36
SEPARATOR = " │ "
ESCAPE_WAIT_SECONDS = 0.05
REDRAW_SECONDS = 0.5
ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")
SEQUENCES = {
    "\x1b[A": "up", "\x1b[B": "down", "\x1b[C": "right", "\x1b[D": "left",
    "\x1bOA": "up", "\x1bOB": "down", "\x1bOC": "right", "\x1bOD": "left",
    "\x1b[Z": "shift-tab",
}
PASTE_START, PASTE_END = "\x1b[200~", "\x1b[201~"
ALT_KEYS = {"\x7f": "ctrl-w", "\x08": "ctrl-w"}
CONTROLS = {
    "\t": "tab", "\r": "enter", "\n": "enter", "\x7f": "backspace", "\x08": "backspace",
    "\x15": "ctrl-u", "\x17": "ctrl-w", "\x03": "esc",
}

Segment = Tuple[str, str]  # (text, SGR parameters or "")
Row = List[Segment]


class Decoder:
    """Turns raw terminal bytes into key names; keeps an unfinished escape sequence for later.

    Option/Alt keys arrive as ESC plus a key: they become "alt-<key>" (Option+Backspace deletes a
    word), never Escape. Pasted text (bracketed paste) is typed as characters, newlines dropped,
    so a pasted path never submits the form.
    """

    def __init__(self) -> None:
        self._utf8 = codecs.getincrementaldecoder("utf-8")(errors="replace")
        self._pending = ""
        self._pasting = False

    def feed(self, data: bytes, final: bool = False) -> List[str]:
        """Key names in `data`; `final` turns a lone trailing ESC into the Escape key."""
        text = self._pending + self._utf8.decode(data)
        keys: List[str] = []
        index = 0
        while index < len(text):
            if self._pasting:
                step = self._paste_step(text, index, keys, final)
            elif text[index] == "\x1b":
                step = self._escape_step(text, index, keys, final)
            else:
                key = CONTROLS.get(text[index], text[index] if text[index].isprintable() else None)
                keys += [key] if key else []
                step = 1
            if step == 0:
                break
            index += step
        self._pending = text[index:]
        return keys

    def _escape_step(self, text: str, index: int, keys: List[str], final: bool) -> int:
        """Decode the escape sequence at `index`; returns its length, 0 to wait for more input."""
        end = _sequence_end(text, index)
        if end is None and not final:
            return 0
        if end is None or end == index + 1:
            keys.append("esc")
            return 1
        sequence = text[index:end]
        if sequence == PASTE_START:
            self._pasting = True
        elif len(sequence) == 2 and sequence[1] not in "[O":
            keys.append(ALT_KEYS.get(sequence[1], "alt-" + sequence[1]))
        elif sequence in SEQUENCES:
            keys.append(SEQUENCES[sequence])
        return end - index

    def _paste_step(self, text: str, index: int, keys: List[str], final: bool) -> int:
        if text.startswith(PASTE_END, index):
            self._pasting = False
            return len(PASTE_END)
        if PASTE_END.startswith(text[index:]) and not final:
            return 0
        if text[index].isprintable():
            keys.append(text[index])
        return 1


def _sequence_end(text: str, start: int) -> Optional[int]:
    """End of the escape sequence at `start` (ESC + one key for Alt); None if incomplete."""
    if start + 1 >= len(text):
        return None
    kind = text[start + 1]
    if kind == "\x1b":
        return start + 1
    if kind == "O":
        return start + 3 if start + 2 < len(text) else None
    if kind != "[":
        return start + 2
    for index in range(start + 2, len(text)):
        if "\x40" <= text[index] <= "\x7e":
            return index + 1
    return None


def visible_width(line: str) -> int:
    return len(ANSI.sub("", line))


def fit(row: Row, width: int) -> str:
    """The row as styled text, cut or padded to exactly `width` columns."""
    out, used = "", 0
    for text, style in row:
        piece = text[: max(0, width - used)]
        if piece:
            out += "\x1b[{}m{}\x1b[0m".format(style, piece) if style else piece
            used += len(piece)
    return out + " " * (width - used)


def foreground(colour: Optional[str]) -> str:
    if not colour:
        return ""
    red, green, blue = (int(colour[index : index + 2], 16) for index in (1, 3, 5))
    return "38;2;{};{};{}".format(red, green, blue)


def render(form: Form, setup: Setup, width: int, height: int) -> List[str]:
    """The whole popup screen, one string per line."""
    preview_width = min(PREVIEW_MAX_WIDTH, width // 3) if width >= PREVIEW_MIN_WIDTH else 0
    left_width = width - preview_width - (len(SEPARATOR) if preview_width else 0)
    body_height = max(0, height - 1)
    left = _form_rows(form, setup, left_width)
    right = _preview_rows(form, setup, preview_width, body_height) if preview_width else []
    lines = []
    for number in range(body_height):
        line = fit(left[number] if number < len(left) else [], left_width)
        if preview_width:
            line += fit([(SEPARATOR, DIM)], len(SEPARATOR)) + fit(right[number] if number < len(right) else [], preview_width)
        lines.append(line)
    return lines + [fit([(help_line(form, setup), DIM)], width)][: max(0, height - body_height)]


def _form_rows(form: Form, setup: Setup, width: int) -> List[Row]:
    target = setup.target()
    title = " New space" if setup.mode == NEW else " Rename space " + (target["label"] if target else "")
    rows: List[Row] = [[(title, BOLD)], []]
    if setup.mode == NEW:
        rows.append(_field("Folder", form, "folder", [(form.folder, "")]))
        if form.field == "folder":
            rows += _suggestion_rows(form, setup)
    rows.append(_field("Name", form, "name", _name_value(form, setup)))
    rows.append(_field("Group", form, "group", _group_value(form, setup)))
    rows.append(_field("Colour", form, "colour", _colour_value(form, setup)))
    rows.append([])
    hints = [(form.message, RED)] if form.message else [(group_hint(form, setup), DIM), (colour_hint(form, setup), DIM)]
    for text, style in hints:
        rows += [[(line, style)] for line in textwrap.wrap(text, max(10, width - 1))]
    return rows


def _field(label: str, form: Form, field: str, value: Row) -> Row:
    focused = form.field == field
    cursor = [("█", "")] if focused and field in ("folder", "name") else []
    return [(label.ljust(LABEL_WIDTH), REVERSE if focused else BOLD), (" ", "")] + value + cursor


def _suggestion_rows(form: Form, setup: Setup) -> List[Row]:
    choices = folder_choices(form, setup)
    start = max(0, form.pick - SUGGESTION_ROWS + 1)
    rows = []
    for index in range(start, min(len(choices), start + SUGGESTION_ROWS)):
        choice = choices[index]
        style = REVERSE if index == form.pick else ""
        rows.append([(" " * (LABEL_WIDTH + 1), ""), (shorten(choice.path, setup.home), style), ("  " + choice.source, DIM)])
    return rows


def _name_value(form: Form, setup: Setup) -> Row:
    label = effective_label(form, setup)
    if not form.name.strip():
        return [("(" + label + ")", DIM)] if label else []
    return [(form.name, "")] + ([("  → " + label, DIM)] if label != form.name.strip() else [])


def _group_value(form: Form, setup: Setup) -> Row:
    group = effective_name_group(form)[1]
    if group == HOME:
        return [("home: always first", DIM)]
    row: Row = []
    for choice in CHOOSABLE_GROUPS:
        mark = "(•)" if choice == group else "( )"
        row += [("{} {}{}".format(mark, choice, SUFFIXES.get(choice, "")), BOLD if choice == group else ""), ("  ", "")]
    return row


def _colour_value(form: Form, setup: Setup) -> Row:
    lock = colour_lock(form, setup)
    if lock:
        return [(lock, DIM)]
    chosen = shown_colour(form, setup)
    row: Row = [("[auto]" if chosen is None else " auto ", BOLD if chosen is None else DIM), (" ", "")]
    for colour in setup.config.palette:
        swatch = "[●]" if colour == chosen else " ● "
        row.append((swatch, foreground(colour)))
    return row


def _preview_rows(form: Form, setup: Setup, width: int, height: int) -> List[Row]:
    rows = preview_rows(form, setup)
    room = max(0, height - 1)
    target = next((index for index, row in enumerate(rows) if row.target), 0)
    start = min(max(0, target - room // 2), max(0, len(rows) - room))
    lines: List[Row] = [[("Sidebar preview", BOLD)]]
    for row in rows[start : start + room]:
        marker = " ◀" if row.target else ""
        text = row.text[: max(0, width - len(marker))]
        style = ";".join(part for part in (foreground(row.colour), BOLD if row.target else "") if part)
        lines.append([(text, style), (marker, BOLD)])
    return lines


@contextlib.contextmanager
def raw_terminal(fd: int, out: IO[str]) -> Iterator[None]:
    """Raw input with bracketed paste, on the alternate screen with a hidden cursor; always restored."""
    saved = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        out.write("\x1b[?1049h\x1b[?25l\x1b[?2004h")
        out.flush()
        yield
    finally:
        out.write("\x1b[?2004l\x1b[?25h\x1b[?1049l")
        out.flush()
        termios.tcsetattr(fd, termios.TCSADRAIN, saved)


def run_dialog(setup: Setup, fd: int, out: IO[str]) -> Form:
    """Show the dialog until Enter (a valid form) or Escape; returns the final form."""
    form = initial_form(setup)
    decoder = Decoder()
    shown: List[str] = []
    with raw_terminal(fd, out):
        while form.result is None:
            # Redraw on input or a resize only; the timeout just catches resizes.
            frame = render(form, setup, *_size(out))
            if frame != shown:
                _draw(out, frame)
                shown = frame
            if not select.select([fd], [], [], REDRAW_SECONDS)[0]:
                continue
            data = os.read(fd, 1024)
            if not data:
                return replace(form, result="cancel")
            keys = decoder.feed(data)
            if not keys and not select.select([fd], [], [], ESCAPE_WAIT_SECONDS)[0]:
                keys = decoder.feed(b"", final=True)
            for key in keys:
                form = handle(form, key, setup)
                if form.result:
                    break
    return form


def _size(out: IO[str]) -> Tuple[int, int]:
    try:
        size = os.get_terminal_size(out.fileno())
        return size.columns, size.lines
    except (OSError, ValueError):
        return 80, 20


def _draw(out: IO[str], lines: List[str]) -> None:
    out.write("\x1b[H" + "\r\n".join(lines) + "\x1b[J")
    out.flush()
