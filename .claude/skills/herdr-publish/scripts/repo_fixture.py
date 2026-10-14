"""Throwaway plugin repositories for the tests, isolated from the user's git configuration.

Each TempRepo is a main checkout whose origin is a GitHub URL rewritten (url.<bare>.insteadOf) to a
local bare repository, the same trick the eval sandbox uses: pushes stay on disk.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Dict, Iterable, Mapping, Optional
from unittest import mock

TOP_LEVEL = {
    "id": "acme.sorter",
    "name": "Sorter",
    "version": "0.1.0",
    "min_herdr_version": "0.9.3",
    "description": "Sort things.",
    "platforms": ["macos", "linux"],
}

TABLES = """
[[actions]]
id = "sort"
title = "Sort"
command = ["python3", "sorter.py"]

[[events]]
on = "workspace.created"
command = ["python3", "sorter.py", "--hook"]
"""

PASSING_TEST = """import unittest


class SmokeTest(unittest.TestCase):
    def test_runs(self):
        self.assertTrue(True)
"""

FAILING_TEST = PASSING_TEST.replace("assertTrue(True)", "assertTrue(False)")


def render_manifest(
    overrides: Optional[Mapping[str, object]] = None, drop: Iterable[str] = (), tables: str = TABLES
) -> str:
    """Manifest text from TOP_LEVEL plus overrides; json.dumps writes TOML-compatible strings and arrays."""
    top = dict(TOP_LEVEL)
    top.update(overrides or {})
    for key in drop:
        top.pop(key, None)
    lines = ["{} = {}".format(key, json.dumps(value)) for key, value in top.items()]
    return "\n".join(lines) + "\n" + tables


def git(cwd: Path, *args: str) -> str:
    result = subprocess.run(["git", *args], cwd=str(cwd), check=True, capture_output=True, text=True)
    return result.stdout.strip()


class TempRepo:
    def __init__(self, slug: str = "ACME/plugins") -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="herdr-release-test-")).resolve()
        home = self.tmp / "home"
        home.mkdir()
        (home / ".gitconfig").write_text("", encoding="utf-8")
        self._env = mock.patch.dict(
            os.environ,
            {
                "HOME": str(home),
                "GIT_CONFIG_NOSYSTEM": "1",
                "GIT_CONFIG_GLOBAL": str(home / ".gitconfig"),
                "GIT_AUTHOR_NAME": "Test",
                "GIT_AUTHOR_EMAIL": "test@example.com",
                "GIT_COMMITTER_NAME": "Test",
                "GIT_COMMITTER_EMAIL": "test@example.com",
            },
        )
        self._env.start()
        self.slug = slug
        self.url = "https://github.com/{}.git".format(slug)
        self.bare = self.tmp / "origin.git"
        self.root = self.tmp / "repo"
        git(self.tmp, "init", "-q", "--bare", "-b", "main", str(self.bare))
        git(self.tmp, "init", "-q", "-b", "main", str(self.root))
        for key, value in (("commit.gpgsign", "false"), ("tag.gpgsign", "false")):
            self.git("config", key, value)
        self.git("remote", "add", "origin", self.url)
        self.git("config", "url.{}.insteadOf".format(self.bare), self.url)

    def close(self) -> None:
        self._env.stop()
        shutil.rmtree(str(self.tmp), ignore_errors=True)

    def git(self, *args: str) -> str:
        return git(self.root, *args)

    def write(self, relpath: str, text: str) -> None:
        path = self.root / relpath
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def remove(self, relpath: str) -> None:
        (self.root / relpath).unlink()

    def commit(self, message: str, files: Optional[Dict[str, str]] = None) -> str:
        for relpath, text in (files or {}).items():
            self.write(relpath, text)
        self.git("add", "-A")
        self.git("commit", "-q", "--allow-empty", "-m", message)
        return self.git("rev-parse", "HEAD")

    def tag(self, name: str, rev: str = "HEAD", annotated: bool = True) -> None:
        if annotated:
            self.git("tag", "-a", name, "-m", name, rev)
        else:
            self.git("tag", name, rev)

    def push(self, *refs: str) -> None:
        self.git("push", "-q", "origin", "main", *refs)

    def add_plugin(
        self, folder: str, manifest: Optional[str] = None, extra: Optional[Dict[str, str]] = None
    ) -> None:
        """A plugin folder following the repo conventions, plus its README row."""
        owner, name = self.slug.split("/")
        files = {
            "{}/herdr-plugin.toml".format(folder): manifest
            or render_manifest({"id": "{}.{}".format(owner.lower(), folder)}),
            "{}/README.md".format(folder): "# {}\n".format(folder),
            "{}/config.example.json".format(folder): '{"mode": "off"}\n',
            "{}/sorter.py".format(folder): "print('sort')\n",
            "{}/herdr_api.py".format(folder): "API = 1\n",
            "{}/test_herdr_api.py".format(folder): PASSING_TEST,
            "{}/test_sorter.py".format(folder): PASSING_TEST,
        }
        files.update(extra or {})
        for relpath, text in files.items():
            self.write(relpath, text)
        readme = self.root / "README.md"
        rows = readme.read_text(encoding="utf-8") if readme.exists() else (
            "# plugins\n\n| Plugin | What it does | Install |\n| --- | --- | --- |\n"
        )
        rows += "| [{f}]({f}/) | Does {f} things | `herdr plugin install {o}/{n}/{f}` |\n".format(
            f=folder, o=owner, n=name
        )
        self.write("README.md", rows)
