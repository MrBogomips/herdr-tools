"""Read herdr-plugin.toml and check the metadata the marketplace indexes.

The marketplace lists a manifest only when its required metadata parses, so the check must parse like
TOML does. tomllib (Python 3.11+) is authoritative; on the macOS system Python (3.9) a small fallback
reads the subset the plugins use (strings, arrays, booleans, numbers, [table] and [[array]] headers)
and refuses anything else rather than guessing.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Dict, FrozenSet, List, Optional, Tuple

try:
    import tomllib
except ImportError:  # Python < 3.11
    tomllib = None  # type: ignore[assignment]

REQUIRED = ("id", "name", "version", "min_herdr_version")
CONVENTIONAL = ("description", "platforms")
PLATFORMS = frozenset({"macos", "linux", "windows"})
LOCAL_ID_TABLES = ("actions", "panes", "link_handlers")
SEMVER = re.compile(r"^\d+\.\d+\.\d+$")

_ARRAY_HEADER = re.compile(r"^\[\[\s*([A-Za-z0-9_-]+)\s*\]\]$")
_TABLE_HEADER = re.compile(r"^\[\s*([A-Za-z0-9_-]+)\s*\]$")
_KEY = re.compile(r"^([A-Za-z0-9_-]+)\s*=\s*(.*)$")
_NUMBER = re.compile(r"^[+-]?\d+(\.\d+)?$")


class ManifestError(ValueError):
    pass


@dataclass(frozen=True)
class Finding:
    level: str  # "error" | "warn" | "info" | "ok"
    message: str


@dataclass(frozen=True)
class Summary:
    id: Optional[str]
    name: Optional[str]
    version: Optional[str]
    min_herdr_version: Optional[str]
    description: Optional[str]
    platforms: FrozenSet[str]
    actions: FrozenSet[str]
    events: Tuple[str, ...]
    panes: FrozenSet[str]
    link_handlers: FrozenSet[str]
    startup: int


def parse(text: str, use_tomllib: bool = True) -> Dict[str, Any]:
    if use_tomllib and tomllib is not None:
        try:
            return tomllib.loads(text)
        except tomllib.TOMLDecodeError as exc:
            raise ManifestError(str(exc)) from exc
    return _parse_subset(text)


def summarise(data: Dict[str, Any]) -> Summary:
    def text(key: str) -> Optional[str]:
        value = data.get(key)
        return value if isinstance(value, str) else None

    platforms = data.get("platforms")
    startup = data.get("startup")
    return Summary(
        id=text("id"),
        name=text("name"),
        version=text("version"),
        min_herdr_version=text("min_herdr_version"),
        description=text("description"),
        platforms=frozenset(p for p in platforms if isinstance(p, str)) if isinstance(platforms, list) else frozenset(),
        actions=frozenset(table_ids(data, "actions")),
        events=tuple(table_ids(data, "events", "on")),
        panes=frozenset(table_ids(data, "panes")),
        link_handlers=frozenset(table_ids(data, "link_handlers")),
        startup=len(startup) if isinstance(startup, list) else 0,
    )


def table_ids(data: Dict[str, Any], table: str, key: str = "id") -> List[str]:
    """The `key` of every [[table]] entry that has a string one."""
    entries = data.get(table)
    if not isinstance(entries, list):
        return []
    return [entry[key] for entry in entries if isinstance(entry, dict) and isinstance(entry.get(key), str)]


def check(data: Dict[str, Any], folder: str, owner: str) -> List[Finding]:
    """Marketplace metadata plus this repo's conventions (id = <owner>.<folder>, platforms declared)."""
    findings: List[Finding] = []
    for key in REQUIRED + CONVENTIONAL[:1]:
        value = data.get(key)
        if not isinstance(value, str) or not value.strip():
            findings.append(Finding("error", "{}: `{}` is missing or empty".format(folder, key)))
    for key in ("version", "min_herdr_version"):
        value = data.get(key)
        if isinstance(value, str) and value and not SEMVER.match(value):
            findings.append(Finding("error", "{}: `{}` = {!r} is not plain X.Y.Z semver".format(folder, key, value)))
    expected = "{}.{}".format(owner.lower(), folder)
    if isinstance(data.get("id"), str) and data["id"] != expected:
        findings.append(Finding("error", "{}: id {!r} should be {!r}".format(folder, data["id"], expected)))
    findings.extend(_check_platforms(data.get("platforms"), folder))
    for table in LOCAL_ID_TABLES:
        for local_id in table_ids(data, table):
            if "." in local_id:
                findings.append(Finding("error", "{}: [[{}]] id {!r} contains a dot".format(folder, table, local_id)))
    return findings


