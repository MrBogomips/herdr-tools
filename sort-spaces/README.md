# sort-spaces

Sorts the Herdr spaces sidebar into groups, then by name: on demand from a key binding, or by
itself right after a space is created or renamed.

```
~                 home, always first
LUMON +           head group: name ends with " +"
ACME - api        default group, by name ignoring case
ACME - web
Globex - etl
SYS -             bottom group: name ends with " -"
```

Herdr has no sort setting for spaces: they keep the order you give them by dragging. This plugin
reorders all spaces at once with the socket method `workspace.move_block`. The focused space stays
focused, worktree children stay under their parent, and running it on a sorted list changes
nothing. Space numbers and next/previous-space navigation follow the new order.

## Install

```bash
herdr plugin install MrBogomips/herdr-tools/sort-spaces
```

Then bind a key in `~/.config/herdr/config.toml` and run `herdr server reload-config`:

```toml
[[keys.command]]
key = "prefix+shift+s"
type = "plugin_action"
command = "mrbogomips.sort-spaces.sort"
description = "sort spaces: ~, head (+), default, bottom (-)"
```

The manual sort reports its result as a Herdr toast: "Spaces sorted", "Spaces already sorted", or
"Space sort failed" with the reason.

## Groups

A suffix in the space name chooses its group. Groups are sorted in this order, and inside each
group spaces sort by name with the suffix removed, ignoring case:

| Group | Name convention | Example |
| --- | --- | --- |
| home | the name `~` | `~` (always first) |
| head | ends with a space and `+` | `LUMON +` |
| default | no suffix | `ACME - api` |
| bottom | ends with a space and `-` | `SYS -` |

The space before the suffix is required, so names like `C++` or `ACME - api` stay in the default
group. Worktree children follow their parent's group. To move a space, rename it (for example to
`LUMON +`); with autosort on it moves at once, otherwise press the sort key.

## Autosort

Autosort is off until you turn it on. Create `config.json` in the plugin's config directory
(`herdr plugin config-dir mrbogomips.sort-spaces` prints it):

```json
{
  "auto_sort": "both"
}
```

| `auto_sort` | Sorts after |
| --- | --- |
| `"off"` (default) | nothing: only the key binding sorts |
| `"created"` | a space is created (including a new worktree space) |
| `"renamed"` | a space is renamed |
| `"both"` | either |

Autosort runs from the plugin's `workspace.created` and `workspace.renamed` hooks. It stays silent
when it works and shows a toast only when sorting fails. The setting is read on every event, so
changes apply at once. A space nobody named shows its folder name; following its folder with `cd`
is not a rename, so it does not trigger a sort.

## Command line

From a terminal inside Herdr:

```bash
python3 sort_spaces.py --dry-run   # print the current and the target order only
python3 sort_spaces.py             # sort now
```

It talks to `$HERDR_SOCKET_PATH` (set inside Herdr panes, key commands and plugins), falling back
to `~/.config/herdr/herdr.sock`. Without the plugin you can still bind the script directly with a
`type = "shell"` key command.

## Troubleshooting

- `herdr plugin log list --plugin mrbogomips.sort-spaces` shows every hook and action run with its
  output.
- If spaces are created or closed while a sort runs, the sort starts over (up to three times)
  before it reports a failure.

## Tests

```bash
cd sort-spaces && python3 -m unittest -v
```
