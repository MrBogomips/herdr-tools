--- === HerdrJump ===
---
--- One key back to your terminal, one key to the Herdr agent that needs you, and a menu bar counter
--- of the agents waiting for you (blocked on a question, or done and not yet seen), oldest wait first.
---
--- Download: https://github.com/MrBogomips/herdr-tools/tree/main/herdr-jump

local obj = {}
obj.__index = obj

obj.name = "HerdrJump"
obj.version = "0.4.0"
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
local herdr = load("herdr")
local icon = load("icon")
local locate = load("locate")
local picker = load("picker")
local procs = load("procs")
local since = load("since")
local terminal = load("terminal")

local SEEN_KEY = "HerdrJump.seen"
local SINCE_KEY = "HerdrJump.since"
local ORDER_KEY = "HerdrJump.order"
local HAMMERSPOON = "org.hammerspoon.Hammerspoon"
local PS = "/bin/ps -axo pid=,ppid=,tty=,command="
local AUTOMATION_SETTINGS = "x-apple.systempreferences:com.apple.preference.security?Privacy_Automation"

-- Styled text brings its own font and color, so the picker rows set both. Named system colors
-- follow the light or dark appearance.
local TEXT_FONT_SIZE, SUBTEXT_FONT_SIZE = 18, 12
local TEXT_COLOR = { list = "System", name = "labelColor" }
local SUBTEXT_COLOR = { list = "System", name = "secondaryLabelColor" }
local SEPARATOR_COLOR = { list = "System", name = "separatorColor" }
-- How long the legend footer follows the picker's window as it opens: reads, and seconds apart.
local FOOTER_FOLLOW = { reads = 8, seconds = 0.05 }
-- The status icons, in points: the picker fits its row images to the row, the menu shows them as is.
local BADGE_SIZE = { chooser = 32, menu = 18 }

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

--- HerdrJump.itermBundleID
--- Variable
--- Deprecated: the former name of terminalBundleID, still honoured.
obj.itermBundleID = nil

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
  self.clientCount = 0
  self.lastRaise = nil
  self.automation = nil
end

