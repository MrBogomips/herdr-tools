"""Preset palettes taken from popular editor and terminal themes, plus custom palette parsing.

Only accent colours are listed: background and plain text colours would make a coloured name
look uncoloured. Themes with more accents than 8 add their own extra shades, up to the 15 colours
a sidebar row can hold; the most distinct colours come first, so `palette_size` can keep just
those. The order is part of the contract, since a space's colour is an index into it.
"""
from __future__ import annotations

import re
from typing import Any, Dict, Tuple

Palette = Tuple[str, ...]

DEFAULT_PALETTE = "catppuccin"
MIN_PRESET_COLORS = 8
HEX_COLOR = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")

PRESETS: Dict[str, Palette] = {
    # Catppuccin Mocha: the 14 accents (most distinct first), then overlay 2.
    "catppuccin": (
        "#f38ba8", "#fab387", "#f9e2af", "#a6e3a1", "#94e2d5",
        "#89dceb", "#89b4fa", "#b4befe", "#cba6f7", "#f5c2e7",
        "#f2cdcd", "#f5e0dc", "#eba0ac", "#74c7ec", "#9399b2",
    ),
    # Dracula: red, orange, yellow, green, cyan, purple, pink, comment, then the ANSI bright
    # red, green, yellow, blue, magenta and cyan.
    "dracula": (
        "#ff5555", "#ffb86c", "#f1fa8c", "#50fa7b", "#8be9fd",
        "#bd93f9", "#ff79c6", "#6272a4", "#ff6e6e", "#69ff94",
        "#ffffa5", "#d6acff", "#ff92df", "#a4ffff",
    ),
    # GitHub Dark: red, orange, yellow, green, cyan, blue, purple, pink, then the ANSI bright
    # red, green, yellow, blue, magenta, cyan and the light pink.
    "github-dark": (
        "#ff7b72", "#ffa657", "#d29922", "#3fb950", "#39c5cf",
        "#58a6ff", "#bc8cff", "#db61a2", "#ffa198", "#56d364",
        "#e3b341", "#79c0ff", "#d2a8ff", "#56d4dd", "#f778ba",
    ),
    # Gruvbox dark: the bright accents, gray, then the neutral accents.
    "gruvbox": (
        "#fb4934", "#fe8019", "#fabd2f", "#b8bb26", "#8ec07c",
        "#83a598", "#d3869b", "#a89984", "#cc241d", "#d65d0e",
        "#d79921", "#98971a", "#689d6a", "#458588", "#b16286",
    ),
    # Kanagawa Wave: peach red, surimi orange, carp yellow, spring green, wave aqua, spring blue,
    # crystal blue, oni violet, sakura pink, then samurai red, ronin yellow, autumn green, spring
    # violet, boat yellow and light blue.
    "kanagawa": (
        "#ff5d62", "#ffa066", "#e6c384", "#98bb6c", "#7aa89f",
        "#7fb4ca", "#7e9cd8", "#957fb8", "#d27e99", "#e82424",
        "#ff9e3b", "#76946a", "#9cabca", "#c0a36e", "#a3d4d5",
    ),
    # Nord aurora and frost (nord11-15, nord7-10): Nord has no more accents.
    "nord": (
        "#bf616a", "#d08770", "#ebcb8b", "#a3be8c", "#b48ead",
        "#8fbcbb", "#88c0d0", "#81a1c1", "#5e81ac",
    ),
    # One Dark (red, dark red, orange, yellow, green, cyan, blue, purple).
    "one-dark": ("#e06c75", "#be5046", "#d19a66", "#e5c07b", "#98c379", "#56b6c2", "#61afef", "#c678dd"),
    # Solarized accents (yellow, orange, red, magenta, violet, blue, cyan, green).
    "solarized": ("#b58900", "#cb4b16", "#dc322f", "#d33682", "#6c71c4", "#268bd2", "#2aa198", "#859900"),
    # Tokyo Night: red, orange, yellow, green, green1, cyan, blue, magenta, then red1, green2,
    # blue1, magenta2, purple, teal and blue6.
    "tokyo-night": (
        "#f7768e", "#ff9e64", "#e0af68", "#9ece6a", "#73daca",
        "#7dcfff", "#7aa2f7", "#bb9af7", "#db4b4b", "#41a6b5",
        "#2ac3de", "#ff007c", "#9d7cd8", "#1abc9c", "#b4f9f8",
    ),
}


def normalize_hex(value: Any) -> str:
    """Return a colour as lowercase #rrggbb; Herdr token styles accept only hex foregrounds."""
    if not isinstance(value, str) or not HEX_COLOR.match(value):
        raise ValueError("{!r} is not a #RGB or #RRGGBB colour".format(value))
    digits = value[1:].lower()
    if len(digits) == 3:
        digits = "".join(digit * 2 for digit in digits)
    return "#" + digits


def resolve_palette(spec: Any) -> Palette:
    """A preset name (any case) or a non-empty list of distinct hex colours."""
    if isinstance(spec, str):
        name = spec.strip().lower()
        if name not in PRESETS:
            raise ValueError("unknown palette {!r}; presets: {}".format(spec, ", ".join(sorted(PRESETS))))
        return PRESETS[name]
    if not isinstance(spec, list) or not spec:
        raise ValueError("palette must be a preset name or a non-empty list of hex colours")
    colors = tuple(normalize_hex(color) for color in spec)
    if len(set(colors)) != len(colors):
        raise ValueError("palette repeats a colour: {}".format(", ".join(colors)))
    return colors
