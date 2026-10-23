"""Build the herdr-tools site: `python3 build.py [OUT]`, by default into `_site` next to this file.

Pages in `pages/` are HTML fragments that start with a JSON metadata comment; each one is set in
`layout.html`. Screenshots come from the plugins' own `docs/` folders and the playground's
palettes from `space-herder/palettes.py`, so the site never keeps a second copy of either.
Placeholders such as `{{version:space-herder}}` are filled from the manifests.
"""
from __future__ import annotations

import html
import importlib.util
import json
import re
import shutil
import sys
from pathlib import Path
from string import Template
from typing import Any, Dict, List, Mapping, Optional, Tuple

SITE = Path(__file__).resolve().parent
REPO = SITE.parent
SITE_URL = "https://mrbogomips.github.io/herdr-tools/"
OG_IMAGE = SITE_URL + "img/space-herder/hero.png"
DEFAULT_OUT = SITE / "_site"
# Written into every build, so a rebuild only ever deletes a folder it made itself.
MARKER = ".herdr-tools-site"
IMAGE_FOLDERS = {
    "space-herder": REPO / "space-herder" / "docs",
    "herdr-jump": REPO / "herdr-jump" / "docs",
}
NAV = (
    ("space-herder.html", "Space Herder"),
    ("auto-tab-name.html", "auto-tab-name"),
    ("herdr-jump.html", "herdr-jump"),
    ("install.html", "Install"),
)
METADATA = re.compile(r"\A\s*<!--\s*(\{.*?\})\s*-->\s*", re.S)
PLACEHOLDER = re.compile(r"\{\{\s*([a-z_]+)(?::([a-z0-9-]+))?\s*\}\}")
SPOON_VERSION = re.compile(r'^obj\.version\s*=\s*"([^"]+)"', re.M)
REQUIRED_METADATA = ("title", "description")


class BuildError(Exception):
    """A page, manifest or output folder the build cannot use; the message says which."""


def manifest_field(plugin: str, field: str) -> str:
    """A top-level string field of a plugin's herdr-plugin.toml (no tomllib on Python 3.9)."""
    path = REPO / plugin / "herdr-plugin.toml"
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as err:
        raise BuildError("{}: {}".format(path, err)) from err
    found = re.search(r'^{}\s*=\s*"([^"]*)"'.format(re.escape(field)), text, re.M)
    if not found:
        raise BuildError("{}: no {} field".format(path, field))
    return found.group(1)


def spoon_version() -> str:
    path = REPO / "herdr-jump" / "HerdrJump.spoon" / "init.lua"
    found = SPOON_VERSION.search(path.read_text(encoding="utf-8"))
    if not found:
        raise BuildError("{}: no obj.version".format(path))
    return found.group(1)


def load_presets() -> Dict[str, Tuple[str, ...]]:
    """Space Herder's preset palettes, loaded from its palettes.py by path."""
    path = REPO / "space-herder" / "palettes.py"
    spec = importlib.util.spec_from_file_location("space_herder_palettes", path)
    if spec is None or spec.loader is None:
        raise BuildError("{}: cannot be loaded".format(path))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return dict(module.PRESETS)


def plugin_names() -> List[str]:
    return sorted(manifest.parent.name for manifest in REPO.glob("*/herdr-plugin.toml"))


def placeholder_value(name: str, argument: Optional[str]) -> str:
    if name == "version" and argument == "herdr-jump":
        return spoon_version()
    if name == "version" and argument in plugin_names():
        return manifest_field(argument, "version")
    if name == "min_herdr" and argument in plugin_names():
        return manifest_field(argument, "min_herdr_version")
    if name == "palette_count" and argument is None:
        return str(len(load_presets()))
    raise BuildError("unknown placeholder {{{{{}{}}}}}".format(name, ":" + argument if argument else ""))


def fill(text: str) -> str:
    return PLACEHOLDER.sub(lambda match: placeholder_value(match.group(1), match.group(2)), text)


def split_page(text: str, name: str) -> Tuple[Dict[str, Any], str]:
    """(metadata, body) of a page: the body follows a leading `<!-- {json} -->` comment."""
    found = METADATA.match(text)
    if not found:
        raise BuildError("{}: missing the <!-- {{...}} --> metadata comment".format(name))
    try:
        meta = json.loads(found.group(1))
    except ValueError as err:
        raise BuildError("{}: bad metadata: {}".format(name, err)) from err
    missing = [key for key in REQUIRED_METADATA if not meta.get(key)]
    if missing:
        raise BuildError("{}: metadata lacks {}".format(name, ", ".join(missing)))
    return meta, text[found.end():]


def nav_links(current: str) -> str:
    items = []
    for href, label in NAV:
        current_attr = ' aria-current="page"' if href == current else ""
        items.append('<a href="{}"{}>{}</a>'.format(href, current_attr, label))
    return "\n        ".join(items)


def render(name: str, meta: Mapping[str, Any], body: str, layout: Template) -> str:
    url = SITE_URL + ("" if name == "index.html" else name)
    is_404 = name == "404.html"
    scripts = "\n".join('  <script src="assets/js/{}" defer></script>'.format(js) for js in meta.get("scripts", []))
    return layout.substitute(
        title=html.escape(meta["title"]),
        description=html.escape(meta["description"]),
        # 404.html is served for any missing path, however deep: anchor its relative links.
        base='\n  <base href="/herdr-tools/">' if is_404 else "",
        canonical="" if is_404 else '\n  <link rel="canonical" href="{}">'.format(url),
        url=url,
        og_image=OG_IMAGE,
        page=name[: -len(".html")],
        nav=nav_links(name),
        content=fill(body),
        scripts=scripts,
    )


def prepare(out: Path) -> None:
    """Empty `out` for a new build, refusing to touch a folder the build did not make."""
    if out.exists():
        if not out.is_dir() or (any(out.iterdir()) and not (out / MARKER).is_file()):
            raise BuildError("{} is not a site build; pick an empty or new folder".format(out))
        shutil.rmtree(out)
    out.mkdir(parents=True)
    (out / MARKER).write_text("built by site/build.py\n", encoding="utf-8")
    (out / ".nojekyll").write_text("", encoding="utf-8")


def write_palettes(out: Path) -> None:
    palettes = {name: list(colours) for name, colours in sorted(load_presets().items())}
    script = "/* Generated by site/build.py from space-herder/palettes.py. */\nwindow.PALETTES = {};\n"
    (out / "assets" / "js" / "palettes.js").write_text(script.format(json.dumps(palettes)), encoding="utf-8")


def build(out: Path) -> List[Path]:
    """Build the whole site into `out`; returns the pages written."""
    layout = Template((SITE / "layout.html").read_text(encoding="utf-8"))
    prepare(out)
    shutil.copytree(SITE / "assets", out / "assets")
    write_palettes(out)
    for plugin, folder in IMAGE_FOLDERS.items():
        shutil.copytree(folder, out / "img" / plugin)
    written = []
    for source in sorted((SITE / "pages").glob("*.html")):
        meta, body = split_page(source.read_text(encoding="utf-8"), source.name)
        target = out / source.name
        target.write_text(render(source.name, meta, body, layout), encoding="utf-8")
        written.append(target)
    return written


def main(argv: List[str]) -> int:
    out = Path(argv[0]).resolve() if argv else DEFAULT_OUT
    try:
        pages = build(out)
    except BuildError as err:
        print("build failed: {}".format(err), file=sys.stderr)
        return 1
    print("built {} pages into {}".format(len(pages), out))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
