#!/usr/bin/env python3
"""Release helper for the herdr-publish skill: where each plugin stands, whether it is fit to publish,
and its release notes. Read-only: it never commits, tags, fetches or pushes.

  herdr_release.py status [plugin...] [--json]
  herdr_release.py preflight [plugin...] [--no-tests] [--schema-file PATH] [--python PATH] [--json]
  herdr_release.py notes <plugin> [--version X.Y.Z]

Global options (before the command): -C DIR (repository, default: cwd), --index URL|PATH (default:
$HERDR_PLUGIN_INDEX or the live marketplace index), --no-index, --now ISO-8601 (tests).
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, List, Optional, Tuple

import release_index as ri
import release_notes
import release_preflight as rp
import release_render as render
import release_status as rs
from release_git import Git, GitError

SYSTEM_PYTHON = "/usr/bin/python3"


def main(argv: Optional[List[str]] = None) -> int:
    args = _parser().parse_args(argv)
    now = ri.parse_time(args.now) if args.now else datetime.now(timezone.utc)
    if now is None:
        print("--now must be ISO-8601, e.g. 2026-10-14T14:00:00Z", file=sys.stderr)
        return 2
    try:
        git = Git(Path(args.C))
        return args.handler(args, git, now)
    except (GitError, rs.StatusError) as exc:
        print("herdr_release: {} (git repository with a GitHub origin required)".format(exc), file=sys.stderr)
        return 2


def _status(args: argparse.Namespace, git: Git, now: datetime) -> int:
    index, error = _index(args)
    report = rs.build(git, args.plugins, index, now, error)
    print(_json(report) if args.json else render.status(report, now))
    return 0


def _preflight(args: argparse.Namespace, git: Git, now: datetime) -> int:
    index, _ = _index(args)
    herdr = os.environ.get("HERDR_BIN_PATH") or shutil.which("herdr") or "herdr"
    events, note = rp.load_schema_events(args.schema_file, herdr)
    python = args.python or (SYSTEM_PYTHON if Path(SYSTEM_PYTHON).exists() else sys.executable)
    report = rp.run(git, args.plugins, index, events, python, not args.no_tests, note)
    print(_json(report) if args.json else render.preflight(report))
    return 0 if report.ok else 1


def _notes(args: argparse.Namespace, git: Git, now: datetime) -> int:
    status = rs.build(git, [args.plugin], None, now).plugins[0]
    version = args.version or status.next_version or status.manifest_version or "?"
    if status.last_tag is None:
        print(release_notes.render_first(args.plugin, version, status.description), end="")
    else:
        print(release_notes.render(args.plugin, version, status.commits), end="")
    return 0


def _index(args: argparse.Namespace) -> Tuple[Optional[dict], Optional[str]]:
    if args.no_index:
        return None, "skipped (--no-index)"
    source = args.index or os.environ.get("HERDR_PLUGIN_INDEX") or ri.DEFAULT_URL
    try:
        return ri.load(source), None
    except ri.IndexLoadError as exc:
        return None, str(exc)


def _json(report: Any) -> str:
    data = asdict(report)
    if hasattr(report, "ok"):
        data["ok"] = report.ok
    return json.dumps(data, indent=2, default=lambda value: value.isoformat() if isinstance(value, datetime) else str(value))


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="herdr_release.py", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("-C", default=".", metavar="DIR", help="repository to inspect (default: cwd)")
    parser.add_argument("--index", help="marketplace index URL or file")
    parser.add_argument("--no-index", action="store_true", help="do not read the marketplace index")
    parser.add_argument("--now", help=argparse.SUPPRESS)
    commands = parser.add_subparsers(dest="command", required=True)

    status = commands.add_parser("status", help="releases, unreleased changes, suggested bumps, listing")
    status.add_argument("plugins", nargs="*", metavar="plugin")
    status.add_argument("--json", action="store_true")
    status.set_defaults(handler=_status)

    preflight = commands.add_parser("preflight", help="marketplace eligibility, repo conventions, tests")
    preflight.add_argument("plugins", nargs="*", metavar="plugin")
    preflight.add_argument("--no-tests", action="store_true", help="skip running each plugin's tests")
    preflight.add_argument("--schema-file", help="saved `herdr api schema --json`; '' skips the event check")
    preflight.add_argument("--python", help="interpreter for the tests (default: {})".format(SYSTEM_PYTHON))
    preflight.add_argument("--json", action="store_true")
    preflight.set_defaults(handler=_preflight)

    notes = commands.add_parser("notes", help="release notes for the tag message")
    notes.add_argument("plugin")
    notes.add_argument("--version", help="version to title the notes with (default: the suggested one)")
    notes.set_defaults(handler=_notes)
    return parser


if __name__ == "__main__":
    sys.exit(main())
