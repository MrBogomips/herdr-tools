# herdr-tools

Small tools for the [Herdr](https://herdr.dev) terminal multiplexer, built on its CLI and socket API.
Python standard library only; each tool runs with the system `/usr/bin/python3`.

| Tool | What it does | Key |
| --- | --- | --- |
| [sort-spaces](sort-spaces/) | Sorts the spaces sidebar into head / default / bottom groups (name suffix), then by name | `prefix+shift+s` |

## sort-spaces

Herdr has no sort setting for spaces: they keep the order you give them by dragging. This tool
reorders all spaces at once with the socket method `workspace.move_block`. The focused space
stays focused, worktree children stay under their parent, and running it again on a sorted list
changes nothing. A Herdr toast reports the result ("Spaces sorted", "Spaces already sorted", or
"Space sort failed" with the reason).

### Groups

A suffix in the space name chooses its group. Groups are sorted in this order, and inside each
group spaces sort by name with the suffix removed, ignoring case:

| Group | Name convention | Example |
| --- | --- | --- |
| home | the name `~` | `~` (always first) |
| head | ends with a space and `+` | `LAB +` |
| default | no suffix | `ACME - API` |
| bottom | ends with a space and `-` | `SYS -` |

The space before the suffix is required, so names like `C++` or `ACME - API` stay in the
default group. Worktree children follow their parent's group. To move a space, rename it
(`prefix+shift+w`), for example to `LAB +`, then press `prefix+shift+s`.

Wire it in `~/.config/herdr/config.toml`, then run `herdr server reload-config`:

```toml
[[keys.command]]
key = "prefix+shift+s"
type = "shell"
command = "/usr/bin/python3 /path/to/herdr-tools/sort-spaces/sort_spaces.py"
description = "sort spaces: ~, head (+), default, bottom (-)"
```

From a terminal inside Herdr:

```bash
/usr/bin/python3 sort-spaces/sort_spaces.py --dry-run   # print current and target order only
/usr/bin/python3 sort-spaces/sort_spaces.py             # sort now
```

It uses `$HERDR_SOCKET_PATH` (set inside Herdr panes and key commands), falling back to
`~/.config/herdr/herdr.sock`. Space numbers and next/previous-space navigation follow the new order.

Tests: `cd sort-spaces && /usr/bin/python3 -m unittest -v`
