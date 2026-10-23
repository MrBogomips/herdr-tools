# space-colors

Colours the names in Herdr's spaces sidebar, so every space of one customer gets the same colour,
and replaces Herdr's new-space and rename prompts with dialogs that show the result as you type.

<img src="docs/sidebar.png" alt="Herdr spaces sidebar: ACME - api, its feature-checkout worktree and ACME - web in blue, Initech in mauve, Globex in teal, LUMON in red, SYS in peach" width="300" align="right">

Name your spaces `CUSTOMER - project` and the colour follows the customer: on the right, every
`ACME` space is blue, worktree included, and both Initech spaces are mauve (Catppuccin palette,
sticky mode). Together with [sort-spaces](../sort-spaces/) the spaces of one customer also sit
next to each other, with `LUMON +` pinned on top and `SYS -` at the bottom.

- **Stable colours:** a customer gets the same colour on every machine, or in sticky mode the
  least-used one, so customers stay apart.
- **15 colours** from nine preset palettes, or your own.
- **[Dialogs](#dialogs)** to create and rename spaces with a live preview of the sorted, coloured
  sidebar, and to pick a customer's colour yourself.

<br clear="right">

<img src="docs/new-space.gif" alt="The new-space dialog: a folder is picked from the recent ones, the name Initech - billing is typed, the head group moves it to the top of the preview, mauve is picked and both Initech spaces turn mauve, then Enter creates the space at the top of the sidebar" width="100%">

## How the colour is chosen

1. **Rules first.** Each rule is a regular expression matched against the space name; the first
   one that matches picks the colour.
2. **Then a colour chosen in a dialog.** The [new-space and rename dialogs](#dialogs) can give a
   key a palette colour of your choice.
3. **Otherwise the key's colour.** The key is part of the name, by default the text before the
   first `" -"` (`ACME - api` → `ACME`). Two ways to turn it into a colour (`assign`):
   - `"hash"` (default): a stable hash (SHA-256) of the key picks a palette colour. The same
     customer gets the same colour on every machine, with nothing stored.
   - `"sticky"`: a new key starts from its hash colour but takes the least-used colour instead
     when that one is taken, and keeps it from then on. No two customers share a colour until
     there are more customers than colours.
4. **Worktree children** take their parent's colour, so a repo's checkouts match it.

Before the key is taken, the name is normalized: whitespace runs count as one space, case is
ignored, and the sort-spaces markers ` +` / ` -` at the end are dropped, so `ACME +` and
`ACME - api` share a colour.

With hashing, two customers share a colour more often than intuition says: with 15 colours, the
odds that some pair of 6 customers clashes are about 2 in 3. Use `"assign": "sticky"`, or pin a
customer to a colour with a rule.

## Install

1. Install the plugin:

   ```bash
   herdr plugin install MrBogomips/herdr-tools/space-colors
   ```

2. Optionally pick a palette, sticky mode and rules in `config.json` (see
   [Configuration](#configuration)).
3. Generate the sidebar rows:

   ```bash
   herdr plugin action invoke mrbogomips.space-colors.snippet
   ```

   It writes `sidebar-rows.toml` next to `config.json` and shows the path in a toast.
4. In `~/.config/herdr/config.toml`, set `rows` of your `[ui.sidebar.spaces]` table to the value
   from that file. Keep the table's other keys, such as `row_gap`; add the table if you have none.
   **Never paste a second `[ui.sidebar.spaces]` table**: a duplicate table makes the whole config
   invalid and Herdr falls back to its defaults, key bindings included.
5. Check, then reload:

   ```bash
   herdr config check && herdr server reload-config
   ```

The rows replace the built-in `workspace` token of the first space row with one token per colour
(`$spc0`, `$spc1`, …), each with its own foreground:

```toml
[ui.sidebar.spaces]
rows = [
  [
    "state_icon",
    { token = "$spc0", fg = "#f38ba8" },
    { token = "$spc1", fg = "#fab387" },
    # … one entry per colour
  ],
  ["branch", "git_status"],
]
```

The plugin writes each space's name into exactly one of those tokens, so the name shows in its
colour; Herdr hides the empty ones.

**Generate the rows again after changing the palette, `palette_size` or a rule's colour**, since
the colours live in `config.toml`. The first comment line carries a fingerprint of the colours, so
you can tell whether the rows in your config are current.

## Dialogs

Herdr's own "new space" and "rename space" prompts ask only for a name. The plugin's dialogs open
in a popup and show the result while you type: the name with its sort-spaces group suffix, and
the sidebar as it will look, with the space in its place and in its colour.

<img src="docs/new-space.png" alt="The new-space dialog over a Herdr layout: folder ~/git/initech-crm, name Initech - billing becoming Initech - billing + in the head group, mauve picked in the colour row, and a sidebar preview with Initech - billing + at the top and both Initech spaces in mauve" width="100%">

| Field | Keys | What it does |
| --- | --- | --- |
| Folder (new space only) | type, `Tab` completes, `↑` `↓` pick a suggestion | Where the space starts. It opens on the folder of the focused pane; suggestions are the folders you used in this dialog, the folders of open panes and, when [zoxide](https://github.com/ajeetdsouza/zoxide) is installed, its best-ranked ones |
| Name | type, `Backspace`, `Ctrl+W`, `Ctrl+U` | Empty for a new space: Herdr names it after the folder. Ending it with ` +` or ` -` picks the group |
| Group | `←` `→`, `+` `-` `=` | head (` +`), default, or bottom (` -`), as [sort-spaces](../sort-spaces/) orders them. The name `~` is the home space, always first |
| Colour | `←` `→`, `a` for auto | A palette colour for **every space of the key** (`ACME` for `ACME - api`), or auto for the hash or sticky colour |

`Tab` and `Shift+Tab` move between fields (in Folder, `Tab` first completes the path, or lists
the matching folders when there are several), `Enter` creates or renames, `Esc` cancels. A pasted
path is typed in as is: its newline doesn't submit the form. Rename works on the space the key was pressed in.

Bind the two actions to Herdr's keys and move the built-in prompts elsewhere, then run
`herdr config check && herdr server reload-config`:

```toml
[keys]
new_workspace = "prefix+ctrl+n"    # Herdr's own prompts, still reachable
rename_workspace = "prefix+ctrl+w"

[[keys.command]]
key = "prefix+shift+n"
type = "plugin_action"
command = "mrbogomips.space-colors.new-space"
description = "new space: folder, name, group, colour"

[[keys.command]]
key = "prefix+shift+w"
type = "plugin_action"
command = "mrbogomips.space-colors.rename-space"
description = "rename space: name, group, colour"
```

The dialog does not sort the sidebar itself: with sort-spaces' `"auto_sort": "both"` the space
moves to the place shown at once; otherwise press the sort key.

### Chosen colours

<img src="docs/rename.png" alt="The rename dialog on ACME - api: blue is picked in the colour row, and the sidebar preview shows ACME - api, its feature-checkout worktree and ACME - web all in blue" width="100%">

A colour picked in a dialog is saved for the key in `overrides.json` in the plugin state directory
and kept until you set the key back to auto. It beats the hash and sticky colours, and in sticky
mode new customers avoid it; a rule still beats it, so when a rule matches the name the Colour
field shows the rule instead. Worktree children follow their parent and can't pick a colour. Only
palette colours can be picked, since each colour needs its own row slot in `config.toml`; a saved
colour that leaves the palette is ignored.

## Configuration

`config.json` lives in the plugin's config directory (`herdr plugin config-dir
mrbogomips.space-colors`). Every key is optional; an unknown key is an error.
[config.example.json](config.example.json) uses all of them:

```json
{
  "palette": "dracula",
  "palette_size": 13,
  "assign": "sticky",
  "key": "prefix",
  "separator": " -",
  "ignore_case": true,
  "ignore_suffixes": [" +", " -"],
  "marker": "▌",
  "worktrees_follow_parent": true,
  "rules": [
    {"match": "^~$", "color": null},
    {"match": "^Lumon\\b", "color": "#e0e0e0"},
    {"match": "^Initech\\b", "color": 4}
  ]
}
```

| Key | Default | Meaning |
| --- | --- | --- |
| `palette` | `"catppuccin"` | A preset name, or your own list of `#RGB` / `#RRGGBB` colours |
| `palette_size` | `null` (all) | Use only the first N colours of the palette, to leave slots for rule colours |
| `assign` | `"hash"` | `"hash"` or `"sticky"`, see [How the colour is chosen](#how-the-colour-is-chosen) |
| `key` | `"prefix"` | What picks the colour: `"prefix"` (before the first separator), `"suffix"` (after the last), or `"whole"` |
| `separator` | `" -"` | Splits prefix from suffix. A name without it, or with an empty side, uses the whole name |
| `ignore_case` | `true` | `ACME` and `acme` share a colour; rules match ignoring case too |
| `ignore_suffixes` | `[" +", " -"]` | Endings dropped before the key is taken (the sort-spaces group markers) |
| `marker` | `"▌"` | Drawn before the name in the same colour, as a swatch. `""` for none, `"● "` for a dot |
| `worktrees_follow_parent` | `true` | Worktree children use their parent's colour |
| `rules` | `[]` | `{"match": "<regex>", "color": ...}`, checked in order before the key's colour |

A rule's `color` is a hex colour, a palette index (`0` is the first colour), or `null` for the
default text colour. Regular expressions use Python syntax and match anywhere in the name; anchor
them with `^` and `$`.

**Slots.** A sidebar row holds 16 tokens and the agent-state dot takes one, so 15 colours fit.
The palette uses one slot per colour; a rule colour that is not in the palette takes one more, and
`null` takes one for all such rules. Most presets already use 14 or 15 slots, so to add rule
colours or `null`, lower `palette_size` (the example keeps 13 Dracula colours for one extra
colour and `null`). Rules that use palette colours or indices need no slot. The error message
says how far to lower it.

The config is read on every run. After editing it, run
`herdr plugin action invoke mrbogomips.space-colors.recolor`, and generate the sidebar rows again
if colours changed. To bind an action to a key:

```toml
[[keys.command]]
key = "prefix+shift+c"
type = "plugin_action"
command = "mrbogomips.space-colors.recolor"
description = "recolour spaces"
```

### Sticky assignments

Sticky mode remembers each key's colour in `assignments.json` in the plugin state directory
(`~/.local/state/herdr/plugins/mrbogomips.space-colors/`). Palette colours that rules pin to open
spaces count as taken, so a new customer avoids them too. A key not seen for 90 days is forgotten,
so the folder names of unnamed spaces do not pile up. A remembered colour that is no longer in the
palette is assigned again. Delete the file to deal the colours afresh.

## Palettes

Accent colours of popular themes. Themes with extra shades of their own (bright and dim variants,
secondary accents) use them, up to the 15 colours a row can hold; the most distinct colours come
first, so a smaller `palette_size` keeps those. `python3 space_colors.py palettes` prints them.

| Preset | Colours |
| --- | --- |
| `catppuccin` (Mocha) | 15 |
| `github-dark` | 15 |
| `gruvbox` (dark) | 15 |
| `kanagawa` (Wave) | 15 |
| `tokyo-night` | 15 |
| `dracula` | 14 |
| `nord` | 9 |
| `one-dark` | 8 |
| `solarized` | 8 |

## When it runs

| Hook | Why |
| --- | --- |
| startup | Herdr does not keep plugin tokens across a server restart |
| `workspace.created`, `workspace.renamed` | a new or renamed space gets its colour |
| `workspace.updated` | a space joins or leaves a worktree group |
| `pane.focused` | a space nobody named shows its folder, and a `cd` changes it with no event a plugin can hook; the name catches up at the next focus change |

Every run compares the wanted tokens with the current ones and writes only the difference, so the
frequent focus hook costs one `workspace.list` call when nothing changed. Hooks are silent when
they work. When one fails, a toast says why; the same failure toasts again only after 10 minutes,
and every run's error is in `herdr plugin log list --plugin mrbogomips.space-colors`.

## Limits

- **No background colour.** Herdr styles a token's foreground, bold and dim only: "token styles
  never change separators or row backgrounds". The marker before the name stands in for a swatch.
- At most 15 colours, the tokens one sidebar row can hold next to the agent-state dot.
- The colours show in the expanded sidebar. The collapsed rail and the mobile layout keep
  Herdr's own rendering.
- The plugin now shows the space names. If it is disabled while its rows are in `config.toml`,
  the first row loses its name; restore the default rows (see [Uninstall](#uninstall)).
- `ACME-api` does not split on `" -"`; keep the space before the dash, or change `separator`.
- `▌` is drawn one column wide by most terminals; if yours shows a gap or overlap, pick another
  `marker`.
- The dialogs replace Herdr's prompts only on the keys you bind; other ways to create or rename a
  space keep Herdr's own behaviour.
- The dialog's preview copies the sort-spaces order; it shows where sort-spaces will put the space,
  not where Herdr puts it before sorting.

## Uninstall

1. Set `rows` of `[ui.sidebar.spaces]` back to the default,
   `[["state_icon", "workspace"], ["branch", "git_status"]]` (or remove the key), then run
   `herdr config check && herdr server reload-config`.
2. `herdr plugin uninstall mrbogomips.space-colors`. Its tokens are gone after the next server
   restart; the default rows do not show them meanwhile.

## Command line

From a terminal inside Herdr, in the plugin folder:

```bash
python3 space_colors.py preview         # each space: key, slot, colour, and why; writes nothing
python3 space_colors.py                 # colour every space now (same as "reconcile")
python3 space_colors.py snippet         # print the sidebar rows
python3 space_colors.py snippet --write # write them to sidebar-rows.toml next to config.json
python3 space_colors.py clear           # remove the plugin's tokens (hooks add them back)
python3 space_colors.py palettes        # list the presets
python3 space_dialog.py run new         # the new-space dialog in this terminal
python3 space_dialog.py run rename      # rename the space in $SPACE_COLORS_WORKSPACE_ID
```

`--config PATH` reads another config file.

## Tests

```bash
cd space-colors && python3 -m unittest -v
```
