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
  (`pane.updated` and `layout.updated` cannot be hooked on 0.9.3).
- `min_herdr_version` is the oldest version actually verified (`herdr status server` shows the
  running server, which can lag behind the installed binary).
- Every plugin is listed in the root `README.md` table; its own README documents install, key
  binding, config and limits.
- Run tests from the plugin folder: `/usr/bin/python3 -m unittest -v`.
- Test labels and docs use neutral names (ACME, Globex, Initech, Lumon): never real customer names.

## Git / PR Working Policy
- Worktree usage: enabled
- Worktree location: in-repo, Claude Code default (.claude/worktrees/<branch>/)
- Base branch: main
- Recorded on: 2026-10-14
