"""auto-tab-name settings: read config.json, validate it, and write it back."""
from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, Mapping, Tuple

from herdr_api import ConfigError, load_json_config

FORMATS = ("basename", "repo", "last_n", "home_path", "repo_branch")
SOURCES = ("foreground_cwd", "cwd")
# Key order here is the order of the file `save_config` writes.
DEFAULTS: Dict[str, Any] = {
    "auto_sync": True,
    "format": "basename",
    "depth": 2,
    "max_length": 24,
    "source": "foreground_cwd",
    "home_tilde": True,
}
BOOL_KEYS = ("auto_sync", "home_tilde")
MIN_DEPTH = 1
MIN_MAX_LENGTH = 0
JSON_INDENT = 2


@dataclass(frozen=True)
class Config:
    auto_sync: bool = True
    format: str = "basename"
    depth: int = 2
    max_length: int = 24
    source: str = "foreground_cwd"
    home_tilde: bool = True


def load_config(path: Path) -> Config:
    return build_config(load_json_config(path, DEFAULTS), str(path))


def build_config(raw: Mapping[str, Any], origin: str) -> Config:
    """Validate merged settings; every error names `origin` and the offending key."""
    try:
        return _build(raw)
    except ValueError as err:
        raise ConfigError("{}: {}".format(origin, err)) from err


def _build(raw: Mapping[str, Any]) -> Config:
    for name in BOOL_KEYS:
        if not isinstance(raw[name], bool):
            raise ValueError("{} must be true or false, not {!r}".format(name, raw[name]))
    _check_int(raw, "depth", MIN_DEPTH)
    _check_int(raw, "max_length", MIN_MAX_LENGTH)
    _check_choice(raw, "format", FORMATS)
    _check_choice(raw, "source", SOURCES)
    return Config(**{name: raw[name] for name in DEFAULTS})


def _check_int(raw: Mapping[str, Any], name: str, minimum: int) -> None:
    value = raw[name]
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ValueError("{} must be a whole number of {} or more, not {!r}".format(name, minimum, value))


def _check_choice(raw: Mapping[str, Any], name: str, choices: Tuple[str, ...]) -> None:
    if raw[name] not in choices:
        raise ValueError("{} must be one of {}, not {!r}".format(name, ", ".join(choices), raw[name]))


def config_to_dict(config: Config) -> Dict[str, Any]:
    """The settings as a plain dict, keys in file order."""
    values = asdict(config)
    return {name: values[name] for name in DEFAULTS}


def save_config(path: Path, config: Config) -> None:
    """Write the config atomically, so a crash never leaves half a file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(dir=str(path.parent), prefix=path.name + ".", suffix=".tmp")
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as output:
            json.dump(config_to_dict(config), output, indent=JSON_INDENT)
            output.write("\n")
        os.replace(temporary, path)
    except BaseException:
        os.unlink(temporary)
        raise
