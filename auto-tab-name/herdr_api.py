"""Small Herdr client shared by the herdr-tools plugins.

Vendored: every plugin folder carries an identical copy, so each plugin installs on its own with
`herdr plugin install MrBogomips/herdr-tools/<plugin>`. CI fails when the copies differ; edit one,
then copy it to the other plugins.
"""
from __future__ import annotations

import contextlib
import fcntl
import hashlib
import json
import os
import re
import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Callable, Dict, Iterator, List, Mapping, Optional, Union

SOCKET_TIMEOUT_SECONDS = 5
SOCKET_FILE_NAME = "herdr.sock"
CONFIG_FILE_NAME = "config.json"
LOCK_POLL_SECONDS = 0.05
FAILURE_TOAST_QUIET_SECONDS = 600
FAILURE_STAMP_FILE_NAME = "last-failure-toast.json"

Call = Callable[[str, Dict[str, Any]], Any]
Workspace = Dict[str, Any]


class HerdrError(Exception):
    """A Herdr request failed or returned something unexpected."""

    def __init__(self, message: str, code: Optional[str] = None) -> None:
        super().__init__(message)
        self.code = code


class ConfigError(Exception):
    """The plugin config file is missing a value, malformed, or holds an unknown key."""


class LockTimeout(HerdrError):
    """Another run of the same plugin kept the lock for too long."""


