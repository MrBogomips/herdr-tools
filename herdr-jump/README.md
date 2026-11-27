# herdr-jump

A [Hammerspoon](https://www.hammerspoon.org) Spoon for macOS that gets you back to your Herdr
agents from any app: one key back to your terminal, one key to the agent that needs you, and a menu
bar icon that counts the agents waiting for you.

**Website: [herdr-jump at a glance](https://mrbogomips.github.io/herdr-tools/herdr-jump.html)**;
this README is the full reference.

Run five agents at once and they queue up for you: a permission here, a finished review there.
HerdrJump lines them up first come, first served, tells you how long each one has waited, and
takes you to its pane with Enter, whatever app you are in.

<img src="docs/picker.png" alt="The agents picker: two blocked agents with orange pause icons on top, each with the shortcut ⌘1 or ⌘2, then two finished agents with green check marks, ⌘3 and ⌘4, each with an outlined bookmark after its title; then an idle agent with a pink bookmark, to review since 12:37; then a working agent coordinating a release, with an outlined bookmark and its three sub-sessions on compact indented lines under it: the finished one with ⌘5, an idle one with a yellow bookmark, a working one; then a working agent marked with a teal bookmark; a line at the bottom explains the icons, the three bookmark colors, the sort in use and the arrow keys" width="800">

The picker (`⌃⌥⌘A`, from any app), with fictional agents: blocked first, then done, each oldest
first, each with its ⌘ shortcut; then the agents marked to review (a bookmark in one of three
colors), then the others, sub-sessions under their master. The outlined bookmark marks an agent;
Tab sorts newest first or by name.

## Standalone

HerdrJump needs only a running Herdr server. No Herdr plugin, from this repository or anywhere
else, and nothing to set up inside Herdr: your config, spaces and tabs stay as they are. It reads
the server with three commands of the `herdr` binary that ships with Herdr, `herdr agent list` and
`herdr pane list` every `pollSeconds`, and `herdr agent focus` on a jump (see [How it works](#how-it-works)), so it works
with any Herdr setup, plugins or none. One line installs it, and the next key press switches agents.

It is not a Herdr plugin itself: it runs in Hammerspoon, outside Herdr. It has no
`herdr-plugin.toml`, so the plugin marketplace does not list it.

## Use cases

- **An agent asks for a permission while you are in the browser.** The icon turns solid with a
  count. `⌃⌥⌘A` opens the picker with that agent on top and how long it has waited; Enter lands
  you on its pane, with the terminal window and tab running Herdr in front.
- **Several agents finish while you are in a meeting.** The count says how many. The picker queues
  them oldest first, each with its wait ("done 25m · since 10:40"), so you serve them in turn;
  each one leaves the count once you have looked at it.
- **Following the latest answers instead of the queue.** Tab in the picker sorts newest first
  (LIFO): among the `done` agents, the one that just finished is on top (`blocked` ones still come
  first). Tab again sorts every agent by name. The choice is remembered.
- **Back and forth between your terminal and the app you were in.** `⌃⌥⌘I` brings the terminal
  running Herdr forward on the window you used last, Space or display included; pressed again from
  the terminal, it goes back to the app you came from.
- **A glance instead of a switch.** The icon alone says whether anything waits. Click it for the
  same list as the picker, as a menu.
- **An agent runs sub-sessions next to it.** The helpers it started in its tab are listed under it,
  indented, and its row sums them up (`+4 sub · 1 done`). A helper that is done stays out of the
  count: its master hears about it. One that waits on a permission counts like any agent, since
  only you can answer it.
- **You looked at the result but have not reviewed it yet.** Once seen, a `done` agent turns
  `idle` and looks finished. Click the bookmark after its title in the picker (or press Space) to
  keep it "to review": a pink bookmark and "to review since 10:02", above the idle agents while it
  is idle. Click again for yellow, then teal, to tell your marks apart; once more clears it. Any
  agent can be marked, a working one too, and the bookmark stays while it works.

## Keys

| Key | What happens |
| --- | --- |
| `⌃⌥⌘I` | Activates the terminal running Herdr (see [Terminals](#terminals)). Herdr keeps its focused pane, so you land where you left. From the terminal, goes back to the previous app. |
| `⌃⌥⌘A` | The agents picker, most urgent first: `blocked` (waiting on a permission or a question), `done` (finished, not seen yet), `unknown`, `idle`, `working`; within a status the oldest change first (FIFO). Type to filter by title or folder, arrows to move (every arrow mode works on the rows the filter leaves; at the top or bottom the selection stays), Enter or a click to jump: Herdr focuses the agent's pane and the terminal window and tab running the Herdr client come forward. Esc, a click elsewhere or `⌃⌥⌘A` again closes it. |
| `⌘1`…`⌘9` (in the picker) | Jump to an agent that waits for you, `blocked` or `done` and not seen, sub-sessions included, numbered in list order. The others have no shortcut: pick them with the arrows, the filter or the mouse. A shortcut stays on its agent while you filter. |
| `⌥↑` `⌥↓` (in the picker) | Move over the top-level rows only: masters and agents without sub-sessions. The sub-sessions stay on screen and are skipped; from one, `⌥↑` goes back to its master. With `groupChildren = false` every row is top-level, so they move like the plain arrows. |
| `⇧↑` `⇧↓` (in the picker) | Move over the agents that wait for you only, `blocked` or `done` and not seen, sub-sessions included, past the ninth too (the rows with no `⌘` key left). |
| `Space`, `⌘R` or a click on the bookmark (in the picker) | Mark the selected agent to review in pink, then move the mark to yellow, then teal, then clear it (see [To review](#to-review)). Any agent can be marked, whatever its status; marking a `done` one also counts as seeing it. Space marks only while the filter is empty; with text in it, Space types a space (a filter can hold several words) and `⌘R` marks. The chip on the selected row names the key that marks it now (`␣` or `⌘R`). A click on the bookmark does not jump. |
| `Tab` (in the picker) | Next sort: FIFO (oldest change first, the default), LIFO (newest first, still by status), name (every agent by title). The filter you typed stays; the choice is remembered. |

Both keys can be changed, see [Configure](#configure).

## Symbols

Each row starts with a colored icon; the status and its time under the title take the same color.
A filled icon waits for you, an outlined one does not. The line at the bottom of the picker is the
legend, with the sort in use, the ones Tab moves to and the arrows' modifiers (`⌥↑↓ masters · ⇧↑↓
waiting`); it is not a row, so it cannot be selected.
The menu bar drop-down has a Legend submenu with the icons.

| Icon | Color | Status |
| --- | --- | --- |
| Disc with pause bars | orange | `blocked`: waiting on a permission or a question |
| Disc with a check mark | green | `done`: finished, not seen yet |
| Ring with `?` | purple | `unknown`: a status HerdrJump does not know (listed, never counted) |
| Empty ring | grey | `idle`, or `done` and already seen |
| Half-filled ring | blue | `working` |

After the title, a filled bookmark (pink, yellow or teal) marks an agent [to review](#to-review);
an outlined grey one, on every other agent, is the button that marks it.

## Waiting times

Herdr reports no times, only counters, so HerdrJump notes when it sees each agent change state and
shows how long ago that was: `12m`, `1h 5m`, `2d 3h`, with the start time for agents that wait for
you (`since 09:41`, `Tue 23:05` within the week). The time is the poll that saw the change, so it
can be up to `pollSeconds` late. `≥12m · since ≤09:41` means the change happened while HerdrJump
could not see it (Hammerspoon was not running, or Herdr did not answer): the agent has waited at
least that long, since that time or earlier.
The times live in Hammerspoon's settings (`HerdrJump.since`) and survive a reload; the queue order
comes from Herdr's own change counter, so it is exact either way.

## Menu bar

<img src="docs/menubar.svg" alt="The menu bar item: two outlined agents while nothing waits, two solid agents with a count while some wait, outlined with a question mark when Herdr cannot be read" width="440">

| Icon | Meaning |
| --- | --- |
| Two outlined agents | Nothing waits for you |
| Two solid agents and a number | That many agents are `blocked`, or `done` and not seen yet (a `done` [sub-session](#sub-sessions) aside) |
| Two outlined agents and `?` | Herdr cannot be read; the menu says why |

Click it for the drop-down: the agents in the picker's order, each with its icon and wait, then
**Sort by** (FIFO, LIFO, by name; the checked one is in use), **Legend** and **Diagnostics** (see
[Troubleshooting](#troubleshooting)).

<img src="docs/menu.png" alt="The menu bar drop-down with fictional agents: two blocked, two done, an idle one marked to review, then a working agent coordinating a release with its three sub-sessions indented under it, the idle one marked to review, then a working agent still marked to review; each with its status icon and wait, a marked one ending with to review and its bookmark color; then the Sort by, Legend and Diagnostics submenus" width="479">

macOS adds the item left of the other menu bar icons, on the main display. The count can lag by
up to `pollSeconds`; the picker asks Herdr again when it opens, so its list is the current one.

### Seen agents

Herdr's server marks a `done` agent as seen when something focuses it through the API, as the
picker does. Looking at it inside the Herdr TUI may not, and the count would stay high. So
HerdrJump keeps its own record: a `done` agent counts as seen once it was the focused pane while
the terminal running Herdr was in front. A later completion of the same agent makes it `done` again. The record lives
in Hammerspoon's settings (`HerdrJump.seen`) and survives a reload; an entry whose completion
counter goes backwards (Herdr restarted and reused the pane id) is forgotten.

### To review

A `done` agent you have looked at turns `idle`, which reads as "can be closed" even when you have
not reviewed its work yet. Mark it to review: the bookmark after its title, or Space (filter empty) or `⌘R` on the
selected row. Each further click moves the mark to the next color, pink, yellow, teal, and the
one after teal clears it: three colors to sort your marks by whatever you like (urgent, waiting
for someone, to discuss). Any agent can be marked, a working or blocked one too. A marked agent
keeps the icon of its real status, with the bookmark in its color after the title and "to review
since 10:02" under it; changing the color keeps that time. While it reads `idle` it ranks after the `done` ones
and before `unknown`, oldest mark first (newest first in LIFO); while it works again, is blocked
or done, it ranks with that status and keeps the bookmark. Masters add "N to review" for their
sub-sessions, and the menu bar drop-down ends a marked row with "· to review (yellow)". A mark
never counts or gets a `⌘` key.

The mark goes when you click the bookmark (or press Space or `⌘R`) past teal, when the pane closes, or when Herdr
restarts (its pane ids are reused; a restart goes unnoticed on an agent that never finished since it was marked). The marks live in Hammerspoon's settings
(`HerdrJump.review`) and survive a reload; a mark stored by an older version reads as pink.
`spoon.HerdrJump:toggleReview(paneId)` does the same as a click from a script.

## Sub-sessions

An agent that starts helpers with `herdr agent start <name>` (as session-hub does, or a script
of yours) gives each one a Herdr name; the agent itself has none. HerdrJump reads that from
`herdr agent list`:

- in a tab, the named agents are sub-sessions of the only unnamed agent there (helpers split into
  panes next to their master);
- a named agent in a tab with no unnamed agent (helpers in tabs of their own) is a sub-session of
  the only unnamed agent of its workspace whose folder holds the helper's folder.

When `herdr agent start` times out, the helper often comes up anyway and Herdr detects it, but
without a name. Two fallbacks cover it:

- in a tab where only one unnamed agent has a pane without a label (`herdr pane list`), that one
  is the master and the others are its sub-sessions, as session-hub labels a helper's pane before
  the start. A label alone never makes an agent a sub-session, since you may label panes of your
  own: a labelled master keeps its helpers;
- in a tab with several unnamed agents, the oldest one is the master when its folder holds the
  folder of every other agent of the tab, and is not the same folder. Herdr numbers panes in order
  within a workspace (`w12:p2K` before `w12:p3H`), which tells the oldest. The numbering is not a
  documented contract, so the folder check has to agree.

Anything else ambiguous, such as two unnamed agents in one folder or two masters on the same
folder, stays a top-level agent.

| What | A sub-session |
| --- | --- |
| Picker and menu | right under its master, indented; in the picker on one compact line. The group ranks as its most urgent member, quiet ones aside, and keeps the sort in use inside |
| Master's row | `+4 sub`, then how many sub-sessions are `blocked` and `done` |
| `done` | quiet: listed with its icon, not counted |
| `blocked` | counted, like any agent |

`groupChildren = false` keeps one flat list, each sub-session naming its master (`sub of <master>`);
a `done` sub-session stays quiet either way.

## Terminals

HerdrJump finds the terminal that runs the Herdr client by itself: it climbs from the client's
process (`ps`) to the app that started it. Nothing to configure for the usual cases.

| Terminal | A jump brings forward |
| --- | --- |
| iTerm2 | the window, tab and session running Herdr (AppleScript, by tty) |
| Terminal | the window and tab running Herdr (AppleScript, by tty) |
| Any other app: Ghostty, WezTerm, kitty, Alacritty, Warp, VS Code… | the app, on its last used window |

- A client inside tmux, screen or zellij, or reached over ssh, hides its terminal: the keys bring
  forward `terminalBundleID` (by default iTerm2 when installed, else Terminal), and Diagnostics
  says why.
- An iTerm2 restart can leave its shells under an `iTermServer` process that no longer belongs to
  iTerm2: HerdrJump still takes it for iTerm2.
- A client of a named session (`herdr --session <name>`) counts when `socketPath` is that session's
  socket; with no client of it in sight, every client counts.

## Install

Requirements: macOS, Herdr 0.9.5 or newer in a terminal (see [Terminals](#terminals)), and
Homebrew if [Hammerspoon](https://github.com/Hammerspoon/hammerspoon) (MIT) is not installed yet.

Paste into a terminal:

```bash
curl -fsSL https://raw.githubusercontent.com/MrBogomips/herdr-tools/main/herdr-jump/install.sh | sh
```

The script asks nothing and prints what it does:

- installs Hammerspoon with Homebrew when it is missing;
- downloads `HerdrJump.spoon` from this repository into the `Spoons` folder of Hammerspoon's
  config (`~/.hammerspoon/Spoons`, or beside the `init.lua` that Hammerspoon's `MJConfigFile`
  setting names), replacing the previous copy: the same line updates it;
- creates `init.lua` from [`init.example.lua`](init.example.lua) when you have none (it also turns
  off Hammerspoon's crash reporting, starts it at login and hides its Dock icon), or appends the
  HerdrJump lines to yours. Either way it adds `herdrBin`, the `herdr` your shell runs, and
  `socketPath` when `herdr status server` names another socket than the default: Hammerspoon sees
  neither your `PATH` nor `XDG_CONFIG_HOME` or `HERDR_SESSION`. An `init.lua` that loads HerdrJump
  already is left as it is;
- reloads Hammerspoon, or starts it.

To see what HerdrJump needs and what it finds, on a Mac with or without it, changing nothing:

```bash
curl -fsSL https://raw.githubusercontent.com/MrBogomips/herdr-tools/main/herdr-jump/install.sh | sh -s -- --check
```

It checks Hammerspoon, `init.lua` and the Spoon, `herdr` and its version, the server socket and
the installed terminals, then prints the running HerdrJump's own Diagnostics through the `hs`
command line. It exits 1 when Hammerspoon or `herdr` is missing.

To read the script first, or to install a branch or a release tag (`herdr-jump-vX.Y.Z`, when one
has been cut) instead of `main`:

```bash
curl -fsSL https://raw.githubusercontent.com/MrBogomips/herdr-tools/main/herdr-jump/install.sh -o install.sh
less install.sh
sh install.sh --ref <branch-or-tag>
```

From a clone, `ln -s "$PWD/herdr-jump/HerdrJump.spoon" ~/.hammerspoon/Spoons/HerdrJump.spoon`
follows your checkout instead; the script leaves such a link alone unless you pass `--force`.

macOS asks for two permissions:

- **Accessibility** for Hammerspoon, on first launch: global hotkeys need it.
- **Automation: Hammerspoon → iTerm2, or → Terminal**, on the first jump: selecting the Herdr tab
  uses the terminal's AppleScript. Without it, a jump still focuses the agent and activates the
  terminal, but cannot pick the window when you have several; an alert points to System Settings ›
  Privacy & Security › Automation, and so does Diagnostics.

To remove HerdrJump, delete `HerdrJump.spoon` from Hammerspoon's `Spoons` folder and its lines in
`init.lua`, then reload Hammerspoon.

## Configure

Set these before `start()`:

| Setting | Default | Meaning |
| --- | --- | --- |
| `herdrBin` | found | The `herdr` binary. Unset or missing, it is looked for in `/opt/homebrew/bin`, `/usr/local/bin`, `~/.local/bin` (Herdr's installer), `~/.cargo/bin`, the Nix profiles, `/opt/local/bin` and mise's shims: Hammerspoon's PATH has none of them |
| `socketPath` | `~/.config/herdr/herdr.sock` | The Herdr server socket, passed as `HERDR_SOCKET_PATH`: set it when your Herdr uses another one (`herdr status server` prints it), such as a named session's `~/.config/herdr/sessions/<name>/herdr.sock` |
| `terminalBundleID` | iTerm2 when installed, else Terminal | The terminal to bring forward when no Herdr client shows its own (Herdr in tmux, or not running); `itermBundleID`, its former name, still works |
| `pollSeconds` | `5` | How often the agent list is read |
| `showMenubar` | `true` | Show the menu bar icon and count |
| `defaultOrder` | `"fifo"` | The sort until you choose one: `"fifo"`, `"lifo"` or `"name"`; your last choice (Tab, menu) wins |
| `groupChildren` | `true` | List sub-sessions under their master (see [Sub-sessions](#sub-sessions)); `false` keeps one flat list |

`spoon.HerdrJump:setOrder("lifo")` sorts from a script, like Tab, and is remembered too.

Other keys: pass your own mapping instead of `defaultHotkeys`.

```lua
hs.loadSpoon("HerdrJump")
spoon.HerdrJump.pollSeconds = 10
spoon.HerdrJump:bindHotkeys({
  terminal = { { "ctrl", "alt", "cmd" }, "t" },
  agents = { { "ctrl", "alt", "cmd" }, "space" },
})
spoon.HerdrJump:start()
```

`iterm`, the former name of `terminal`, still works in the mapping.

## How it works

- Every `pollSeconds` it runs `herdr agent list` (about 0.1 s), which prints the agents as JSON on
  stdout; errors come as a JSON envelope on stderr. Then `herdr pane list` for the pane labels that
  name helpers (see [Sub-sessions](#sub-sessions)); if it fails, the agents are used without them. Herdr can push status events, but only one
  pane per subscription, so polling is simpler. The picker key runs the same read before the
  picker opens.
- A jump runs `herdr agent focus <pane id>`, then finds the Herdr client with `ps`, climbs its
  parent processes to the app that runs it (apps come from `hs.application.runningApplications()`),
  and has iTerm2 or Terminal select the tab on the client's tty over AppleScript; any other app is
  activated.
- The icon is drawn with `hs.canvas` as a template image, so macOS tints it for light and dark
  menu bars; the count is the item's title. The status icons are drawn the same way, in color.
- The picker is a page of its own, `picker.html`, in an `hs.webview` that takes the keyboard and
  closes when it loses focus; the page filters, moves the selection and handles the keys, and
  posts jump, close and sort back to Lua. `picker.lua` builds what it shows. `hs.chooser` could not
  do it: its rows all have one height, and it numbers the first nine rows whatever they are.
- It does not use `hs.socket` on Herdr's socket: in Hammerspoon 1.1.1, connecting `hs.socket` to
  a Unix socket aborts Hammerspoon (GCDAsyncSocket throws while building the peer's URL).

## Limits

- Only agents in Herdr: agents running in plain terminal tabs or in tmux are not listed.
- With Herdr clients in several terminals, a jump brings forward the one `ps` lists first; in it,
  the frontmost window running a client.
- Terminals other than iTerm2 and Terminal come forward as an app, on their last used window: their
  tab is not selected.
- iTerm documents its AppleScript support as deprecated; if a future iTerm drops it, a jump falls
  back to activating iTerm.
- A sub-session is any named agent next to an unnamed one: an agent you named by hand
  (`herdr agent rename`) in a tab with another, unnamed agent is listed as its sub-session.
- The picker grows with the list up to the screen's height, then the list scrolls. It opens on
  the main screen (the one with the focused window).

## Troubleshooting

- **Diagnostics**, at the bottom of the menu bar drop-down, lists what HerdrJump found: `herdr` and
  where, the socket, the terminal and how a jump brings it forward, the last jump's problem. **Copy
  diagnostics** puts it on the clipboard; `hs -c 'return spoon.HerdrJump:diagnostics()'` prints it,
  and `install.sh --check` adds Hammerspoon, `init.lua` and the installed terminals.
- The Hammerspoon console (Diagnostics › Open the Hammerspoon console) shows the `HerdrJump` log
  lines: failed agent list reads with the raw reply, dropped malformed agents, agent statuses it
  does not know, focus errors and why the terminal's tab could not be selected.
- `?` next to the icon and "Herdr is not running" in the menu: no Herdr server answers on
  `socketPath`; start Herdr, or set `socketPath` to the socket `herdr status server` prints. "herdr
  not found": set `herdrBin` to the output of `command -v herdr`. The count recovers on the next
  poll.
- No icon in sight: look left of the other icons on the main display; a crowded menu bar can push
  it out, as for any app.
- An alert after a jump means macOS refused the Automation permission, or the terminal could not
  be activated at all; other reasons go to the console and to Diagnostics.

## Tests

```bash
lua herdr-jump/tests/run.lua           # the pure modules (sorting, sub-sessions, seen record, wait times, icons, herdr replies, processes, terminals, herdr lookup, diagnostics, picker model and size), Lua 5.4
sh herdr-jump/tests/test_install.sh    # install.sh, with the system commands stubbed
```

Neither needs Hammerspoon.
