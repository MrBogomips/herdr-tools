# herdr-jump

A [Hammerspoon](https://www.hammerspoon.org) Spoon for macOS that gets you back to your Herdr
agents from any app: one key back to iTerm, one key to the agent that needs you, and a menu bar
icon that counts the agents waiting for you.

<img src="docs/menubar.svg" alt="The menu bar item: two outlined agents while nothing waits, two solid agents with a count while some wait, outlined with a question mark when Herdr cannot be read" width="440">

It is not a Herdr plugin: it runs in Hammerspoon, outside Herdr, and talks to the Herdr server
through the `herdr` command line. It has no `herdr-plugin.toml`, so the plugin marketplace does
not list it.

## Use cases

- **An agent asks for a permission while you are in the browser.** The icon turns solid with a
  count. `⌃⌥⌘A` opens the picker with that agent on top; Enter lands you on its pane, with the
  iTerm window, tab and session running Herdr in front.
- **Several agents finish while you are in a meeting.** The count says how many. The picker lists
  them `done` first, latest first; each one leaves the count once you have looked at it.
- **Back and forth between iTerm and the app you were in.** `⌃⌥⌘I` brings iTerm forward on the
  window you used last, Space or display included; pressed again from iTerm, it goes back to the
  app you came from.
- **A glance instead of a switch.** The icon alone says whether anything waits. Click it for the
  same list as the picker, as a menu.

## Keys

| Key | What happens |
| --- | --- |
| `⌃⌥⌘I` | Activates iTerm2. Herdr keeps its focused pane, so you land where you left. From iTerm, goes back to the previous app. |
| `⌃⌥⌘A` | The agents picker, most urgent first: `blocked` (waiting on a permission or a question), `done` (finished, not seen yet), `unknown`, `idle`, `working`; within a status the latest change first. Type to filter by title or folder, Enter to jump: Herdr focuses the agent's pane and the iTerm window, tab and session running the Herdr client come forward. |

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
```

Both keys can be changed, see [Configure](#configure).

## Menu bar

| Icon | Meaning |
| --- | --- |
| Two outlined agents | Nothing waits for you |
| Two solid agents and a number | That many agents are `blocked`, or `done` and not seen yet |
| Two outlined agents and `?` | Herdr cannot be read; the menu says why |

macOS adds the item left of the other menu bar icons, on the main display. The count can lag by
up to `pollSeconds`.

### Seen agents

Herdr's server marks a `done` agent as seen when something focuses it through the API, as the
picker does. Looking at it inside the Herdr TUI may not, and the count would stay high. So
HerdrJump keeps its own record: a `done` agent counts as seen once it was the focused pane while
iTerm was in front. A later completion of the same agent makes it `done` again. The record lives
in Hammerspoon's settings (`HerdrJump.seen`) and survives a reload; an entry whose completion
counter goes backwards (Herdr restarted and reused the pane id) is forgotten.

## Install

Requirements: macOS, Herdr 0.9.3 or newer running in iTerm2, and Homebrew if
[Hammerspoon](https://github.com/Hammerspoon/hammerspoon) (MIT) is not installed yet.

Paste into a terminal:

```bash
curl -fsSL https://raw.githubusercontent.com/MrBogomips/herdr-tools/main/herdr-jump/install.sh | sh
```

The script asks nothing and prints what it does:

- installs Hammerspoon with Homebrew when it is missing;
- downloads `HerdrJump.spoon` from this repository into `~/.hammerspoon/Spoons`, replacing the
  previous copy: the same line updates it;
- creates `~/.hammerspoon/init.lua` from [`init.example.lua`](init.example.lua) when you have
  none (it also turns off Hammerspoon's crash reporting, starts it at login and hides its Dock
  icon), or appends the three HerdrJump lines to yours;
- reloads Hammerspoon, or starts it.

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
- **Automation: Hammerspoon → iTerm2**, on the first jump: selecting the Herdr session uses
  iTerm's AppleScript. Without it, a jump still focuses the agent and activates iTerm, but cannot
  pick the window when you have several; an alert points to System Settings › Privacy &
  Security › Automation.

To remove HerdrJump, delete `~/.hammerspoon/Spoons/HerdrJump.spoon` and its lines in
`~/.hammerspoon/init.lua`, then reload Hammerspoon.

## Configure

Set these before `start()`:

| Setting | Default | Meaning |
| --- | --- | --- |
| `herdrBin` | `/opt/homebrew/bin/herdr` | The `herdr` binary (Hammerspoon's PATH has no Homebrew) |
| `socketPath` | `~/.config/herdr/herdr.sock` | The Herdr server socket, passed as `HERDR_SOCKET_PATH` |
| `itermBundleID` | `com.googlecode.iterm2` | The app to bring forward |
| `pollSeconds` | `5` | How often the agent list is read |
| `showMenubar` | `true` | Show the menu bar icon and count |

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
- The icon is drawn with `hs.canvas` as a template image, so macOS tints it for light and dark
  menu bars; the count is the item's title.
- It does not use `hs.socket` on Herdr's socket: in Hammerspoon 1.1.1, connecting `hs.socket` to
  a Unix socket aborts Hammerspoon (GCDAsyncSocket throws while building the peer's URL).

## Limits

- Only agents in Herdr: agents running in plain iTerm tabs or in tmux are not listed.
- With several Herdr clients, a jump brings forward the frontmost iTerm window running one.
- iTerm documents its AppleScript support as deprecated; if a future iTerm drops it, a jump falls
  back to activating iTerm.

## Troubleshooting

- The Hammerspoon console (menu bar icon → Console) shows the `HerdrJump` log lines: failed
  agent list reads with the raw reply, dropped malformed agents, agent statuses it does not know,
  focus errors and why the iTerm session could not be selected.
- `?` next to the icon and "Herdr is not running" in the menu: no Herdr server answers on
  `socketPath`; start Herdr. "cannot run /opt/homebrew/bin/herdr": set `herdrBin` to the output
  of `which herdr`. The count recovers on the next poll.
- No icon in sight: look left of the other icons on the main display; a crowded menu bar can push
  it out, as for any app.
- An alert after a jump says why the Herdr tab could not be selected; iTerm still comes forward.

## Tests

```bash
lua herdr-jump/tests/run.lua           # the pure modules (ranking, seen record, icon geometry, herdr replies, iTerm), Lua 5.4 or newer
sh herdr-jump/tests/test_install.sh    # install.sh, with the system commands stubbed
```

Neither needs Hammerspoon.
