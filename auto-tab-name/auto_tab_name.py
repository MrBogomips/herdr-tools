#!/usr/bin/env python3
"""Name each Herdr tab after the folder of its pane.

Every manifest entry runs this script: the startup and event hooks and the refresh action
(`reconcile --hook`), the key-bound actions (`sync`, `toggle`, `follow`, `unfollow`, `configure`)
and the configuration popup (`menu`). A tab follows its folder until it is renamed by hand; see
the README.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
from typing import Any, Callable, Dict, Iterator, List, Mapping, Optional, Sequence, Set, Tuple

from config import Config, load_config, save_config
from herdr_api import (
    SOCKET_TIMEOUT_SECONDS,
    Call,
    ConfigError,
    HerdrError,
    config_path,
    notify,
    plugin_lock,
    report_failure,
    socket_path,
    socket_rpc,
)
from menu import run_menu
from naming import tab_label
from plan import Rename, auto_labels, plan_tabs, set_follow
from state import load_states, save_states, state_file

PLUGIN_ID = "mrbogomips.auto-tab-name"
TOOL = "auto-tab-name"
CONFIGURE_ENTRYPOINT = "configure"
NO_TAB_MESSAGE = "no current tab: run this from a tab"
TAB_NOT_FOUND = "tab_not_found"


class AfterSaveError(Exception):
    """A step after a saved change failed; `title` says the change holds, so a retry won't undo it."""

    def __init__(self, title: str, cause: Exception) -> None:
        super().__init__(str(cause))
        self.title = title
        self.cause = cause


@contextmanager
def after_save(title: str) -> Iterator[None]:
    """Report a failure inside the block under `title` instead of the command's own failure title."""
    try:
        yield
    except Exception as err:  # noqa: BLE001 - main() reports it like any other failure
        raise AfterSaveError(title, err) from err


def renamed_summary(count: int) -> Optional[str]:
    return "Renamed {} tab(s)".format(count) if count else None


def _list_records(call: Call, method: str, key: str) -> List[Dict[str, Any]]:
    result = call(method, {})
    records = result.get(key) if isinstance(result, dict) else None
    if not isinstance(records, list) or not all(isinstance(record, dict) for record in records):
        raise HerdrError("unexpected {} result".format(method), "bad_result")
    return records


def list_tabs(call: Call) -> List[Dict[str, Any]]:
    tabs = _list_records(call, "tab.list", "tabs")
    for item in tabs:
        if not all(isinstance(item.get(key), str) for key in ("tab_id", "workspace_id", "label")):
            raise HerdrError("unexpected tab.list result", "bad_result")
    return tabs


def list_panes(call: Call) -> List[Dict[str, Any]]:
    panes = _list_records(call, "pane.list", "panes")
    for item in panes:
        folders_ok = all(isinstance(item.get(key), (str, type(None))) for key in ("cwd", "foreground_cwd"))
        if not (isinstance(item.get("pane_id"), str) and isinstance(item.get("tab_id"), str)
                and isinstance(item.get("focused"), bool) and folders_ok):
            raise HerdrError("unexpected pane.list result", "bad_result")
    return panes


def load_tab_states(path: Path) -> Dict[str, Any]:
    states, warning = load_states(path)
    if warning:
        print("auto-tab-name: ignoring damaged state: " + warning, file=sys.stderr)
    return states


def reconcile_tabs(call: Call, config: Config, state_path: Path, only: Optional[set] = None) -> List[Rename]:
    """Rename the tabs that should follow their folder; the caller holds the plugin lock.

    A tab that closed before its rename is skipped and forgotten. Nothing is saved when another
    rename fails: the tabs already renamed are recognised as ours on the next run, because their
    label equals the name computed for them.
    """
    tabs = list_tabs(call)
    panes = list_panes(call)
    states = load_tab_states(state_path)
    home = str(Path.home())
    plan = plan_tabs(
        tabs, panes, states,
        label_for=lambda cwd: tab_label(cwd, config, home),
        source=config.source, only=only,
    )
    renames, closed = _apply_renames(call, plan.renames, {item["tab_id"]: item["label"] for item in tabs})
    new_states = {tab_id: state for tab_id, state in plan.states.items() if tab_id not in closed}
    if new_states != states:
        save_states(state_path, new_states)
    return renames


