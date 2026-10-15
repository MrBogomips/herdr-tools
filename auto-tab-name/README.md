# auto-tab-name

Names each Herdr tab after the folder of its pane, and keeps the name in sync as you move around.
Tabs you name yourself are left alone.

```
~/tools/initech/sort     basename (default)     sort
                         repo                   initech/sort
                         repo_branch            initech@main
```

Herdr shows a tab nobody named as its position number: 1 for the first tab of a workspace, 2 for the
second, and so on. This plugin renames those tabs after the folder their pane is in (the folder of
the program running in the foreground, by default), and updates the name when the folder changes. A
tab you rename by hand stops following its folder until you say so. Names are written with the
socket method `tab.rename`, and only for the tabs whose name changes: a run with nothing to change
writes nothing.

## Install

```bash
herdr plugin install MrBogomips/herdr-tools/auto-tab-name
```

## Key bindings

Bind the actions you want in `~/.config/herdr/config.toml` and run `herdr server reload-config`:

```toml
[[keys.command]]
key = "prefix+alt+c"
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

The plugin has six actions. Every one of them toasts when it fails; on success `toggle`, `sync`,
`follow` and `unfollow` report their result as a Herdr toast, while `configure` just opens the popup
and `refresh` stays quiet:

| Action | What it does |
| --- | --- |
| `configure` | Opens the configuration popup |
| `toggle` | Turns `auto_sync` on or off, and syncs at once when it turns on |
| `sync` | Names every followed tab now, even with `auto_sync` off |
| `follow` | Makes the current tab follow its folder again and names it now |
| `unfollow` | Keeps the current tab's name as it is and stops renaming it |
| `refresh` | The quiet hook run, for the [shell integration](#shell-integration-optional): names the followed tabs only when `auto_sync` is on, toasts only on failure |

Without a key binding, run any of them from a terminal inside Herdr with
`herdr plugin action invoke mrbogomips.auto-tab-name.<action>` (`follow` and `unfollow` act on the
current tab).

## Configuration

Settings live in `config.json` in the plugin's config directory (`herdr plugin config-dir
mrbogomips.auto-tab-name` prints it). The file is optional and read on every run, so changes apply
at once. The `configure` action opens a popup menu that edits the same file: type an item's number
to change it, `s` saves (and syncs the names when `auto_sync` is on), `q` leaves without saving.
`toggle` and the popup both write `config.json`.

| Key | Type | Default | Meaning |
| --- | --- | --- | --- |
| `auto_sync` | boolean | `true` | Rename tabs from the hooks; with `false` only `sync` and `follow` rename |
| `format` | string | `"basename"` | What the name shows, see below |
| `depth` | integer, 1 or more | `2` | Folders shown by `last_n` |
| `max_length` | integer, 0 or more | `24` | Longest name, cut with `…`; `0` means no limit |
| `source` | string | `"foreground_cwd"` | `"foreground_cwd"`: folder of the program in the foreground (an agent's folder, say); `"cwd"`: folder of the shell. See [Which folder](#which-folder-source) |
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

When a name is longer than `max_length` (24 by default), `basename`, `repo` and `repo_branch` keep
the start and end with `…` (the folder `globex-billing-reconciliation` gives
`globex-billing-reconcil…`); `last_n` and `home_path` keep the end and start with `…`
(`~/work/acme/apps/web/frontend` gives `…/acme/apps/web/frontend`), where the folder you are in is.

### Which folder (`source`)

A pane runs a shell, and often a program inside the shell: a coding agent, an editor, a build.
Herdr reports two folders for each pane:

| `source` | Folder |
| --- | --- |
| `cwd` | The shell's folder: it changes when you `cd` |
| `foreground_cwd` | The folder of the program in the foreground, the one using the terminal now |

At the prompt the program in the foreground is the shell itself, so the two are the same, and they
stay the same for a program that runs in the folder it was started in (an editor, `htop`). They
differ when a program moves to another folder while it runs, as a coding agent does when it starts
working in a worktree. Started in `~/tools/initech` (branch `main`), an agent working in the worktree
`~/tools/initech/.worktrees/login` (branch `feature/login`) gives:

| `format` | `"cwd"` | `"foreground_cwd"` |
| --- | --- | --- |
| `basename` | `initech` | `login` |
| `repo_branch` | `initech@main` | `initech@feature/login` |

- `foreground_cwd` (the default) names the tab after the folder the work happens in: with agents in
  worktrees, each tab tells which worktree or branch its agent is on. A long command that runs in
  another folder, such as `(cd build && make)`, can name the tab `build` while it runs, if a hook
  runs meanwhile (a focus change, say).
- `cwd` follows only your `cd` in the shell: steadier, but the tab of an agent working in a
  worktree keeps the name of the folder the agent was started in.

When Herdr cannot tell one of the two folders, the plugin uses the other.

## Which tabs follow their folder

- A new tab shows its position number (the number Herdr shows for an unnamed tab), so it follows
  its folder from the start.
- Renaming a tab by hand (to anything but its position number) stops it following: your name stays.
- `follow` makes the tab follow again, and so does renaming it back to its position number.
- `unfollow` stops following and keeps the current name; on a tab that still shows its position
  number it pins that number as the name, so a new position (a tab before it closes or moves) does
  not bring it back into sync. Such a tab already shows that number, so renaming it back changes
  nothing: `follow` resumes it.
- A tab already named like its folder when the plugin starts counts as followed, so a Herdr restart
  changes nothing.

Herdr asks for a name when you create a tab (`ui.prompt_new_tab_name`, on by default). Leave the
name empty to get an automatic one; type a name to keep it.

## Shell integration (optional)

Herdr has no event for `cd`, so without more a name catches up at the next focus change, tab or
pane change. To rename the tab as soon as you change folder, have your shell call the quiet
`refresh` action: add the lines for your shell to its startup file and open a new shell.

### zsh

```zsh
# ~/.zshrc
if [[ $HERDR_ENV == 1 && -n $HERDR_BIN_PATH ]]; then
  autoload -Uz add-zsh-hook
  _auto_tab_name_chpwd() { "$HERDR_BIN_PATH" plugin action invoke mrbogomips.auto-tab-name.refresh >/dev/null 2>&1 &! }
  add-zsh-hook chpwd _auto_tab_name_chpwd
