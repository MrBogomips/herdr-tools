# auto-tab-name

Names each Herdr tab after the folder of its pane, and keeps the name in sync as you move around.
Tabs you name yourself are left alone.

```
~/tools/initech/sort     basename (default)     sort
                         repo                   initech/sort
                         repo_branch            initech@main
```

Herdr shows a tab nobody named as its number. This plugin renames those tabs after the folder their
pane is in (the folder of the program running in the foreground, by default), and updates the name
when the folder changes. A tab you rename by hand stops following its folder until you say so. Names
are written with the socket method `tab.rename`, and only for the tabs whose name changes: a run with
nothing to change writes nothing.

## Install

```bash
herdr plugin install MrBogomips/herdr-tools/auto-tab-name
```

## Key bindings

Bind the actions you want in `~/.config/herdr/config.toml` and run `herdr server reload-config`:

```toml
[[keys.command]]
key = "prefix+shift+t"
type = "plugin_action"
command = "mrbogomips.auto-tab-name.configure"
description = "configure auto tab names"

[[keys.command]]
key = "prefix+alt+t"
type = "plugin_action"
command = "mrbogomips.auto-tab-name.toggle"
description = "toggle auto tab names"

[[keys.command]]
key = "prefix+alt+f"
type = "plugin_action"
command = "mrbogomips.auto-tab-name.follow"
description = "make this tab follow its folder"
```

The plugin has six actions; each one reports its result as a Herdr toast:

| Action | What it does |
| --- | --- |
| `configure` | Opens the configuration popup |
| `toggle` | Turns `auto_sync` on or off, and syncs at once when it turns on |
| `sync` | Names every followed tab now, even with `auto_sync` off |
| `follow` | Makes the current tab follow its folder again and names it now |
| `unfollow` | Keeps the current tab's name as it is and stops renaming it |
| `refresh` | Quiet `sync` for the shell hook below: honours `auto_sync`, toasts only on failure |

Without a key binding, `herdr plugin action invoke --plugin mrbogomips.auto-tab-name <action>` runs
any of them.

## Configuration

Settings live in `config.json` in the plugin's config directory (`herdr plugin config-dir
mrbogomips.auto-tab-name` prints it). The file is optional and read on every run, so changes apply
at once. The `configure` action opens a popup menu that edits the same file: type an item's number
to change it, `s` saves and syncs the names, `q` leaves without saving. `toggle` and the popup both
write `config.json`.

| Key | Type | Default | Meaning |
| --- | --- | --- | --- |
| `auto_sync` | boolean | `true` | Rename tabs from the hooks; with `false` only `sync` and `follow` rename |
| `format` | string | `"basename"` | What the name shows, see below |
| `depth` | integer, 1 or more | `2` | Folders shown by `last_n` |
| `max_length` | integer, 0 or more | `24` | Longest name, cut with `…`; `0` means no limit |
| `source` | string | `"foreground_cwd"` | `"foreground_cwd"`: folder of the foreground program (an agent's folder, say); `"cwd"`: folder of the shell. Either one falls back to the other when it is unknown |
| `home_tilde` | boolean | `true` | Write the home folder as `~` |

`config.example.json` holds the defaults. Unknown keys and wrong values make the run fail with the
file's path in the message.

### Formats

For `~/tools/initech/sort`, inside the repository `initech` on branch `main`:

| `format` | Name | Outside a repository |
| --- | --- | --- |
| `basename` | `sort` | same |
| `repo` | `initech/sort` (just `initech` at the repository root) | like `basename` |
| `last_n` | `initech/sort` (the last `depth` folders) | same |
| `home_path` | `~/tools/initech/sort` | same |
| `repo_branch` | `initech@main`; a detached HEAD shows the short hash, `initech@1a2b3c4` | like `basename` |

A linked worktree shows the name of its main repository, a submodule the name of its own folder.
The repository is found by reading `.git` (no `git` process runs).

When a name is longer than `max_length`, `basename`, `repo` and `repo_branch` keep the start and
end with `…` (`Globex-billing-ser…`); `last_n` and `home_path` keep the end and start with `…`
(`…/acme/web/frontend`), where the folder you are in is.

## Which tabs follow their folder

- A new tab shows its number, so it follows its folder from the start.
- Renaming a tab by hand (to anything but its number) stops it following: your name stays.
- `follow` makes the tab follow again, and so does renaming it back to its number.
- `unfollow` stops following and keeps the current name; on a tab that still shows its number it
  pins that number as the name, so moving the tab does not bring it back into sync.
- A tab already named like its folder when the plugin starts counts as followed, so a Herdr restart
  changes nothing.

Herdr asks for a name when you create a tab (`ui.prompt_new_tab_name`, on by default). Leave the
name empty to get an automatic one; type a name to keep it.

## Instant updates on `cd` (optional)

Herdr has no event for `cd`, so without more a name catches up at the next focus change, tab or
pane change. To update it right away, call the `refresh` action from your shell:

```zsh
# ~/.zshrc
if [[ -n $HERDR_ENV ]]; then
  autoload -Uz add-zsh-hook
  _auto_tab_name_chpwd() { herdr plugin action invoke --plugin mrbogomips.auto-tab-name refresh >/dev/null 2>&1 &! }
  add-zsh-hook chpwd _auto_tab_name_chpwd
fi
```

```bash
# ~/.bashrc
if [[ -n $HERDR_ENV ]]; then
  _auto_tab_name_prompt() {
    [[ $PWD == "${_auto_tab_name_pwd-}" ]] && return
    _auto_tab_name_pwd=$PWD
    (herdr plugin action invoke --plugin mrbogomips.auto-tab-name refresh >/dev/null 2>&1 &)
  }
  PROMPT_COMMAND="_auto_tab_name_prompt${PROMPT_COMMAND:+;$PROMPT_COMMAND}"
fi
```

Both run only inside Herdr (`HERDR_ENV` is set) and in the background.

## Limits

- No Herdr event fires on `cd` (`pane.updated` cannot be hooked): without the shell hook a name
  catches up at the next focus or tab change.
- Herdr reports only the globally focused pane, so a tab with several panes uses the pane you
  focused last in it, or its first pane when none was focused yet.
- A tab renamed through the API keeps its name for good: Herdr has no way back to the automatic
  number. That is why `unfollow` pins the number, and why renaming a tab back to its number by hand
  is what resumes following.
- With `foreground_cwd` the name follows the program in the foreground, which is not always the
  shell's folder (an agent started in another folder, for instance). Use `"source": "cwd"` for the
  shell's folder.
- State (which tabs follow, the last pane of each) lives in the plugin's state directory, one file
  per Herdr server.

## Troubleshooting

`herdr plugin log list --plugin mrbogomips.auto-tab-name` shows every hook and action run with its
output. Hooks stay silent when they work and toast only on failure, at most once in a while.

## Tests

```bash
cd auto-tab-name && /usr/bin/python3 -m unittest -v
```