def _apply_renames(call: Call, renames: Sequence[Rename],
                   old_labels: Mapping[str, str]) -> Tuple[List[Rename], Set[str]]:
    """Make the renames; returns the ones made and the tabs that closed before theirs."""
    done: List[Rename] = []
    closed: Set[str] = set()
    for rename in renames:
        try:
            call("tab.rename", {"tab_id": rename.tab_id, "label": rename.label})
        except HerdrError as err:
            if err.code != TAB_NOT_FOUND:
                raise
            closed.add(rename.tab_id)
            print("skipped {}: the tab closed before its rename".format(rename.tab_id))
            continue
        done.append(rename)
        print("renamed {}: {} -> {}".format(rename.tab_id, old_labels[rename.tab_id], rename.label))
    return done, closed


def reconcile_locked(config: Config, only: Optional[set] = None) -> List[Rename]:
    with plugin_lock(PLUGIN_ID):
        return reconcile_tabs(socket_rpc(socket_path(), TOOL), config, state_file(PLUGIN_ID), only)


def current_tab_id() -> str:
    tab_id = os.environ.get("HERDR_TAB_ID")
    if not tab_id:
        try:
            context = json.loads(os.environ.get("HERDR_PLUGIN_CONTEXT_JSON", ""))
        except ValueError:
            context = None
        tab_id = context.get("tab_id") if isinstance(context, dict) else None
    if not isinstance(tab_id, str) or not tab_id:
        raise HerdrError(NO_TAB_MESSAGE, "no_tab")
    return tab_id


def cmd_reconcile(args: argparse.Namespace, path: Path) -> int:
    config = load_config(path)
    if not config.auto_sync:
        return 0
    reconcile_locked(config)
    return 0


def cmd_sync(args: argparse.Namespace, path: Path) -> int:
    renames = reconcile_locked(load_config(path))
    if renames:
        notify("Tab names synced", renamed_summary(len(renames)))
    else:
        notify("Tab names already up to date")
    return 0


def cmd_toggle(args: argparse.Namespace, path: Path) -> int:
    current = load_config(path)
    config = replace(current, auto_sync=not current.auto_sync)
    save_config(path, config)
    if not config.auto_sync:
        notify("Auto tab names off")
        return 0
    with after_save("Auto tab names on; names not updated"):
        renames = reconcile_locked(config)
    notify("Auto tab names on", renamed_summary(len(renames)))
    return 0


def _set_follow(tab_id: str, follow: bool, config: Config) -> str:
    """Record the choice for one tab (and rename it when it now follows); returns its label."""
    with plugin_lock(PLUGIN_ID):
        call = socket_rpc(socket_path(), TOOL)
        state_path = state_file(PLUGIN_ID)
        tabs = list_tabs(call)
        tab = next((item for item in tabs if item["tab_id"] == tab_id), None)
        if tab is None:
            raise HerdrError("tab {} not found".format(tab_id), TAB_NOT_FOUND)
        if not follow and tab["label"] == auto_labels(tabs)[tab_id]:
            # Pin the automatic label, the tab's position: once a tab in front of it closes, its new
            # position would otherwise read as "renamed back to its automatic name".
            call("tab.rename", {"tab_id": tab_id, "label": tab["label"]})
        save_states(state_path, set_follow(load_tab_states(state_path), tab, follow))
        if not follow:
            return tab["label"]
        with after_save("Tab followed; name not updated"):
            renames = reconcile_tabs(call, config, state_path, None if config.auto_sync else {tab_id})
        return next((item.label for item in renames if item.tab_id == tab_id), tab["label"])


def cmd_follow(args: argparse.Namespace, path: Path) -> int:
    config = load_config(path)
    notify("Tab follows its folder", _set_follow(current_tab_id(), True, config))
    return 0


def cmd_unfollow(args: argparse.Namespace, path: Path) -> int:
    config = load_config(path)
    notify("Tab name kept", _set_follow(current_tab_id(), False, config))
    return 0


