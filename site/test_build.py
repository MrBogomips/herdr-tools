"""The site build: every page renders, every local link and asset resolves, nothing loads from
another host, and every plugin of the repo has its page and its install line."""
from __future__ import annotations

import json
import re
import tempfile
import unittest
from html.parser import HTMLParser
from pathlib import Path
from typing import Dict, List, Set, Tuple

import build

REPO = build.REPO
PAGE_NAMES = {"index.html", "space-herder.html", "auto-tab-name.html", "herdr-jump.html", "install.html", "404.html"}


class PageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.ids: Set[str] = set()
        self.links: List[Tuple[str, str]] = []  # (attribute, value)
        self.titles = 0
        self.meta: Dict[str, str] = {}
        self.canonical = ""
        self.lang = ""

    def handle_starttag(self, tag: str, attrs: List[Tuple[str, str]]) -> None:
        values = {name: value or "" for name, value in attrs}
        if "id" in values:
            self.ids.add(values["id"])
        for name in ("href", "src"):
            if name in values:
                self.links.append((tag + "." + name, values[name]))
        if tag == "title":
            self.titles += 1
        if tag == "html":
            self.lang = values.get("lang", "")
        if tag == "meta" and ("name" in values or "property" in values):
            self.meta[values.get("name") or values["property"]] = values.get("content", "")
        if tag == "link" and values.get("rel") == "canonical":
            self.canonical = values.get("href", "")


def parse(path: Path) -> PageParser:
    parser = PageParser()
    parser.feed(path.read_text(encoding="utf-8"))
    return parser


class BuiltSite(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp = tempfile.TemporaryDirectory()
        cls.out = Path(cls.tmp.name) / "site"
        build.build(cls.out)
        cls.pages = {path.name: parse(path) for path in cls.out.glob("*.html")}

    @classmethod
    def tearDownClass(cls) -> None:
        cls.tmp.cleanup()

    def test_every_page_is_built(self) -> None:
        self.assertEqual(set(self.pages), PAGE_NAMES)

    def test_pages_have_one_title_a_description_and_a_canonical_url(self) -> None:
        for name, page in self.pages.items():
            with self.subTest(page=name):
                self.assertEqual(page.lang, "en")
                self.assertEqual(page.titles, 1)
                self.assertGreater(len(page.meta.get("description", "")), 40)
                self.assertTrue(page.meta.get("og:image", "").startswith(build.SITE_URL))
                expected = build.SITE_URL + ("" if name == "index.html" else name)
                if name != "404.html":
                    self.assertEqual(page.canonical, expected)

    def test_local_links_and_assets_resolve(self) -> None:
        for name, page in self.pages.items():
            for attribute, value in page.links:
                # <base> only re-roots 404.html, which GitHub Pages serves at any depth.
                if attribute == "base.href" or re.match(r"^(https?:|mailto:)", value):
                    continue
                with self.subTest(page=name, link=value):
                    target, _, anchor = value.partition("#")
                    path = (self.out / name).parent / target if target else self.out / name
                    self.assertTrue(path.is_file(), "{} points to a missing file".format(attribute))
                    if anchor and path.suffix == ".html":
                        self.assertIn(anchor, parse(path).ids, "missing #{}".format(anchor))

    def test_nothing_loads_from_another_host(self) -> None:
        for name, page in self.pages.items():
            for attribute, value in page.links:
                # Links may go anywhere; what a page loads (src, <link href>) stays on the site.
                if attribute == "a.href" or value.startswith(build.SITE_URL):
                    continue
                with self.subTest(page=name, link=value):
                    self.assertFalse(re.match(r"^(https?:)?//", value), "{} loads {}".format(attribute, value))

    def test_no_placeholder_is_left(self) -> None:
        for path in self.out.rglob("*.html"):
            text = path.read_text(encoding="utf-8")
            with self.subTest(page=path.name):
                self.assertNotIn("{{", text)

    def test_every_plugin_has_a_page_an_install_line_and_its_version(self) -> None:
        install = (self.out / "install.html").read_text(encoding="utf-8")
        index_links = {value for _, value in self.pages["index.html"].links}
        for plugin in build.plugin_names():
            with self.subTest(plugin=plugin):
                page = (self.out / (plugin + ".html")).read_text(encoding="utf-8")
                self.assertIn(plugin + ".html", index_links)
                self.assertIn("herdr plugin install MrBogomips/herdr-tools/" + plugin, install)
                self.assertIn("herdr plugin install MrBogomips/herdr-tools/" + plugin, page)
                self.assertIn(build.manifest_field(plugin, "version"), page)

    def test_herdr_jump_page_shows_the_spoon_version(self) -> None:
        page = (self.out / "herdr-jump.html").read_text(encoding="utf-8")
        self.assertIn(build.spoon_version(), page)

    def test_plugin_screenshots_are_copied(self) -> None:
        for plugin, folder in build.IMAGE_FOLDERS.items():
            for image in folder.iterdir():
                with self.subTest(image=image.name):
                    self.assertTrue((self.out / "img" / plugin / image.name).is_file())

    def test_palettes_come_from_space_herder(self) -> None:
        text = (self.out / "assets" / "js" / "palettes.js").read_text(encoding="utf-8")
        data = json.loads(re.search(r"=\s*(\{.*\});", text, re.S).group(1))
        self.assertEqual(data, {name: list(colours) for name, colours in build.load_presets().items()})


class BuildRules(unittest.TestCase):
    def test_unknown_placeholder_is_an_error(self) -> None:
        with self.assertRaisesRegex(build.BuildError, "unknown placeholder"):
            build.fill("Space Herder {{version:nope}}")

    def test_refuses_to_replace_a_folder_it_did_not_build(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "keep.txt").write_text("mine", encoding="utf-8")
            with self.assertRaisesRegex(build.BuildError, "not a site build"):
                build.build(Path(tmp))
            self.assertTrue((Path(tmp) / "keep.txt").is_file())

    def test_rebuilds_over_its_own_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "site"
            build.build(out)
            (out / "stale.html").write_text("old", encoding="utf-8")
            build.build(out)
            self.assertFalse((out / "stale.html").exists())

    def test_page_without_metadata_is_an_error(self) -> None:
        with self.assertRaisesRegex(build.BuildError, "metadata"):
            build.split_page("<h1>no metadata</h1>", "x.html")


if __name__ == "__main__":
    unittest.main()
