--- === HerdrJump ===
---
--- One key back to your terminal, one key to the Herdr agent that needs you, and a menu bar counter
--- of the agents waiting for you (blocked on a question, or done and not yet seen), oldest wait first.
---
--- Download: https://github.com/MrBogomips/herdr-tools/tree/main/herdr-jump

local obj = {}
obj.__index = obj

obj.name = "HerdrJump"
obj.version = "0.10.0"
obj.author = "Giovanni Costagliola"
obj.homepage = "https://github.com/MrBogomips/herdr-tools/tree/main/herdr-jump"
obj.license = "MIT - https://opensource.org/licenses/MIT"
-- The oldest Herdr this Spoon is verified with.
obj.minHerdrVersion = "0.9.5"

local function load(name)
  return dofile(hs.spoons.resourcePath(name .. ".lua"))
end

local attention = load("attention")
local diagnostics = load("diagnostics")
local family = load("family")
local herdr = load("herdr")
local icon = load("icon")
local locate = load("locate")
local menubar = load("menubar")
local panel = load("panel")
local picker = load("picker")
local procs = load("procs")
local review = load("review")
local since = load("since")
local terminal = load("terminal")

local bar = menubar.new(attention)

local SEEN_KEY = "HerdrJump.seen"
local SINCE_KEY = "HerdrJump.since"
local ORDER_KEY = "HerdrJump.order"
local REVIEW_KEY = "HerdrJump.review"
local HAMMERSPOON = "org.hammerspoon.Hammerspoon"
local PS = "/bin/ps -axo pid=,ppid=,tty=,command="
local AUTOMATION_SETTINGS = "x-apple.systempreferences:com.apple.preference.security?Privacy_Automation"
local HERDR_NOT_FOUND = "herdr not found: set spoon.HerdrJump.herdrBin (see Diagnostics in the menu)"
-- How old the terminal found last may get before a poll or the toggle looks again: Herdr can start,
-- move to another terminal or quit after start(). Looking costs one ps run, about 0.1 s.
local TERMINAL_RECHECK_SECONDS = 30

-- The size of the menu's status icons, in points.
local MENU_BADGE_SIZE = 18
-- Where the picker's window goes when no screen is reported.
local FALLBACK_SCREEN = { x = 0, y = 0, w = 1440, h = 900 }