def _check_platforms(platforms: Any, folder: str) -> List[Finding]:
    if not isinstance(platforms, list) or not platforms:
        return [Finding("error", "{}: `platforms` is missing or empty (the index records it)".format(folder))]
    unknown = [p for p in platforms if p not in PLATFORMS]
    if unknown:
        return [Finding("error", "{}: unknown platforms {}; use {}".format(folder, unknown, sorted(PLATFORMS)))]
    return []


# --- fallback parser -------------------------------------------------------------------------


def _parse_subset(text: str) -> Dict[str, Any]:
    root: Dict[str, Any] = {}
    current = root
    lines = text.splitlines()
    index = 0
    while index < len(lines):
        number = index + 1
        line = _strip_comment(lines[index]).strip()
        index += 1
        if not line:
            continue
        header = _ARRAY_HEADER.match(line)
        if header:
            entries = root.setdefault(header.group(1), [])
            if not isinstance(entries, list):
                raise ManifestError("line {}: [[{}]] reuses a key".format(number, header.group(1)))
            current = {}
            entries.append(current)
            continue
        header = _TABLE_HEADER.match(line)
        if header:
            if header.group(1) in root:
                raise ManifestError("line {}: [{}] is defined twice".format(number, header.group(1)))
            current = root[header.group(1)] = {}
            continue
        pair = _KEY.match(line)
        if not pair:
            raise ManifestError("line {}: cannot parse {!r}".format(number, line))
        key, raw = pair.groups()
        while raw.startswith("[") and _depth(raw) > 0:
            if index >= len(lines):
                raise ManifestError("line {}: unterminated array".format(number))
            raw += "\n" + _strip_comment(lines[index])
            index += 1
        if key in current:
            raise ManifestError("line {}: duplicate key {!r}".format(number, key))
        current[key] = _value(raw.strip(), number)
    return root


def _value(raw: str, number: int) -> Any:
    if raw in ("true", "false"):
        return raw == "true"
    if _NUMBER.match(raw):
        return float(raw) if "." in raw else int(raw)
    if raw.startswith("'") and raw.endswith("'") and len(raw) >= 2 and "'" not in raw[1:-1]:
        return raw[1:-1]
    if raw.startswith(('"', "[")) and not raw.startswith('"""'):
        try:
            return json.loads(re.sub(r",\s*\]", "]", raw))
        except ValueError:
            pass
    raise ManifestError("line {}: unsupported value {!r} (use Python 3.11+ for full TOML)".format(number, raw))


def _scan(text: str) -> List[Tuple[int, str, bool]]:
    """(position, character, inside a string) for each character, honouring escapes in basic strings."""
    out = []
    quote = ""
    escaped = False
    for position, char in enumerate(text):
        inside = bool(quote)
        if quote == '"' and escaped:
            escaped = False
        elif quote == '"' and char == "\\":
            escaped = True
        elif quote and char == quote:
            quote = ""
        elif not quote and char in "\"'":
            quote = char
            inside = True
        out.append((position, char, inside))
    return out


def _strip_comment(line: str) -> str:
    for position, char, inside in _scan(line):
        if char == "#" and not inside:
            return line[:position]
    return line


def _depth(raw: str) -> int:
    depth = 0
    for _, char, inside in _scan(raw):
        if not inside:
            depth += {"[": 1, "]": -1}.get(char, 0)
    return depth
