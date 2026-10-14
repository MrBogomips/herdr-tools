#!/usr/bin/env python3
"""Colour Herdr space names in the sidebar, so every space of one customer shares a colour.

The colour comes from a stable hash of the name's key (its prefix before " -" by default), from a
preset or custom palette, unless a regex rule picks one. Herdr can only style a token's
foreground, so each colour is a slot token (`$spc0`, `$spc1`, ...) styled in config.toml by the
`snippet` command; this tool fills one slot per space with the name. See the README.
"""
from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from config import Config, load_config
from herdr_api import (
    Call,
    Workspace,
    config_path,
    list_workspaces,
    notify,
    plugin_lock,
    report_failure,
    socket_path,
    socket_rpc,
    state_dir,
)
from palettes import PRESETS
from plan import Choice, Report, choose, clear_reports, plan_reports, token_name
from snippet import render_rows
from sticky import STATE_FILE_NAME, load_state, save_state

PLUGIN_ID = "mrbogomips.space-colors"
SOURCE = PLUGIN_ID
COMMANDS = ("reconcile", "preview", "snippet", "clear", "palettes")
SNIPPET_FILE_NAME = "sidebar-rows.toml"

Toast = Tuple[str, Optional[str]]


def reconcile(call: Call, config: Config) -> int:
    """Bring every space's coloured name up to date; returns how many spaces changed."""
    with plugin_lock(PLUGIN_ID):
        spaces = list_workspaces(call)
        reports = plan_reports(spaces, choose_and_remember(spaces, config), config.marker)
        send(call, reports)
    return len({workspace_id for workspace_id, _ in reports})


def choose_and_remember(spaces: List[Workspace], config: Config) -> Dict[str, Choice]:
    """Pick the slots; in sticky mode also save new assignments.

    The state file is shared by every Herdr server on the machine, so its read-modify-write
    holds a lock that is not per server.
    """
    if config.assign != "sticky":
        return choose(spaces, config, {}, date.today())[0]
    state = state_dir(PLUGIN_ID) / STATE_FILE_NAME
    with plugin_lock(PLUGIN_ID, per_server=False):
        stored = load_state(state)
        choices, remembered = choose(spaces, config, stored, date.today())
        if remembered != stored:
            save_state(state, remembered)
    return choices


def clear(call: Call) -> None:
    with plugin_lock(PLUGIN_ID):
        send(call, clear_reports(list_workspaces(call)))


def send(call: Call, reports: List[Report]) -> None:
    for workspace_id, patch in reports:
        call("workspace.report_metadata", {"workspace_id": workspace_id, "source": SOURCE, "tokens": patch})


def preview_lines(call: Call, config: Config) -> List[str]:
    """One line per space: name, key, slot, colour and why; sticky choices are not saved."""
    spaces = list_workspaces(call)
    stored = load_state(state_dir(PLUGIN_ID) / STATE_FILE_NAME) if config.assign == "sticky" else {}
    choices, _ = choose(spaces, config, stored, date.today())
    width = max([len(space["label"]) for space in spaces] + [5])
    lines = []
    for space in spaces:
        choice = choices[space["workspace_id"]]
        color = config.slots[choice.slot] or "unstyled"
        lines.append(
            "{:<{}}  {:<20}  {:<5}  {:<8}  {}".format(
                space["label"], width, choice.key, token_name(choice.slot), color, choice.reason
            )
        )
    return lines


def palette_lines() -> List[str]:
    return ["{:<12} {}".format(name, " ".join(colors)) for name, colors in sorted(PRESETS.items())]


def snippet(config: Config, target: Optional[Path]) -> Optional[Toast]:
    """Print the sidebar rows, or write them next to config.json (for the plugin action)."""
    if target is None:
        print(render_rows(config), end="")
        return None
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(render_rows(config), encoding="utf-8")
    print("wrote {}".format(target))
    return "Sidebar rows written", str(target)


def run(args: argparse.Namespace) -> Optional[Toast]:
    """Do the command; returns the toast a manual run shows, or None."""
    if args.command == "palettes":
        print("\n".join(palette_lines()))
        return None
    path = config_path(PLUGIN_ID, args.config)
    config = load_config(path)
    if args.command == "snippet":
        return snippet(config, path.parent / SNIPPET_FILE_NAME if args.write else None)
    call = socket_rpc(socket_path(), "space-colors")
    if args.command == "preview":
        print("\n".join(preview_lines(call, config)))
        return None
    if args.command == "clear":
        clear(call)
        return "Space colours cleared", None
    changed = reconcile(call, config)
    print("recoloured {} space(s)".format(changed))
    if not changed:
        return "Space colours already up to date", None
    return "Space colours updated", "{} space{}".format(changed, "" if changed == 1 else "s")


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("command", nargs="?", default="reconcile", choices=COMMANDS)
    parser.add_argument("--hook", action="store_true", help="run as a Herdr startup or event hook: no toast on success")
    parser.add_argument("--config", help="config file (default: the plugin config dir)")
    parser.add_argument("--write", action="store_true", help="snippet: write {} next to the config".format(SNIPPET_FILE_NAME))
    args = parser.parse_args(argv)

    try:
        toast = run(args)
    except Exception as err:  # noqa: BLE001 - a detached hook or key binding has no other place to report
        return report_failure("space-colors", "Space colours failed", err, PLUGIN_ID if args.hook else None)

    if toast and not args.hook:
        notify(*toast)
    return 0


if __name__ == "__main__":
    sys.exit(main())
