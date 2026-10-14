# herdr-tools

Small tools that extend the Herdr terminal multiplexer through its CLI and socket API.

## Conventions

- One folder per tool (`<tool-name>/`), with its tests next to the code (`test_*.py`).
- Python standard library only, compatible with `/usr/bin/python3` (3.9): tools run from Herdr
  keybindings and must not depend on a virtualenv or Homebrew Python.
- Talk to Herdr through `$HERDR_BIN_PATH` / `$HERDR_SOCKET_PATH` when set; the raw socket protocol is
  newline-delimited JSON (`herdr api schema --json` prints the schema for the installed binary).
- Every tool is listed in `README.md` with its key binding and the `config.toml` snippet that wires it.
- Run tests from the tool folder: `/usr/bin/python3 -m unittest -v`.

## Git / PR Working Policy
- Worktree usage: enabled
- Worktree location: in-repo, Claude Code default (.claude/worktrees/<branch>/)
- Base branch: main
- Recorded on: 2026-10-14