def _herdr_config_dir() -> Path:
    """Herdr's own config folder: under $XDG_CONFIG_HOME when set, as Herdr does, else ~/.config."""
    return Path(os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")) / "herdr"


def socket_path() -> Path:
    """The server socket: the one Herdr hands to plugins, else found by Herdr's own rules."""
    explicit = os.environ.get("HERDR_SOCKET_PATH")
    if explicit:
        return Path(explicit)
    session = os.environ.get("HERDR_SESSION")
    # Herdr names its unnamed session "default", and keeps that one's socket out of sessions/.
    if session and session != "default":
        return _herdr_config_dir() / "sessions" / session / SOCKET_FILE_NAME
    return _herdr_config_dir() / SOCKET_FILE_NAME


def socket_rpc(path: Union[str, Path], client: str) -> Call:
    """Return a `call(method, params)` that sends one newline-delimited JSON request per call."""

    def call(method: str, params: Dict[str, Any]) -> Any:
        request = {"id": "{}:{}".format(client, method), "method": method, "params": params}
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
            connection.settimeout(SOCKET_TIMEOUT_SECONDS)
            connection.connect(str(path))
            connection.sendall((json.dumps(request) + "\n").encode())
            response = json.loads(_read_line(connection))
        if not isinstance(response, dict):
            raise HerdrError("{} returned an unexpected response: {}".format(method, json.dumps(response)[:200]))
        if "error" in response:
            error, code = response["error"], None
            if isinstance(error, dict):
                code = error.get("code")
                error = "{}: {}".format(code or "error", error.get("message", ""))
            raise HerdrError("{} failed: {}".format(method, error), code)
        return response.get("result")

    return call


def _read_line(connection: socket.socket) -> str:
    chunks = []
    while True:
        chunk = connection.recv(65536)
        if not chunk:
            break
        chunks.append(chunk)
        if b"\n" in chunk:
            break
    line = b"".join(chunks).split(b"\n", 1)[0]
    if not line:
        raise HerdrError("Herdr closed the connection without a response")
    return line.decode()


def check_workspaces(result: Any) -> List[Workspace]:
    """Validate a workspace list result; `tokens` and `worktree` are optional per space."""
    spaces = result.get("workspaces") if isinstance(result, dict) else None
    if not isinstance(spaces, list) or not all(
        isinstance(space, dict) and {"workspace_id", "label", "number"} <= space.keys() for space in spaces
    ):
        raise HerdrError("unexpected workspace list from Herdr: " + json.dumps(result)[:200])
    return spaces


def list_workspaces(call: Call) -> List[Workspace]:
    return check_workspaces(call("workspace.list", {}))


def worktree_parents(workspaces: List[Workspace]) -> Dict[str, Workspace]:
    """Map each worktree repo key to the space holding its main checkout."""
    return {
        space["worktree"]["repo_key"]: space
        for space in workspaces
        if space.get("worktree") and not space["worktree"].get("is_linked_worktree")
    }


def parent_of(space: Workspace, parents: Mapping[str, Workspace]) -> Optional[Workspace]:
    """Return the main-checkout space of a linked worktree, or None (plain space or orphan)."""
    tree = space.get("worktree") or {}
    if not tree.get("is_linked_worktree"):
        return None
    return parents.get(tree.get("repo_key"))


def config_path(plugin_id: str, explicit: Optional[str]) -> Path:
    """The config file: --config, else Herdr's plugin config dir, else its default location."""
    if explicit:
        return Path(explicit)
    directory = os.environ.get("HERDR_PLUGIN_CONFIG_DIR")
    if directory:
        return Path(directory) / CONFIG_FILE_NAME
    return _herdr_config_dir() / "plugins" / "config" / plugin_id / CONFIG_FILE_NAME


def load_json_config(path: Path, defaults: Mapping[str, Any]) -> Dict[str, Any]:
    """Merge a JSON object file over `defaults`; a missing file gives the defaults."""
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return dict(defaults)
    except (OSError, ValueError) as err:
        raise ConfigError("{}: {}".format(path, err)) from err
    if not isinstance(raw, dict):
        raise ConfigError("{}: the top level must be a JSON object".format(path))
    unknown = sorted(set(raw) - set(defaults))
    if unknown:
        raise ConfigError(
            "{}: unknown key(s) {}; known keys: {}".format(path, ", ".join(unknown), ", ".join(sorted(defaults)))
        )
    return {**defaults, **raw}


def state_dir(plugin_id: str) -> Path:
    """Herdr's plugin state dir, also when run from a terminal outside a plugin command."""
    directory = os.environ.get("HERDR_PLUGIN_STATE_DIR")
    if directory:
        return Path(directory)
    base = os.environ.get("XDG_STATE_HOME") or str(Path.home() / ".local" / "state")
    return Path(base) / "herdr" / "plugins" / plugin_id


@contextlib.contextmanager
def plugin_lock(plugin_id: str, timeout: float = 10.0, per_server: bool = True) -> Iterator[None]:
    """Serialize runs of one plugin (hooks can fire back to back).

    By default only runs against the same Herdr server wait for each other; pass
    `per_server=False` around files in the state dir, which every server shares. Take the
    per-server lock first when holding both.
    """
    directory = state_dir(plugin_id)
    name = re.sub(r"[^A-Za-z0-9_.-]", "_", plugin_id)
    if per_server:
        name += "-" + hashlib.sha256(str(socket_path()).encode()).hexdigest()[:12]
    name += ".lock"
    directory.mkdir(parents=True, exist_ok=True)
    deadline = time.monotonic() + timeout
    with open(directory / name, "w") as handle:
        while True:
            try:
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise LockTimeout("another {} run is still busy after {}s".format(plugin_id, timeout))
                time.sleep(LOCK_POLL_SECONDS)
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def notify(title: str, body: Optional[str] = None) -> None:
    """Show a Herdr toast; a failure is only printed, since there is nowhere else to report it."""
    command = [os.environ.get("HERDR_BIN_PATH", "herdr"), "notification", "show", title]
    if body:
        command += ["--body", body]
    try:
        subprocess.run(command, check=True, capture_output=True, timeout=SOCKET_TIMEOUT_SECONDS)
    except (OSError, subprocess.SubprocessError) as err:
        print("could not show the Herdr notification: {}".format(err), file=sys.stderr)


def report_failure(tool: str, title: str, err: BaseException, hook_plugin_id: Optional[str] = None) -> int:
    """Print and toast a failure from a detached command; returns the exit status.

    Pass `hook_plugin_id` from hooks: they can run on every focus change, so a failure that keeps
    coming back toasts once per FAILURE_TOAST_QUIET_SECONDS. It is still printed every time, which
    `herdr plugin log list` shows.
    """
    expected = (HerdrError, ConfigError, OSError, ValueError)
    reason = str(err) if isinstance(err, expected) else "{}: {}".format(type(err).__name__, err)
    print("{}: {}{}".format(tool, "" if isinstance(err, expected) else "unexpected error: ", reason), file=sys.stderr)
    if hook_plugin_id is None or _first_in_a_while(hook_plugin_id, title + "\n" + reason):
        notify(title, reason)
    return 1


def _first_in_a_while(plugin_id: str, message: str) -> bool:
    """True unless the same message was toasted within the quiet period; records this toast."""
    stamp = state_dir(plugin_id) / FAILURE_STAMP_FILE_NAME
    digest = hashlib.sha256(message.encode()).hexdigest()
    now = time.time()
    try:
        last = json.loads(stamp.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        last = {}
    if not isinstance(last, dict):
        last = {}
    at = last.get("at")
    # A stamp from the future (the clock went back) or a damaged one never silences a toast.
    recent = isinstance(at, (int, float)) and 0 <= now - at < FAILURE_TOAST_QUIET_SECONDS
    if last.get("digest") == digest and recent:
        return False
    try:
        stamp.parent.mkdir(parents=True, exist_ok=True)
        stamp.write_text(json.dumps({"digest": digest, "at": now}), encoding="utf-8")
    except OSError as err:
        print("could not record the failure toast: {}".format(err), file=sys.stderr)
    return True
