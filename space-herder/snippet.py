"""Render the [ui.sidebar.spaces] block that gives each colour slot its foreground.

Herdr keeps token styling in the user's config.toml and only values come from plugins, so the
colours live in this generated block. It replaces the built-in `workspace` token with the slot
tokens; a space shows exactly one of them.
"""
from __future__ import annotations

import hashlib
from typing import List

from config import Config
from plan import token_name

HEADER = (
    "# Space Herder sidebar rows: palette {palette}, {count} slots, fingerprint {fingerprint}.\n"
    "# In Herdr's config.toml, set `rows` of your [ui.sidebar.spaces] table to the value below\n"
    "# (keep its other keys, such as row_gap; add the table if you have none). Two tables with\n"
    "# the same name make the whole config invalid, so run `herdr config check`, then\n"
    "# `herdr server reload-config`. Generate this again after changing the palette or rule colours.\n"
)
SECOND_ROW = '["branch", "git_status"]'


def fingerprint(config: Config) -> str:
    """Short hash of the slot colours, to spot a pasted block that no longer matches the config."""
    layout = "|".join(color or "-" for color in config.slots)
    return hashlib.sha256(layout.encode("utf-8")).hexdigest()[:8]


def render_rows(config: Config) -> str:
    entries: List[str] = ['"state_icon"']
    for slot, color in enumerate(config.slots):
        token = "$" + token_name(slot)
        entries.append('{{ token = "{}", fg = "{}" }}'.format(token, color) if color else '"{}"'.format(token))
    first_row = "".join("    {},\n".format(entry) for entry in entries)
    header = HEADER.format(palette=config.palette_name, count=len(config.slots), fingerprint=fingerprint(config))
    return "{}[ui.sidebar.spaces]\nrows = [\n  [\n{}  ],\n  {},\n]\n".format(header, first_row, SECOND_ROW)
