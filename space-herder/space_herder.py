#!/usr/bin/env python3
"""Herd the Herdr spaces sidebar: sort the spaces into groups and colour them by customer.

The sort puts the home space "~" first, then names ending with " +" (head), plain names, and names
ending with " -" (bottom), each group by name ignoring case. The colour follows the customer
prefix of the name, so every space of one customer shares it. The hooks recolour after every
event and, when `auto_sort` says so, sort after a space is created or renamed. See the README.
"""
from __future__ import annotations

import argparse
import sys
from typing import Callable, List, Optional, Tuple

from coloring import SNIPPET_FILE_NAME, Toast, clear, palette_lines, preview_lines, recolor_toast, reconcile, snippet
from config import PLUGIN_ID, load_config
from herdr_api import Call, config_path, notify, plugin_lock, report_failure, socket_path, socket_rpc
from sorting import autosort_enabled, dry_run_lines, sort_sidebar

TOOL = "space-herder"
COMMANDS = ("recolor", "sort", "preview", "snippet", "clear", "palettes", "hook")
HOOK_EVENTS = ("startup", "created", "renamed", "focused", "updated")
SORT_FAILED = "Space sort failed"
COLOR_FAILED = "Colouring failed"
HOOK_FAILED = "Space Herder failed"


def sort(call: Call) -> Toast:
    with plugin_lock(PLUGIN_ID):
        changed, labels = sort_sidebar(call)
    print(("sorted: " if changed else "already sorted: ") + ", ".join(labels))
    return ("Spaces sorted" if changed else "Spaces already sorted"), None


def run(args: argparse.Namespace) -> Optional[Toast]:
    """Do a command from a key binding or a terminal; returns the toast it shows, or None."""
    if args.command == "palettes":
        print("\n".join(palette_lines()))
        return None
    if args.command == "sort":
        call = socket_rpc(socket_path(), TOOL)
        if args.dry_run:
            print("\n".join(dry_run_lines(call)))
            return None
        return sort(call)
    path = config_path(PLUGIN_ID, args.config)
    config = load_config(path)
    if args.command == "snippet":
        return snippet(config, path.parent / SNIPPET_FILE_NAME if args.write else None)
    call = socket_rpc(socket_path(), TOOL)
    if args.command == "preview":
        print("\n".join(preview_lines(call, config)))
        return None
    if args.command == "clear":
        clear(call)
        return "Colours cleared", None
    changed = reconcile(call, config)
    print("recoloured {} space(s)".format(changed))
    return recolor_toast(changed)


def hook(event: str, config_file: Optional[str]) -> int:
    """Recolour after every event; after a create or rename also sort, when `auto_sort` says so.

    Silent when it works. The steps run apart, so a failed recolour still sorts. The first failure
    toasts, at most once in a while since hooks run on every focus change; every failure is
    printed, which `herdr plugin log list` shows.
    """
    try:
        config = load_config(config_path(PLUGIN_ID, config_file))
    except Exception as err:  # noqa: BLE001 - a hook has no other place to report
        return report_failure(TOOL, HOOK_FAILED, err, PLUGIN_ID)
    call = socket_rpc(socket_path(), TOOL)
    steps: List[Tuple[str, Callable[[], object]]] = [(COLOR_FAILED, lambda: reconcile(call, config))]
    if autosort_enabled(config.auto_sort, event):
        steps.append((SORT_FAILED, lambda: sort(call)))
    failures = []
    for title, step in steps:
        try:
            step()
        except Exception as err:  # noqa: BLE001 - the other steps still run
            failures.append((title, err))
    if not failures:
        return 0
    for title, err in failures[1:]:
        print("{}: {}: {}".format(TOOL, title, err), file=sys.stderr)
    title, err = failures[0]
    return report_failure(TOOL, title, err, PLUGIN_ID)


def parse_args(argv: Optional[List[str]]) -> argparse.Namespace:
    """Read the command line; an option or event given to another command is an error, not ignored."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("command", nargs="?", default="recolor", choices=COMMANDS)
    parser.add_argument("event", nargs="?", choices=HOOK_EVENTS, help="hook: the Herdr event it runs after")
    parser.add_argument("--config", help="config file (default: the plugin config dir)")
    parser.add_argument("--dry-run", action="store_true", help="sort: print the current and the target order only")
    parser.add_argument("--write", action="store_true", help="snippet: write {} next to the config".format(SNIPPET_FILE_NAME))
    # Intermixed, so options may also sit between the command and its event.
    args = parser.parse_intermixed_args(argv)
    if (args.command == "hook") != (args.event is not None):
        parser.error("an event ({}) goes with hook, and only with hook".format(", ".join(HOOK_EVENTS)))
    if args.dry_run and args.command != "sort":
        parser.error("--dry-run goes with sort only")
    if args.write and args.command != "snippet":
        parser.error("--write goes with snippet only")
    return args


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)
    if args.command == "hook":
        return hook(args.event, args.config)

    try:
        toast = run(args)
    except Exception as err:  # noqa: BLE001 - a detached key binding has no other place to report
        return report_failure(TOOL, SORT_FAILED if args.command == "sort" else COLOR_FAILED, err)

    if toast:
        notify(*toast)
    return 0


if __name__ == "__main__":
    sys.exit(main())
