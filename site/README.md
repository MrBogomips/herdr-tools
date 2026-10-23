# herdr-tools site

The source of <https://mrbogomips.github.io/herdr-tools/>: a static site that presents the plugins and
herdr-jump, with an animated session in the hero and a playground that sorts and colours the
visitor's own space names with Space Herder's rules.

No dependencies: `build.py` uses the Python standard library (3.9 or newer), the pages are plain
HTML, CSS and JavaScript, and the fonts are served from the site itself.

## Build and preview

```bash
python3 site/build.py                        # builds into site/_site (ignored by git)
python3 -m http.server -d site/_site 8000    # then open http://localhost:8000
```

`build.py OUT` builds into another folder. It only replaces a folder it built itself.

## Layout

| Path | What it holds |
| --- | --- |
| `layout.html` | The page frame: head, navigation, footer. `${...}` fields are filled per page |
| `pages/*.html` | One fragment per page, starting with a `<!-- {"title": ..., "description": ...} -->` comment; `"scripts"` lists the page's own scripts |
| `assets/css/site.css` | Ink (dark) and paper (light) themes, after the herdr.dev look |
| `assets/js/herd.js` | Space Herder's sort and colour rules, ported for the browser |
| `assets/js/demo.js`, `playground.js` | The home page's animated session and its "try it" section |
| `assets/js/site.js` | The ink/paper switch, copy buttons and the palette swatches |
| `assets/fonts/` | Archivo, Inter and JetBrains Mono (latin subsets), under the SIL Open Font License in `OFL.txt` |

## Single sources

The site keeps no second copy of what the plugins already hold:

- Screenshots are copied at build time from `space-herder/docs/` and `herdr-jump/docs/` into `img/`.
- `assets/js/palettes.js` is generated from `space-herder/palettes.py`.
- `{{version:<plugin>}}`, `{{min_herdr:<plugin>}}` and `{{palette_count}}` in a page are filled from
  the manifests, the Spoon's `obj.version` (`{{version:herdr-jump}}`) and the palettes. An unknown
  placeholder fails the build.

## Tests

```bash
cd site && python3 -m unittest -v
```

- `test_build.py`: every page builds with a title, a description and a canonical URL, every local
  link and anchor resolves, nothing loads from another host, and every plugin of the repository has
  its page, a link from the home page and its install line.
- `test_herd.py`: `herd.js`, run under node, sorts and colours like Space Herder's Python for every
  palette, in hash and sticky mode. Skipped when node is missing; CI has it.

## Deploy

`.github/workflows/site.yml` tests, builds and publishes the site on every push to `main` that touches
it, the manifests, the screenshots or the palettes. GitHub Pages must use "GitHub Actions" as its source.

The customer names in the demos are fictional (ACME, Globex, Initech, Lumon). Bogoware is the author's
brand, named in the footer; it is not covered by the MIT license.