--- HerdrJump:bindHotkeys(mapping)
--- Method
--- Binds `terminal` and `agents`, e.g. `spoon.HerdrJump:bindHotkeys(spoon.HerdrJump.defaultHotkeys)`.
--- `iterm`, the former name of `terminal`, still works.
function obj:bindHotkeys(mapping)
  local toggle = function() self:toggleTerminal() end
  hs.spoons.bindHotkeysToSpec({
    terminal = toggle,
    iterm = toggle,
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
  self.lastPollOk = false
  self.order = self:_initialOrder()
  if self.itermBundleID then
    self.logger.w("itermBundleID is now terminalBundleID: the old name still works")
  end
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
  self.badges = self:_badges()
  self:_newChooser()
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
  -- A wrong path would make hs.task log a launch failure on every poll: say it once, don't poll.
  self.herdrInfo = self:_findHerdr()
  if self.herdrInfo.path == nil then
    self.err = "herdr not found"
    self.logger.e(diagnostics.lines(self:_diagnosticsState())[2] .. " (the output of `command -v herdr`)")
    hs.alert.show("HerdrJump: herdr not found: set spoon.HerdrJump.herdrBin (see Diagnostics in the menu)")
    self:_updateMenubar(0, self.err)
    return self
  end
  if #self.herdrInfo.missing > 0 then
    self.logger.w(("herdrBin %s is missing: using %s"):format(self.herdrInfo.missing[1], self.herdrInfo.path))
  end
  self.timer = hs.timer.doEvery(self.pollSeconds, function() self:refresh() end)
  self:refresh()
  return self
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
  self:_hideFooter()
  for _, name in ipairs({ "sortKey", "menubar", "chooser" }) do
    if self[name] then
      self[name]:delete()
      self[name] = nil
    end
  end
  self.icons, self.iconState, self.badges = nil, nil, nil
  return self
end

-- The agents picker; its legend is a footer drawn while it is open (see _showFooter).
function obj:_newChooser()
  self.chooser = hs.chooser.new(function(choice)
    if choice and choice.paneId then
      self:jump(choice.paneId)
    end
  end)
  self.chooser:searchSubText(true)
  self.chooser:choices(function() return self:_choices() end)
  self.chooser:placeholderText(attention.placeholder(self.order))
  -- Tab changes the sort only while the picker is open; anywhere else it stays Tab.
  self.sortKey = hs.hotkey.new({}, "tab", function() self:_cycleOrder() end)
  self.chooser:showCallback(function()
    if self.sortKey then
      self.sortKey:enable()
    end
  end)
  self.chooser:hideCallback(function()
    if self.sortKey then
      self.sortKey:disable()
    end
    self:_hideFooter()
  end)
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

-- The status icons, per status, at the picker's and the menu's size.
function obj:_badges()
  local badges = {}
  for use, size in pairs(BADGE_SIZE) do
    badges[use] = {}
    for status, color in pairs(attention.COLOR) do
      badges[use][status] = icon.status(status, color, size)
    end
  end
  return badges
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
  local fallback = terminal.fallback({ terminalBundleID = self.terminalBundleID, itermBundleID = self.itermBundleID },
    terminal.installed)
  fallback.name = terminal.nameOf(fallback.bundleID)
  self.terminal = terminal.choose(targets, fallback, notes)
  self.clientCount = #clients
  return self.terminal
end

-- The cached terminal's bundle id, without looking again (the app watcher calls it often).
function obj:_terminalID()
  return self.terminal and self.terminal.bundleID
end

-- The terminal for the "back to the terminal" key: the cached one when a client showed it and it
-- still runs; otherwise look again, as a client may have started since.
function obj:_terminalForToggle()
  local cached = self.terminal
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
  local state = attention.state(count, err)
  if state ~= self.iconState then
    self.iconState = state
    self.menubar:setIcon(self.icons[state], true)
  end
  self.menubar:setTitle(attention.title(count, err))
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
      self.lastPollOk = false
    else
      if detail then
        self.logger.w("agent list: " .. detail)
      end
      self:_reportUnknownStatuses(agents)
      self.agents, self.err = agents, nil
      local seen = attention.updateSeen(self.seen, agents, self:_terminalInFront())
      if not attention.sameSeen(seen, self.seen) then
        self.seen = seen
        hs.settings.set(SEEN_KEY, seen)
      end
      local started = since.update(self.since, agents, os.time(), self.lastPollOk)
      if not since.same(started, self.since) then
        self.since = started
        hs.settings.set(SINCE_KEY, started)
      end
      self.lastPollOk = true
    end
    self:_updateMenubar(attention.count(self.agents, self.seen), self.err)
    if onDone then
      onDone()
    end
  end)
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
  return attention.rows(self.agents, self.seen, self.order, since.describe(self.since, os.time()))
end

local function styled(text, size, color, alignment)
  return hs.styledtext.new(text, {
    font = { name = hs.styledtext.defaultFonts.system.name, size = size },
    color = color,
    paragraphStyle = alignment and { alignment = alignment } or nil,
  })
end

-- The picker entries: the status icon, the title, the status and its age in the status color.
function obj:_choices()
  local choices = {}
  for i, row in ipairs(self:_rows()) do
    choices[i] = {
      text = styled(row.text, TEXT_FONT_SIZE, TEXT_COLOR),
      subText = styled(row.when, SUBTEXT_FONT_SIZE, attention.COLOR[row.status])
        .. styled(row.subText:sub(#row.when + 1), SUBTEXT_FONT_SIZE, SUBTEXT_COLOR),
      image = self.badges.chooser[row.status],
      paneId = row.paneId,
    }
  end
  return choices
end

-- The legend as styled text: each glyph in its status color; and the hint (order, Tab), to be
-- right-aligned.
function obj:_legendTexts()
  local legend = attention.legend(self.order)
  local text = styled("", SUBTEXT_FONT_SIZE, TEXT_COLOR)
  for i, part in ipairs(legend.parts) do
    text = text .. styled((i > 1 and "    " or "") .. part.glyph, SUBTEXT_FONT_SIZE, attention.COLOR[part.status])
      .. styled(" " .. part.meaning, SUBTEXT_FONT_SIZE, TEXT_COLOR)
  end
  return text, styled(legend.hint, SUBTEXT_FONT_SIZE, SUBTEXT_COLOR, "right")
end

-- The legend, as one line over the free space at the bottom of the open picker: a choice row would
-- be selectable. The canvas lets clicks through and goes away with the picker. The picker's window
-- can reach the window list a moment after it opens, and zooms in, so the footer follows its frame
-- for a moment.
function obj:_showFooter()
  self:_hideFooter()
  self:_drawFooter()
  local reads = 0
  self.footerTimer = hs.timer.doEvery(FOOTER_FOLLOW.seconds, function()
    reads = reads + 1
    self:_drawFooter()
    if reads >= FOOTER_FOLLOW.reads then
      self.footerTimer:stop()
      self.footerTimer = nil
      if self.footer == nil then
        self.logger.w("picker window not found: no legend")
      end
    end
  end)
end

-- Draws the footer at the bottom of the picker window, unless it is there already or the window is
-- not on screen.
function obj:_drawFooter()
  local window = picker.chooserWindow(hs.window.list(true), hs.processInfo.processID)
  if window == nil or picker.sameFrame(window, self.footerWindow) then
    return
  end
  local footer = self.footer or hs.canvas.new({ x = window.x, y = window.y, w = 1, h = 1 })
  local legend, hint = self:_legendTexts()
  local layout = picker.footer(window, footer:minimumTextSize(legend), footer:minimumTextSize(hint))
  local elements = {
    {
      type = "segments", action = "stroke", strokeWidth = 1, strokeColor = SEPARATOR_COLOR,
      coordinates = { { x = 0, y = 0.5 }, { x = layout.frame.w, y = 0.5 } },
    },
    { type = "text", text = legend, frame = layout.text },
  }
  if layout.hint then
    elements[#elements + 1] = { type = "text", text = hint, frame = layout.text }
  end
  footer:frame(layout.frame)
  footer:level(window.layer + 1)
  footer:behaviorAsLabels({ "canJoinAllSpaces", "fullScreenAuxiliary" })
  footer:replaceElements(elements)
  footer:show()
  self.footer, self.footerWindow = footer, window
end

function obj:_hideFooter()
  if self.footerTimer then
    self.footerTimer:stop()
    self.footerTimer = nil
  end
  if self.footer then
    self.footer:delete()
    self.footer = nil
  end
  self.footerWindow = nil
end

-- The hs.menubar entry of an attention.menu item: its status icon, a jump or a sort when clicked.
function obj:_menuEntry(item)
  local pane, order = item.paneId, item.order
  local entry = {
    title = item.title,
    tooltip = item.tooltip,
    disabled = item.disabled,
    checked = item.checked,
    image = item.status and self.badges.menu[item.status] or nil,
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
  for i, item in ipairs(attention.menu(self:_rows(), self.err, self.order)) do
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
      name = target.name, source = target.source, legacy = target.legacy, note = target.note,
      selects = terminal.adapter(target.bundleID) ~= "generic" and #target.ttys > 0,
    },
    clients = self.clientCount,
    agentsError = self.herdrInfo.path and self.err or nil,
    lastRaise = self.lastRaise,
    automation = self.automation,
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
  if self.chooser then
    self.chooser:placeholderText(attention.placeholder(order))
    if self.chooser:isVisible() then
      self.chooser:refreshChoicesCallback(true)
      self:_showFooter()
    end
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

--- HerdrJump:toggleIterm()
--- Method
--- The former name of toggleTerminal().
function obj:toggleIterm()
  self:toggleTerminal()
end

--- HerdrJump:showAgents()
--- Method
--- Opens the agents picker, in the chosen order (oldest wait first by default); the list is
--- refreshed once while it is open.
function obj:showAgents()
  if self.chooser == nil then
    hs.alert.show("HerdrJump is stopped: call spoon.HerdrJump:start()")
    return
  end
  if self.err then
    hs.alert.show("HerdrJump: " .. self.err)
    self:refresh()
    return
  end
  if #self.agents == 0 then
    hs.alert.show("HerdrJump: no Herdr agents")
    self:refresh()
    return
  end
  local screen = hs.screen.mainScreen()
  self.chooser:rows(picker.rows(#self.agents, picker.maxRows(screen and screen:frame().h or 0)))
  self.chooser:refreshChoicesCallback()
  self.chooser:show()
  self:_showFooter()
  self:refresh(function()
    if not (self.chooser and self.chooser:isVisible()) then
      return
    end
    if self.err then
      -- An empty picker would look like "no agents": close it and say why.
      self.chooser:hide()
      hs.alert.show("HerdrJump: " .. self.err)
      return
    end
    self.chooser:refreshChoicesCallback(true)
  end)
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
