# herdr-tools

A public suite of Herdr plugins (MIT, github.com/MrBogomips/herdr-tools). Each plugin installs on its
own with `herdr plugin install MrBogomips/herdr-tools/<plugin>`.

## Conventions

- One folder per plugin (`<plugin>/`): `herdr-plugin.toml`, `README.md`, `config.example.json`, code,
  and its tests next to it (`test_*.py`, including `test_manifest.py`). Plugin id `mrbogomips.<folder>`.
- A plugin folder must stand alone: no imports or files from outside it. `herdr_api.py` and
  `test_herdr_api.py` are vendored, byte-identical in every plugin; change one copy, then copy it to the
  others (CI compares them).
- Python standard library only, compatible with `/usr/bin/python3` (3.9): no `tomllib`, so plugin
  config is JSON in `$HERDR_PLUGIN_CONFIG_DIR/config.json`. Manifest commands start with `python3`.
- Talk to Herdr through `$HERDR_BIN_PATH` / `$HERDR_SOCKET_PATH`; the raw socket protocol is
  newline-delimited JSON (`herdr api schema --json` prints the schema for the installed binary).
- Hooks (`[[startup]]`, `[[events]]`) are silent on success and toast only on failure; actions toast
  their result. Not every event can be hooked: `herdr plugin link` warns about unknown names
  (`pane.updated` and `layout.updated` cannot be hooked on 0.9.3). `pane.agent_status_changed` can,
  and it is the only hook that follows an agent changing folder (into a worktree, say).
- `min_herdr_version` is the oldest version actually verified (`herdr status server` shows the
  running server, which can lag behind the installed binary).
- Every plugin is listed in the root `README.md` table; its own README documents install, key
  binding, config and limits.
- Run tests from the plugin folder: `/usr/bin/python3 -m unittest -v`.
- Test labels and docs use neutral names (ACME, Globex, Initech, Lumon): never real customer names.

## Companions (top-level folders without a manifest, except `site/`)

- A companion works with Herdr from outside it; today only `herdr-jump/`, a Hammerspoon Spoon in Lua.
  It must never contain a `herdr-plugin.toml`: without one, the marketplace index, the plugin CI jobs and
  the `herdr-publish` helper all skip it.
- Lua code stays compatible with Lua 5.4 (Hammerspoon embeds 5.4; Homebrew `lua` can be newer), with no
  dependencies. Logic lives in pure modules (no `hs.*` at load time) with the tests; `init.lua` is glue.
- Tests: `lua herdr-jump/tests/run.lua`. The CI job `lua` runs every `*/tests/run.lua` with `lua5.4`.
- Users install with `herdr-jump/install.sh` (`curl … | sh` from GitHub, POSIX sh, no clone); its tests
  `sh herdr-jump/tests/test_install.sh` stub the system commands and run on `/bin/sh` and dash. The CI
  job `unittest` runs every `*/tests/test_*.sh`. Keep `shellcheck -s sh` clean.
- Listed in the root README "Companions" table. Not released by `herdr-publish`: it ships with `main`;
  an annotated tag `herdr-jump-vX.Y.Z` only when the user asks (`install.sh --ref` pins one).
- Live check: Hammerspoon loads the Spoon through `~/.hammerspoon/Spoons/HerdrJump.spoon`, a symlink to
  the main checkout (point it at a worktree to test a branch, then back); `hs -c 'hs.reload()'` reloads it
  and exits non-zero while the connection drops, which is normal (the `hs` CLI needs `require("hs.ipc")`).
  `install.sh` refuses to replace that symlink unless `--force` is passed.

## Site (`site/`)

- The GitHub Pages site (`https://mrbogomips.github.io/herdr-tools/`), built by `site/build.py`
  (stdlib, 3.9) and published by `.github/workflows/site.yml` on pushes to `main`. Not a companion:
  no manifest and no `tests/` folder, so the plugin and companion CI loops skip it.
- Pages are fragments in `site/pages/` with a leading `<!-- {json} -->` metadata comment, set in
  `site/layout.html`. Versions and palettes come from the manifests, the Spoon and `palettes.py`
  through `{{version:<plugin>}}`-style placeholders, screenshots from each folder's `docs/`: never
  copy them into `site/`.
- `site/assets/js/herd.js` ports Space Herder's sort and colour rules for the playground and the hero
  demo; `site/test_herd.py` checks it against the Python under node. Change both together.
- A new plugin needs `site/pages/<plugin>.html`, a link from the home page and a row in
  `install.html`: `site/test_build.py` fails otherwise.
- Tests: `cd site && /usr/bin/python3 -m unittest -v` (the parity test needs node). Preview with
  `python3 site/build.py && python3 -m http.server -d site/_site`.

## Releasing

- A plugin reaches the Herdr marketplace (herdr.dev/plugins) by landing on `main`: the index lists every
  `herdr-plugin.toml` on the default branch and refreshes about every 30 minutes. There is no submission,
  and `herdr plugin update` hands every push to `main` to users, so `main` must always be releasable.
- Before naming a new plugin, check the index (`https://assets.herdr.dev/plugins/index.json`, which
  refuses requests without a User-Agent) for clashing names and ids: generic names such as "Workspace
  Manager" are often taken by other authors.
- Release with the `herdr-publish` skill (`.claude/skills/herdr-publish/`): a semver bump per plugin
  (breaking changes bump the minor while 0.x) and an annotated tag `<plugin>-vX.Y.Z` carrying the notes,
  pushed with `git push --atomic origin main <tag>`. Never push `--tags`, force, or move a pushed tag.
- Never commit a `herdr-plugin.toml` outside a top-level plugin folder, test fixtures included: the index
  would list it as a plugin.
- Commits, tags and PR bodies carry no tool attribution or trailers.

## Working documents

- Specs, drafts, eval workspaces and sandboxes go in `.work/` at the repo root, excluded locally through
  `.git/info/exclude` (not `.gitignore`); nothing there is committed.

## Herdr documentation

- Official docs: https://herdr.dev/docs/ (human-facing HTML).
- For agents, start from the LLM index https://herdr.dev/llms.txt: one line per page, linking raw sources
  pinned to the current stable release. Open only the pages the task needs; for plugin work these are
  Plugins, Socket API, CLI reference and Marketplace. Don't follow `/docs/` links found inside a page.
- Bundles: `llms-small.txt` (abridged), `llms-full.txt` (complete, ~340 KB), `llms-preview.txt` (preview
  channel only), all under https://herdr.dev/. The config reference is a large JSON file: filter it by
  key with `jq` (as `llms.txt` shows) instead of loading it whole.
- The docs follow the latest stable release, which can be newer than `min_herdr_version`: check a
  feature against the version you target (`herdr api schema --json`).

## Git / PR Working Policy
- Worktree usage: enabled (features and multi-file work, merged through a PR)
- Trivial work (doc tweaks, typos, single-line fixes): commit directly to main and push
- Worktree location: in-repo, Claude Code default (.claude/worktrees/<branch>/)
- Base branch: main
- Recorded on: 2026-10-14
