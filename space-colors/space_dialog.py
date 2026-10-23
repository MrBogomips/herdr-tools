#!/usr/bin/env python3
"""Create or rename a Herdr space in a popup that shows the result: its group and its colour.

`open new|rename` runs from the key binding (a plugin action) and opens the popup; `run
new|rename` runs inside the popup, then creates or renames the space, saves a chosen colour as
the override of the space's key, and recolours the spaces. See the README.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional

from config import Config, load_config
from dialog_form import NEW, RENAME, Outcome, Setup
from dialog_ui import run_dialog
from folders import RECENT_FILE_NAME, list_dirs, load_recent, merge_suggestions, remember, save_recent, zoxide_folders
from herdr_api import (
    Call,
    HerdrError,
    config_path,
    list_workspaces,
    plugin_lock,
    report_failure,
    socket_path,
    socket_rpc,
    state_dir,
)
from overrides import OVERRIDES_FILE_NAME, load_overrides, save_overrides, with_override
from space_colors import PLUGIN_ID, reconcile
from sticky import STATE_FILE_NAME, load_state

MODES = (NEW, RENAME)
ENTRYPOINTS = {NEW: "new-space", RENAME: "rename-space"}
ENV_WORKSPACE = "SPACE_COLORS_WORKSPACE_ID"
ENV_CWD = "SPACE_COLORS_CWD"
STDIN_FD = 0


def plugin_context() -> Dict[str, Any]:
    try:
        context = json.loads(os.environ.get("HERDR_PLUGIN_CONTEXT_JSON") or "{}")
    except ValueError:
        return {}
    return context if isinstance(context, dict) else {}


def open_dialog(call: Call, mode: str) -> None:
    """Open the popup, handing it the space and folder the key was pressed in."""
    context = plugin_context()
    workspace_id = context.get("workspace_id") or os.environ.get("HERDR_WORKSPACE_ID") or ""
    if mode == RENAME and not workspace_id:
        raise HerdrError("no space to rename: press the key inside a space")
    cwd = context.get("focused_pane_cwd") or context.get("workspace_cwd") or ""
    call("plugin.pane.open", {
        "plugin_id": PLUGIN_ID,
        "entrypoint": ENTRYPOINTS[mode],
        "placement": "popup",
        "env": {ENV_WORKSPACE: workspace_id, ENV_CWD: cwd},
    })


def open_folders(call: Call) -> List[str]:
    """The folders of the open panes."""
    result = call("pane.list", {})
    panes = result.get("panes") if isinstance(result, dict) else None
    if not isinstance(panes, list):
        return []
    return [pane["cwd"] for pane in panes if isinstance(pane, dict) and isinstance(pane.get("cwd"), str)]


def build_setup(call: Call, mode: str, config: Config) -> Setup:
    state = state_dir(PLUGIN_ID)
    spaces = tuple(list_workspaces(call))
    target_id = (os.environ.get(ENV_WORKSPACE) or None) if mode == RENAME else None
    if mode == RENAME and not any(space["workspace_id"] == target_id for space in spaces):
        raise HerdrError("the space to rename ({}) is no longer open".format(target_id or "none"))
    suggestions = ()
    if mode == NEW:
        suggestions = tuple(merge_suggestions(load_recent(state / RECENT_FILE_NAME), open_folders(call), zoxide_folders()))
    home = str(Path.home())
    return Setup(
        mode=mode,
        home=home,
        cwd=os.environ.get(ENV_CWD) or home,
        workspaces=spaces,
        config=config,
        overrides=load_overrides(state / OVERRIDES_FILE_NAME),
        stored=load_state(state / STATE_FILE_NAME) if config.assign == "sticky" else {},
        today=date.today(),
        target_id=target_id,
        suggestions=suggestions,
        list_dirs=list_dirs,
        is_dir=os.path.isdir,
    )


def apply(call: Call, setup: Setup, outcome: Outcome) -> None:
    """Save the colour, create or rename the space, then recolour every space at once.

    A colour change alone fires no Herdr event, so the recolouring can't be left to the hooks.
    """
    state = state_dir(PLUGIN_ID)
    if outcome.mode == NEW:
        params: Dict[str, Any] = {"cwd": outcome.cwd, "focus": True}
        if outcome.label:
            params["label"] = outcome.label
        call("workspace.create", params)
        with plugin_lock(PLUGIN_ID, per_server=False):
            recent = state / RECENT_FILE_NAME
            save_recent(recent, remember(load_recent(recent), outcome.cwd or ""))
    else:
        target = setup.target()
        if target is not None and outcome.label != target["label"]:
            call("workspace.rename", {"workspace_id": outcome.workspace_id, "label": outcome.label})
    # Saved only once the space exists, so a failed create or rename leaves no colour behind.
    if outcome.colour_changed:
        with plugin_lock(PLUGIN_ID, per_server=False):
            path = state / OVERRIDES_FILE_NAME
            save_overrides(path, with_override(load_overrides(path), outcome.colour_key, outcome.colour))
    reconcile(call, setup.config)


def run(args: argparse.Namespace) -> None:
    call = socket_rpc(socket_path(), "space-dialog")
    if args.command == "open":
        open_dialog(call, args.mode)
        return
    config = load_config(config_path(PLUGIN_ID, args.config))
    setup = build_setup(call, args.mode, config)
    form = run_dialog(setup, STDIN_FD, sys.stdout)
    if form.result == "submit":
        apply(call, setup, form.outcome(setup))


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("command", choices=("open", "run"), help="open the popup, or run inside it")
    parser.add_argument("mode", choices=MODES)
    parser.add_argument("--config", help="config file (default: the plugin config dir)")
    args = parser.parse_args(argv)
    try:
        run(args)
    except Exception as err:  # noqa: BLE001 - a key binding or popup has no other place to report
        return report_failure("space-colors", "Space dialog failed", err)
    return 0


if __name__ == "__main__":
    sys.exit(main())