--- HerdrJump.herdrBin
--- Variable
--- The herdr binary, an absolute path. When it is nil or missing, HerdrJump looks in the usual
--- install folders (Homebrew, Herdr's installer, cargo, Nix, MacPorts, mise): Hammerspoon's PATH
--- has none of them.
obj.herdrBin = nil

--- HerdrJump.socketPath
--- Variable
--- The Herdr server socket, passed to herdr as HERDR_SOCKET_PATH.
obj.socketPath = (os.getenv("HOME") or "") .. "/.config/herdr/herdr.sock"

--- HerdrJump.terminalBundleID
--- Variable
--- The terminal to bring forward when no Herdr client shows which one runs it (Herdr inside tmux, or
--- not running). The terminal of a running client is found by itself. By default iTerm2 when it is
--- installed, else Terminal.
obj.terminalBundleID = nil

--- HerdrJump.pollSeconds
--- Variable
--- How often the menu bar asks Herdr for the agent list (one short `herdr agent list` run).
obj.pollSeconds = 5

--- HerdrJump.showMenubar
--- Variable
--- Whether to show the menu bar icon and counter.
obj.showMenubar = true

--- HerdrJump.defaultOrder
--- Variable
--- How the agents are sorted until another sort is chosen (Tab in the picker, or the menu): "fifo"
--- (oldest wait first), "lifo" (newest first) or "name". The last choice is remembered.
obj.defaultOrder = "fifo"

--- HerdrJump.groupChildren
--- Variable
--- Whether sub-sessions (agents started with a Herdr name by the unnamed agent of their tab) are
--- listed under their master, indented. false keeps one flat list; a done sub-session still does
--- not count either way.
obj.groupChildren = true

--- HerdrJump.defaultHotkeys
--- Variable
--- ⌃⌥⌘I back to the terminal (again: back to the previous app), ⌃⌥⌘A the agents picker.
obj.defaultHotkeys = {
  terminal = { { "ctrl", "alt", "cmd" }, "i" },
  agents = { { "ctrl", "alt", "cmd" }, "a" },
}

obj.logger = hs.logger.new("HerdrJump")

function obj:init()
  self.agents = {}
  self.err = nil
  self.seen = {}
  self.since = {}
  -- The agents marked to review (review.lua).
  self.marks = {}
  -- Whether the last agent list read worked: a change seen after a gap only has an approximate time.
  self.lastPollOk = false
  self.order = attention.order(nil)
  self.previousApp = nil
  -- Every agent list read is numbered; a reply older than one already applied is dropped.
  self.requested = 0
  self.applied = 0
  -- Agent statuses this Spoon does not know, already logged once.
  self.reportedStatuses = {}
  -- The herdr found at start, the terminal found last, the Herdr clients seen then, the last
  -- jump's outcome, and the terminal Hammerspoon may not control: for the jumps and Diagnostics.
  self.herdrInfo = { missing = {} }
  self.terminal = nil
  self.terminalCheckedAt = 0
  self.clientCount = 0
  self.lastRaise = nil
  self.automation = nil
  -- Masters and sub-sessions of the last read.
  self.family = family.none()
end

--- HerdrJump:bindHotkeys(mapping)
--- Method
--- Binds `terminal` and `agents`, e.g. `spoon.HerdrJump:bindHotkeys(spoon.HerdrJump.defaultHotkeys)`.
function obj:bindHotkeys(mapping)
  hs.spoons.bindHotkeysToSpec({
    terminal = function() self:toggleTerminal() end,
    agents = function() self:showAgents() end,
  }, mapping)
  return self
end

--- HerdrJump:start()
--- Method
--- Starts tracking the previous app, the menu bar counter and the agent list polling.
function obj:start()
  local stored = hs.settings.get(SEEN_KEY)
  if stored ~= nil and type(stored) ~= "table" then
    self.logger.w("ignoring a malformed " .. SEEN_KEY .. " setting: " .. hs.inspect(stored))
  end
  self.seen = type(stored) == "table" and stored or {}
  self.since = since.valid(hs.settings.get(SINCE_KEY))
  local storedMarks = hs.settings.get(REVIEW_KEY)
  local marks, malformed = review.valid(storedMarks)
  if malformed then
    self.logger.w("ignoring malformed entries of the " .. REVIEW_KEY .. " setting: " .. hs.inspect(storedMarks))
  end
  self.marks = marks
  self.lastPollOk = false
  self.order = self:_initialOrder()
  self.watcher = hs.application.watcher.new(function(_, event, app)
    if app == nil then
      return
    end
    local id = app:bundleID()
    if event == hs.application.watcher.terminated and id == self:_terminalID() then
      -- Found again at the next jump or toggle.
      self.terminal = nil
    end
    -- The picker activates Hammerspoon: going "back" there would be useless.
    if event == hs.application.watcher.activated and id ~= self:_terminalID() and id ~= HAMMERSPOON then
      self.previousApp = app
    end
  end):start()
  self.badges = icon.badges(attention.COLOR, MENU_BADGE_SIZE)
  self:_newPanel()
  if self.showMenubar then
    self.menubar = hs.menubar.new()
    if self.menubar then
      self.menubar:setMenu(function() return self:_menu() end)
      self.icons = { idle = icon.image("idle"), waiting = icon.image("waiting"), down = icon.image("down") }
      self.iconState = nil
      self:_updateMenubar(0, nil)
    else
      self.logger.e("could not create the menu bar item")
      hs.alert.show("HerdrJump: no menu bar counter (see the Hammerspoon console)")
    end
  end
  self:_detectTerminal()
  self:_connect(false)
  return self
end

-- Finds herdr and polls it. Without herdr it does not poll (each poll would fail to launch it) and
-- says so, unless quiet; the picker key calls it again, so a herdr installed later needs no reload.
function obj:_connect(quiet)
  self.herdrInfo = self:_findHerdr()
  if self.herdrInfo.path == nil then
    self.err = "herdr not found"
    if not quiet then
      self.logger.e(diagnostics.herdrLine(self.herdrInfo, obj.minHerdrVersion) .. " (the output of `command -v herdr`)")
      hs.alert.show("HerdrJump: " .. HERDR_NOT_FOUND)
    end
    self:_updateMenubar(0, self.err)
    return false
  end
  local missing = diagnostics.missingLine(self.herdrInfo)
  if missing then
    self.logger.w(missing)
  end
  self.err = nil
  if self.timer == nil then
    self.timer = hs.timer.doEvery(self.pollSeconds, function() self:refresh() end)
  end
  self:refresh()
  return true
end

--- HerdrJump:stop()
--- Method
--- Stops polling and removes the menu bar item and the picker.
function obj:stop()
  for _, name in ipairs({ "timer", "watcher" }) do
    if self[name] then
      self[name]:stop()
      self[name] = nil
    end
  end
  for _, name in ipairs({ "menubar", "panel" }) do
    if self[name] then
      self[name]:delete()
      self[name] = nil
    end
  end
  self.icons, self.iconState, self.badges = nil, nil, nil
  return self
end

-- The agents picker: picker.html in a window of its own (panel.lua); the page filters, selects and
-- sends jump, close and order back.
function obj:_newPanel()
  local file = assert(io.open(hs.spoons.resourcePath("picker.html"), "r"))
  local template = file:read("a")
  file:close()
  self.panel = panel.new(template, picker.inline, function(message) self:_onPicker(message) end)
end

function obj:_onPicker(message)
  if message.action == "jump" and type(message.pane) == "string" then
    self.panel:hide()
    self:jump(message.pane)
  elseif message.action == "close" then
    self.panel:hide()
  elseif message.action == "order" then
    self:_cycleOrder()
  elseif message.action == "review" and type(message.pane) == "string" then
    self:toggleReview(message.pane)
  end
end

-- The picker's model as JSON and its window, for the rows in the order in use.
function obj:_pickerView()
  local rows = self:_rows()
  local model = picker.model(rows, bar.legend(self.order), bar.placeholder(self.order),
    attention.COLOR, attention.MARK_COLORS)
  local screen = hs.screen.mainScreen()
  return picker.frame(screen and screen:frame() or FALLBACK_SCREEN, rows), hs.json.encode(model)
end

-- The sort chosen last, or defaultOrder; an unknown value is logged and ignored.
function obj:_initialOrder()
  local stored = hs.settings.get(ORDER_KEY)
  if stored ~= nil then
    if attention.order(stored) == stored then
      return stored
    end
    self.logger.w("ignoring an unknown " .. ORDER_KEY .. " setting: " .. hs.inspect(stored))
  end
  if attention.order(self.defaultOrder) ~= self.defaultOrder then
    self.logger.w("unknown defaultOrder " .. hs.inspect(self.defaultOrder) .. ": sorting FIFO")
  end
  return attention.order(self.defaultOrder)
end

function obj:_conn()
  return { bin = self.herdrInfo.path, socket = self.socketPath }
end

local function isFile(path)
  return hs.fs.attributes(path, "mode") == "file"
end

local function shellQuoted(text)
  return "'" .. text:gsub("'", "'\\''") .. "'"
end

-- The herdr to run (herdrBin, else the usual install folders) and its version, as Diagnostics
-- shows them: { path, source, missing, version, older }.
function obj:_findHerdr()
  local home, user = os.getenv("HOME"), os.getenv("USER")
  local path, source, missing = locate.herdr(self.herdrBin, locate.herdrCandidates(home, user), isFile)
  local info = { path = path, source = source, missing = missing }
  if path then
    info.version = locate.version(hs.execute(shellQuoted(path) .. " --version"))
    info.older = info.version and locate.older(info.version, obj.minHerdrVersion) or nil
  end
  return info
end

-- Finds the terminal that runs the Herdr client, from the client's parent processes, and caches
-- it; without a client, the terminalBundleID fallback with the reason.
function obj:_detectTerminal()
  local ps, listed = hs.execute(PS)
  local targets, notes, clients = {}, { "cannot list processes with ps" }, {}
  if listed then
    local parsed = procs.parse(ps)
    clients = procs.clients(parsed, locate.sessionOf(self.socketPath))
    local chains = {}
    for i, client in ipairs(clients) do
      chains[i] = { tty = client.tty, ancestors = procs.ancestry(parsed, client.pid) }
    end
    targets, notes = terminal.resolve(chains, terminal.regularApps())
  end
  local fallback = terminal.fallback({ terminalBundleID = self.terminalBundleID }, terminal.installed)
  fallback.name = terminal.nameOf(fallback.bundleID)
  self.terminal = terminal.choose(targets, fallback, notes)
  self.terminalCheckedAt = os.time()
  self.clientCount = #clients
  return self.terminal
end

-- The terminal found last, when it is recent enough; nil otherwise.
function obj:_freshTerminal()
  if self.terminal and os.time() - (self.terminalCheckedAt or 0) < TERMINAL_RECHECK_SECONDS then
    return self.terminal
  end
  return nil
end

-- The cached terminal's bundle id, without looking again (the app watcher calls it often).
function obj:_terminalID()
  return self.terminal and self.terminal.bundleID
end

-- The terminal for the "back to the terminal" key: the recent one when a client showed it and it
-- still runs; otherwise look again, as a client may have started or moved since.
function obj:_terminalForToggle()
  local cached = self:_freshTerminal()
  if cached and #cached.ttys > 0 and hs.application.get(cached.bundleID) then
    return cached
  end
  return self:_detectTerminal()
end

function obj:_terminalInFront()
  local front = hs.application.frontmostApplication()
  return front ~= nil and self.terminal ~= nil and front:bundleID() == self.terminal.bundleID
end

-- The menu bar item for a count of waiting agents, or for an error: the icon follows the state,
-- the title carries the count.
function obj:_updateMenubar(count, err)
  if not self.menubar then
    return
  end
  local state = menubar.state(count, err)
  if state ~= self.iconState then
    self.iconState = state
    self.menubar:setIcon(self.icons[state], true)
  end
  self.menubar:setTitle(menubar.title(count, err))
  self.menubar:setTooltip(err or "Herdr agents")
end

--- HerdrJump:refresh([onDone])
--- Method
--- Asks Herdr for the agents, updates the seen record and the menu bar.
function obj:refresh(onDone)
  self.requested = self.requested + 1
  local generation = self.requested
  herdr.listAgents(self:_conn(), function(agents, err, detail)
    -- A slow reply sent before a jump would mark the wrong agent as seen.
    if generation < self.applied then
      if onDone then
        onDone()
      end
      return
    end
    self.applied = generation
    if err then
      -- Logged when it starts, not on every poll while Herdr stays down.
      if err ~= self.err then
        self.logger.w("agent list: " .. err .. (detail and (" (" .. detail .. ")") or ""))
      end
      self.agents, self.err = {}, err
      self.family = family.none()
      self.lastPollOk = false
    else
      -- Like an error, a detail (dropped agents, no pane labels) is logged when it starts or changes.
      if detail and detail ~= self.lastDetail then
        self.logger.w("agent list: " .. detail)
      end
      self.lastDetail = detail
      self:_reportUnknownStatuses(agents)
      self.agents, self.err = agents, nil
      if self:_freshTerminal() == nil then
        self:_detectTerminal()
      end
      self:_setSeen(attention.updateSeen(self.seen, agents, self:_terminalInFront()))
      self:_setMarks(review.prune(self.marks, agents))
      local started = since.update(self.since, agents, os.time(), self.lastPollOk)
      if not since.same(started, self.since) then
        self.since = started
        hs.settings.set(SINCE_KEY, started)
      end
      self.family = family.of(agents)
      self.lastPollOk = true
    end
    self:_render()
    if onDone then
      onDone()
    end
  end)
end

-- Shows the current state: the menu bar item and, when open, the picker.
function obj:_render()
  self:_updateMenubar(attention.count(self.agents, self.seen, self.family), self.err)
  self:_updatePicker()
end

-- The open picker follows each read; an error closes it, as an empty list would read "no agents".
function obj:_updatePicker()
  if not (self.panel and self.panel:visible()) then
    return
  end
  if self.err then
    self.panel:hide()
    hs.alert.show("HerdrJump: " .. self.err)
    return
  end
  self.panel:update(self:_pickerView())
end

-- Agents with such a status are never counted, so say it once in the log.
function obj:_reportUnknownStatuses(agents)
  for _, status in ipairs(attention.unknownStatuses(agents)) do
    if not self.reportedStatuses[status] then
      self.reportedStatuses[status] = true
      self.logger.w("unknown agent status '" .. status .. "': listed, never counted")
    end
  end
end

function obj:_rows()
  local now = os.time()
  return attention.rows(self.agents, self.seen, self.order, since.describe(self.since, now), self.family,
    not self.groupChildren, review.describe(self.marks, now, since.clock))
end

-- Keeps and stores a new seen record when it differs.
function obj:_setSeen(seen)
  if not attention.sameSeen(seen, self.seen) then
    self.seen = seen
    hs.settings.set(SEEN_KEY, seen)
  end
end

-- Keeps and stores new marks when they differ.
function obj:_setMarks(marks)
  if not review.same(marks, self.marks) then
    self.marks = marks
    hs.settings.set(REVIEW_KEY, marks)
  end
end

-- The hs.menubar entry of a menubar menu item: its status icon, a jump or a sort when clicked.
function obj:_menuEntry(item)
  local pane, order = item.paneId, item.order
  local entry = {
    title = item.title,
    tooltip = item.tooltip,
    disabled = item.disabled,
    checked = item.checked,
    image = item.status and self.badges[item.status] or nil,
    indent = item.indent,
  }
  if pane then
    entry.fn = function() self:jump(pane) end
  elseif order then
    entry.fn = function() self:setOrder(order) end
  end
  if item.menu then
    entry.menu = {}
    for i, sub in ipairs(item.menu) do
      entry.menu[i] = self:_menuEntry(sub)
    end
  end
  return entry
end

function obj:_menu()
  local menu = {}
  for i, item in ipairs(bar.menu(self:_rows(), self.err, self.order)) do
    menu[i] = self:_menuEntry(item)
  end
  menu[#menu + 1] = { title = "-" }
  menu[#menu + 1] = { title = "Diagnostics", menu = self:_diagnosticsEntries() }
  return menu
end

-- What Diagnostics shows, from what start, the last jump and the last poll found: opening the menu
-- runs nothing.
function obj:_diagnosticsState()
  local target = self.terminal or { name = "none", ttys = {}, source = "default" }
  return {
    version = obj.version,
    minHerdr = obj.minHerdrVersion,
    hammerspoon = hs.processInfo.version,
    herdr = self.herdrInfo,
    socket = { path = self.socketPath, exists = hs.fs.attributes(self.socketPath, "mode") == "socket" },
    terminal = {
      name = target.name, source = target.source, note = target.note,
      selects = terminal.selectsTab(target.bundleID) and #target.ttys > 0,
    },
    clients = self.clientCount,
    agentsError = self.herdrInfo.path and self.err or nil,
    lastRaise = self.lastRaise,
    automation = self.automation,
    subsessions = family.counts(self.family),
  }
end

function obj:_diagnosticsEntries()
  local actions = {
    copy = function()
      hs.pasteboard.setContents(self:diagnostics())
      hs.alert.show("HerdrJump: diagnostics copied")
    end,
    console = function() hs.openConsole() end,
    automation = function() hs.urlevent.openURL(AUTOMATION_SETTINGS) end,
  }
  local entries = {}
  for i, item in ipairs(diagnostics.menu(self:_diagnosticsState())) do
    entries[i] = { title = item.title, disabled = item.disabled, fn = item.action and actions[item.action] }
  end
  return entries
end

--- HerdrJump:diagnostics()
--- Method
--- What HerdrJump finds now: herdr, the socket, the terminal and how a jump brings it forward, as
--- text (the menu's Diagnostics, and `install.sh --check` through the hs command line).
function obj:diagnostics()
  self:_detectTerminal()
  local state = self:_diagnosticsState()
  state.herdr = self:_findHerdr()
  return diagnostics.text(state)
end

--- HerdrJump:setOrder(order)
--- Method
--- Sorts the picker and the menu by "fifo" (oldest wait first), "lifo" (newest first) or "name",
--- and remembers it.
function obj:setOrder(order)
  if attention.order(order) ~= order then
    self.logger.w("unknown order " .. hs.inspect(order) .. ": keeping " .. self.order)
    return self
  end
  self.order = order
  hs.settings.set(ORDER_KEY, order)
  if self.panel then
    self.panel:update(self:_pickerView())
  end
  return self
end

function obj:_cycleOrder()
  self:setOrder(attention.nextOrder(self.order))
end

--- HerdrJump:toggleTerminal()
--- Method
--- Brings forward the terminal that runs Herdr; from it, goes back to the app used before it.
function obj:toggleTerminal()
  local target = self:_terminalForToggle()
  local front = hs.application.frontmostApplication()
  local previous = self.previousApp
  local hasPrevious = previous ~= nil and previous:isRunning()
  local action = terminal.toggleAction(front and front:bundleID(), target.bundleID, hasPrevious)
  if action == "show" then
    if not terminal.show(target.bundleID) then
      self.logger.e("cannot activate " .. target.bundleID)
      hs.alert.show(("HerdrJump: cannot open %s (%s)"):format(target.name, target.bundleID))
    end
  elseif action == "back" and not previous:activate() then
    self.logger.w("cannot go back to " .. tostring(previous:name()))
  end
end

--- HerdrJump:showAgents()
--- Method
--- Opens the agents picker, in the chosen order (oldest wait first by default), or closes it when
--- open. It asks Herdr first, so the list is the current one; it follows every read while open.
function obj:showAgents()
  if self.panel == nil then
    hs.alert.show("HerdrJump is stopped: call spoon.HerdrJump:start()")
    return
  end
  if self.panel:visible() then
    self.panel:hide()
    return
  end
  if self.herdrInfo.path == nil and not self:_connect(true) then
    hs.alert.show("HerdrJump: " .. HERDR_NOT_FOUND)
    return
  end
  -- A second press before Herdr answers must not open the picker twice.
  if self.opening then
    return
  end
  self.opening = true
  self:refresh(function()
    self.opening = false
    if self.panel == nil then
      return
    end
    if self.err then
      hs.alert.show("HerdrJump: " .. self.err)
    elseif #self.agents == 0 then
      hs.alert.show("HerdrJump: no Herdr agents")
    else
      self.panel:show(self:_pickerView())
    end
  end)
end

--- HerdrJump:toggleReview(paneId)
--- Method
--- Marks the agent to review, moves its mark to the next color, or clears it after the last one: the
--- picker's bookmark, Space (filter empty) and ⌘R. Any agent can be marked; a done one counts as seen then. The mark stays
--- while the agent works.
function obj:toggleReview(paneId)
  local found
  for _, agent in ipairs(self.agents) do
    if agent.pane_id == paneId then
      found = agent
    end
  end
  if found == nil then
    self.logger.w("review: no agent in pane " .. tostring(paneId))
    return
  end
  local marks, seen = review.toggle(self.marks, self.seen, found, attention.status(found, self.seen), os.time())
  self:_setMarks(marks)
  self:_setSeen(seen)
  self:_render()
end

--- HerdrJump:jump(paneId)
--- Method
--- Focuses the agent in Herdr, then brings forward the terminal that runs Herdr: its exact window
--- and tab in iTerm2 and Terminal, the app in other terminals.
function obj:jump(paneId)
  herdr.focus(self:_conn(), paneId, function(err)
    if err then
      self.logger.e("focus " .. tostring(paneId) .. ": " .. err)
      hs.alert.show("HerdrJump: " .. err)
      return
    end
    local target = self:_detectTerminal()
    local outcome = terminal.raise(target)
    self.lastRaise = outcome
    if outcome.blocked then
      self.automation = target.name
    elseif outcome.level == "exact" and self.automation == target.name then
      self.automation = nil
    end
    local alert, log = terminal.report(outcome, target.name)
    if log then
      self.logger.w("raise: " .. log)
    end
    if alert then
      hs.alert.show("HerdrJump: " .. alert)
    end
    self:refresh()
  end)
end

return obj