fi
```

`chpwd` runs after every change of folder.

### bash

```bash
# ~/.bashrc
if [[ ${HERDR_ENV-} == 1 && -n ${HERDR_BIN_PATH-} ]]; then
  _auto_tab_name_prompt() {
    [[ $PWD == "${_auto_tab_name_pwd-}" ]] && return
    _auto_tab_name_pwd=$PWD
    ("$HERDR_BIN_PATH" plugin action invoke mrbogomips.auto-tab-name.refresh >/dev/null 2>&1 &)
  }
  PROMPT_COMMAND="_auto_tab_name_prompt${PROMPT_COMMAND:+;$PROMPT_COMMAND}"
fi
```

bash has no hook on `cd`: this runs before each prompt and calls `refresh` only when the folder
changed. It keeps the `PROMPT_COMMAND` you already have and works with the bash 3.2 of macOS.

### fish

```fish
# ~/.config/fish/config.fish
if test "$HERDR_ENV" = 1; and set -q HERDR_BIN_PATH
    function _auto_tab_name_pwd --on-variable PWD
        "$HERDR_BIN_PATH" plugin action invoke mrbogomips.auto-tab-name.refresh >/dev/null 2>&1 &
        disown
    end
end
```

The function runs whenever `PWD` changes; `disown` keeps fish from reporting the finished job.

All three run only inside Herdr (`HERDR_ENV` is `1`) and call the Herdr binary that owns the pane
(`HERDR_BIN_PATH`, so `herdr` need not be on your `PATH`). They run it in the background and discard
its output, so the prompt never waits. `refresh` renames only when `auto_sync` is on and toasts only
on failure. The shell reports only its own `cd`: a program that changes folder while it runs (see
[Which folder](#which-folder-source)) is seen at the next focus change.

## Limits

- No Herdr event fires on `cd` (`pane.updated` cannot be hooked): without the
  [shell integration](#shell-integration-optional) a name catches up at the next focus or tab change.
- Herdr reports only the globally focused pane, so a tab with several panes uses the pane you
  focused last in it, or its first pane when none was focused yet.
- A tab renamed through the API keeps its name for good: Herdr has no way back to the automatic
  position number. That is why `unfollow` pins the number the tab shows, and why renaming a tab back
  to its position number (the number Herdr shows for an unnamed tab) by hand is what resumes
  following; for a tab `unfollow` pinned, use `follow`.
- Another plugin's pane (an overlay, a split or a tab) focused in a tab names the tab after that
  pane's folder until the focus returns to another pane of the tab.
- With `repo` or `repo_branch`, a git repository in your home folder (dotfiles, say) makes every
  folder under home that is not in another repository show as that repository.
- With `foreground_cwd` a command that runs in another folder can rename the tab while it runs, and
  a program that changes folder is seen only at the next focus change: see
  [Which folder](#which-folder-source).
- State (which tabs follow, the last pane of each) lives in the plugin's state directory, one file
  per Herdr server.

## Troubleshooting

`herdr plugin log list --plugin mrbogomips.auto-tab-name` shows every hook and action run with its
output. Hooks stay silent when they work and toast only on failure, at most once in a while.

## Tests

```bash
cd auto-tab-name && /usr/bin/python3 -m unittest -v
```
