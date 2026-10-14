"""Turn a space name into its colour key, and a key into a stable palette index."""
from __future__ import annotations

import hashlib
import unicodedata
from typing import Tuple

from config import Config

HASH_BYTES = 8


def derive_key(label: str, config: Config) -> str:
    """The part of the name that picks the colour: all of it, or the text before/after the separator.

    Unicode is normalized (NFC), whitespace runs count as one space, and a trailing sort marker
    such as " +" is ignored, so "ACME +" and "ACME - api" share a key. A missing separator or an
    empty side falls back to the whole name.
    """
    text = " ".join(unicodedata.normalize("NFC", label).split())
    text = _strip_suffix(text, config.ignore_suffixes)
    if config.key_mode == "prefix":
        side, found, _ = text.partition(config.separator)
    elif config.key_mode == "suffix":
        _, found, side = text.rpartition(config.separator)
    else:
        side, found = text, ""
    key = side.strip() if found and side.strip() else text
    return key.casefold() if config.ignore_case else key


def _strip_suffix(text: str, suffixes: Tuple[str, ...]) -> str:
    for suffix in suffixes:
        if text.endswith(suffix) and len(text) > len(suffix):
            return text[: -len(suffix)].rstrip()
    return text


def color_index(key: str, size: int) -> int:
    """sha256 of the key, first 8 bytes big-endian, modulo the palette size.

    Stable across runs, machines and Python versions (unlike `hash()`), so a customer keeps its
    colour everywhere.
    """
    digest = hashlib.sha256(key.encode("utf-8")).digest()
    return int.from_bytes(digest[:HASH_BYTES], "big") % size
