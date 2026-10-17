# herdr-jump

A [Hammerspoon](https://www.hammerspoon.org) Spoon for macOS that gets you back to your Herdr
agents from any app: one key back to iTerm, one key to the agent that needs you, and a menu bar
counter of the agents waiting for you.

```
⌃⌥⌘A  (from any app)
┌──────────────────────────────────┐
│ ⏸ ACME-API-Fixing-Auth           │
│   blocked · acme-api             │
│ ✓ GLOBEX-ETL-Reviewing-Loader    │
│   done · globex-etl              │
│ · LUMON-Planning-Offsite         │
│   idle · lumon                   │
│ ◐ INITECH-CRM-Implementing-UI    │
│   working · initech-crm          │
└──────────────────────────────────┘
menu bar:  ⧗ 2   (click: the same list as a menu)
```

This is not a Herdr plugin: it runs in Hammerspoon, outside Herdr, and talks to the Herdr server
through the `herdr` command line. It has no `herdr-plugin.toml`, so the plugin marketplace does
not list it.

## What it does

- **`⌃⌥⌘I` back to iTerm.** From any app, activates iTerm2: macOS brings forward the window you
  used last and switches Space or display if needed. Herdr keeps its focused pane, so you land
  where you left. Pressed again while iTerm is in front, it goes back to the app you came from.
- **`⌃⌥⌘A` agents picker.** A Spotlight-style list of the Herdr agents, most urgent first:
  `blocked` (waiting on a permission or a question), `done` (finished, not seen yet), `unknown`,
  `idle`, `working`; within a status the latest change comes first. Type to filter (title or
  folder), Enter to jump: Herdr focuses the agent's pane and the iTerm window, tab and session
  running the Herdr client come forward.
- **Menu bar `⧗ N`.** N counts the `blocked` and unseen `done` agents; with nothing waiting it
  shows `⧗` alone, and `⧗ ?` when Herdr cannot be read (the menu says why). Click it for the same
  list as a menu. macOS adds it left of the other menu bar icons, on the main display.

### Seen agents

Herdr's server marks a `done` agent as seen when something focuses it through the API, as the
picker does. Looking at it inside the Herdr TUI may not, and the counter would stay high. So
HerdrJump keeps its own record: a `done` agent counts as seen once it was the focused pane while
iTerm was in front. A later completion of the same agent makes it `done` again. The record lives
in Hammerspoon's settings (`HerdrJump.seen`) and survives a reload; an entry whose completion
counter goes backwards (Herdr restarted and reused the pane id) is forgotten.

## Install

Requirements: macOS, [Hammerspoon](https://github.com/Hammerspoon/hammerspoon) (MIT), Herdr 0.9.3
or newer running in iTerm2.

```bash
brew install --cask hammerspoon
mkdir -p ~/.hammerspoon/Spoons
ln -s "$PWD/herdr-jump/HerdrJump.spoon" ~/.hammerspoon/Spoons/HerdrJump.spoon   # from a clone
```

Copy [`init.example.lua`](init.example.lua) into `~/.hammerspoon/init.lua` (or add its lines),
then reload Hammerspoon. It turns off Hammerspoon's crash reporting, starts it at login, hides
its Dock icon and loads the Spoon.

macOS asks for two permissions:

- **Accessibility** for Hammerspoon, on first launch: global hotkeys need it.
- **Automation: Hammerspoon → iTerm2**, on the first jump: selecting the Herdr session uses
  iTerm's AppleScript. Without it, a jump still focuses the agent and activates iTerm, but cannot
  pick the window when you have several; an alert points to System Settings › Privacy &
  Security › Automation.

## Configure

Set these before `start()`:

| Setting | Default | Meaning |
| --- | --- | --- |
| `herdrBin` | `/opt/homebrew/bin/herdr` | The `herdr` binary (Hammerspoon's PATH has no Homebrew) |
| `socketPath` | `~/.config/herdr/herdr.sock` | The Herdr server socket, passed as `HERDR_SOCKET_PATH` |
| `itermBundleID` | `com.googlecode.iterm2` | The app to bring forward |
| `pollSeconds` | `5` | How often the agent list is read |
| `showMenubar` | `true` | Show the `⧗` counter |

Other keys: pass your own mapping instead of `defaultHotkeys`.

```lua
hs.loadSpoon("HerdrJump")
spoon.HerdrJump.pollSeconds = 10
spoon.HerdrJump:bindHotkeys({
  iterm = { { "ctrl", "alt", "cmd" }, "t" },
  agents = { { "ctrl", "alt", "cmd" }, "space" },
})
spoon.HerdrJump:start()
```

## How it works

- Every `pollSeconds` it runs `herdr agent list` (about 0.1 s), which prints the agents as JSON on
  stdout; errors come as a JSON envelope on stderr. Herdr can push status events, but only one
  pane per subscription, so polling is simpler.
- A jump runs `herdr agent focus <pane id>`, then finds the Herdr client's terminal with `ps` and
  selects the iTerm session on that tty, with its tab and window.
- It does not use `hs.socket` on Herdr's socket: in Hammerspoon 1.1.1, connecting `hs.socket` to
  a Unix socket aborts Hammerspoon (GCDAsyncSocket throws while building the peer's URL).

## Limits

- Only agents in Herdr: agents running in plain iTerm tabs or in tmux are not listed.
- With several Herdr clients, a jump brings forward the frontmost iTerm window running one.
- The counter can lag by up to `pollSeconds`.
- iTerm documents its AppleScript support as deprecated; if a future iTerm drops it, a jump falls
  back to activating iTerm.

## Troubleshooting

- The Hammerspoon console (menu bar icon → Console) shows the `HerdrJump` log lines: failed
  agent list reads with the raw reply, dropped malformed agents, agent statuses it does not know,
  focus errors and why the iTerm session could not be selected.
- `⧗ ?` and "Herdr is not running" in the menu: no Herdr server answers on `socketPath`; start
  Herdr. "cannot run /opt/homebrew/bin/herdr": set `herdrBin` to the output of `which herdr`.
  The counter recovers on the next poll.
- No `⧗` in sight: look left of the other icons on the main display; a crowded menu bar can push
  it out, as for any app.
- An alert after a jump says why the Herdr tab could not be selected; iTerm still comes forward.

## Tests

The pure modules (ranking, seen record, herdr replies, client detection, AppleScript) run under
plain Lua 5.4 or newer, without Hammerspoon:

```bash
lua herdr-jump/tests/run.lua
```
