#!/usr/bin/env python3
"""Sort Herdr spaces (workspaces) by name, ignoring case, with the home space "~" first.

Herdr has no sort setting for spaces, so this reorders them once through the socket API
(`workspace.move_block`). Bind it to a key in config.toml; see the README.
"""
import argparse
import json
import os
import socket
import subprocess
import sys
from pathlib import Path

HOME_LABEL = "~"
SOCKET_TIMEOUT_SECONDS = 5
DEFAULT_SOCKET_PATH = Path.home() / ".config" / "herdr" / "herdr.sock"


class HerdrError(Exception):
    """A Herdr request failed or returned something unexpected."""


def plan_order(workspaces):
    """Return workspace ids in the target order.

    Worktree children sort with their parent (its label, then its position), so a worktree
    group stays together even when other spaces share the parent's label. Equal keys keep
    their current order.
    """
    parents = {
        space["worktree"]["repo_key"]: space
        for space in workspaces
        if space.get("worktree") and not space["worktree"].get("is_linked_worktree")
    }

    def sort_key(space):
        label = space["label"]
        tree = space.get("worktree") or {}
        is_child = bool(tree.get("is_linked_worktree")) and tree.get("repo_key") in parents
        group = parents[tree["repo_key"]] if is_child else space
        return (
            group["label"] != HOME_LABEL,
            group["label"].casefold(),
            group["number"],
            is_child,
            label.casefold(),
            space["number"],
        )

    return [space["workspace_id"] for space in sorted(workspaces, key=sort_key)]


def sort_spaces(call):
    """Reorder the spaces through `call(method, params) -> result`.

    Returns (changed, labels in the final order).
    """
    current = _workspaces(call("workspace.list", {}))
    target_ids = plan_order(current)
    labels_by_id = {space["workspace_id"]: space["label"] for space in current}
    if target_ids == [space["workspace_id"] for space in current]:
        return False, [labels_by_id[workspace_id] for workspace_id in target_ids]

    moved = _workspaces(call("workspace.move_block", {"workspace_ids": target_ids}))
    moved_ids = [space["workspace_id"] for space in moved]
    if moved_ids != target_ids:
        raise HerdrError("Herdr returned a different order: " + ", ".join(space["label"] for space in moved))
    return True, [space["label"] for space in moved]


def _workspaces(result):
    spaces = result.get("workspaces") if isinstance(result, dict) else None
    if not isinstance(spaces, list) or not all(
        isinstance(space, dict) and {"workspace_id", "label", "number"} <= space.keys() for space in spaces
    ):
        raise HerdrError("unexpected workspace list from Herdr: " + json.dumps(result)[:200])
    return spaces


def socket_rpc(socket_path):
    """Return a `call(method, params)` that sends one newline-delimited JSON request per call."""

    def call(method, params):
        request = {"id": "sort-spaces:" + method, "method": method, "params": params}
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
            client.settimeout(SOCKET_TIMEOUT_SECONDS)
            client.connect(str(socket_path))
            client.sendall((json.dumps(request) + "\n").encode())
            response = json.loads(_read_line(client))
        if not isinstance(response, dict):
            raise HerdrError("{} returned an unexpected response: {}".format(method, json.dumps(response)[:200]))
        if "error" in response:
            error = response["error"]
            if isinstance(error, dict):
                error = "{}: {}".format(error.get("code", "error"), error.get("message", ""))
            raise HerdrError("{} failed: {}".format(method, error))
        return response.get("result")

    return call


def _read_line(client):
    chunks = []
    while True:
        chunk = client.recv(65536)
        if not chunk:
            break
        chunks.append(chunk)
        if b"\n" in chunk:
            break
    line = b"".join(chunks).split(b"\n", 1)[0]
    if not line:
        raise HerdrError("Herdr closed the connection without a response")
    return line.decode()


def notify(title, body=None):
    command = [os.environ.get("HERDR_BIN_PATH", "herdr"), "notification", "show", title]
    if body:
        command += ["--body", body]
    try:
        subprocess.run(command, check=True, capture_output=True, timeout=SOCKET_TIMEOUT_SECONDS)
    except (OSError, subprocess.SubprocessError) as err:
        print("could not show the Herdr notification: {}".format(err), file=sys.stderr)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dry-run", action="store_true", help="print the current and target order only")
    args = parser.parse_args(argv)
    call = socket_rpc(os.environ.get("HERDR_SOCKET_PATH") or DEFAULT_SOCKET_PATH)

    try:
        if args.dry_run:
            current = _workspaces(call("workspace.list", {}))
            labels_by_id = {space["workspace_id"]: space["label"] for space in current}
            print("current:", ", ".join(space["label"] for space in current))
            print("target: ", ", ".join(labels_by_id[workspace_id] for workspace_id in plan_order(current)))
            return 0
        changed, labels = sort_spaces(call)
    except (HerdrError, OSError, ValueError) as err:
        print("sort-spaces: {}".format(err), file=sys.stderr)
        notify("Space sort failed", str(err))
        return 1
    except Exception as err:  # noqa: BLE001 - a detached key binding has no other place to report
        reason = "{}: {}".format(type(err).__name__, err)
        print("sort-spaces: unexpected error: {}".format(reason), file=sys.stderr)
        notify("Space sort failed", reason)
        return 1

    print(("sorted: " if changed else "already sorted: ") + ", ".join(labels))
    notify("Spaces sorted" if changed else "Spaces already sorted")
    return 0


if __name__ == "__main__":
    sys.exit(main())