def popup_command() -> List[str]:
    return [os.environ.get("HERDR_BIN_PATH", "herdr"), "plugin", "pane", "open", "--plugin", PLUGIN_ID,
            "--entrypoint", CONFIGURE_ENTRYPOINT]


def _popup_failure(command: List[str]) -> Optional[str]:
    """Why the popup command failed, or None when it opened."""
    try:
        done = subprocess.run(command, capture_output=True, text=True, timeout=SOCKET_TIMEOUT_SECONDS)
    except (OSError, subprocess.SubprocessError) as err:
        return str(err)
    reason = _error_answer(done.stderr) or _error_answer(done.stdout)
    if reason or done.returncode == 0:
        return reason
    output = done.stderr.strip() or done.stdout.strip()
    status = "herdr exited with status {}".format(done.returncode)
    return "{}: {}".format(status, output) if output else status


def _error_answer(output: str) -> Optional[str]:
    """The reason given by a herdr `{"error": {"code": ..., "message": ...}}` answer.

    That is the message, or the raw text when there is none; None when `output` is no error answer.
    """
    try:
        answer = json.loads(output)
    except ValueError:
        return None
    if not isinstance(answer, dict) or "error" not in answer:
        return None
    error = answer["error"]
    message = error.get("message") if isinstance(error, dict) else None
    return message.strip() if isinstance(message, str) and message.strip() else output.strip()


def cmd_configure(args: argparse.Namespace, path: Path) -> int:
    reason = _popup_failure(popup_command())
    if reason:
        raise HerdrError("{}; edit {} instead".format(reason, path), "popup")
    return 0


def cmd_menu(args: argparse.Namespace, path: Path) -> int:
    try:
        return _menu(path)
    except KeyboardInterrupt:  # Ctrl-C just closes the popup
        return 0


def _menu(path: Path) -> int:
    try:
        config = load_config(path)
    except ConfigError as err:
        return _show_bad_config(err)
    edited = run_menu(config, input, print)
    if edited is None:
        return 0
    save_config(path, edited)
    with after_save("Settings saved; names not updated"):
        renames = reconcile_locked(edited) if edited.auto_sync else []
    notify("Auto tab name settings saved", renamed_summary(len(renames)))
    return 0


def _show_bad_config(err: ConfigError) -> int:
    print(err)
    print("Fix the file, or delete it to start over, then open this menu again. Press Enter.")
    try:
        input()
    except (EOFError, KeyboardInterrupt):
        pass
    return 1


COMMANDS: Mapping[str, Tuple[Callable[[argparse.Namespace, Path], int], str]] = {
    "reconcile": (cmd_reconcile, "Tab names not updated"),
    "sync": (cmd_sync, "Tab names not updated"),
    "toggle": (cmd_toggle, "Auto tab names not toggled"),
    "follow": (cmd_follow, "Tab not followed"),
    "unfollow": (cmd_unfollow, "Tab name not kept"),
    "configure": (cmd_configure, "Configuration popup not opened"),
    "menu": (cmd_menu, "Settings not applied"),
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--config", help="config file (default: the plugin config dir)")
    commands = parser.add_subparsers(dest="command", required=True)
    reconcile = commands.add_parser("reconcile", help="rename the tabs that follow their folder")
    reconcile.add_argument("--hook", action="store_true", help="run as a hook: failures toast at most once in a while")
    for name, help_text in (
        ("sync", "rename the tabs now, whatever auto_sync says"),
        ("toggle", "switch auto_sync on or off"),
        ("follow", "make the current tab follow its folder"),
        ("unfollow", "keep the current tab's name"),
        ("configure", "open the configuration popup"),
        ("menu", "the configuration menu (runs inside the popup)"),
    ):
        commands.add_parser(name, help=help_text)
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    handler, failure_title = COMMANDS[args.command]
    hook = getattr(args, "hook", False)
    try:
        return handler(args, config_path(PLUGIN_ID, args.config))
    except AfterSaveError as err:
        return report_failure(TOOL, err.title, err.cause, PLUGIN_ID if hook else None)
    except Exception as err:  # noqa: BLE001 - a detached hook or key binding has no other place to report
        return report_failure(TOOL, failure_title, err, PLUGIN_ID if hook else None)


if __name__ == "__main__":
    sys.exit(main())
