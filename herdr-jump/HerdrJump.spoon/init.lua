--- === HerdrJump ===
---
--- One key back to iTerm, one key to the Herdr agent that needs you, and a menu bar counter of
--- the agents waiting for you (blocked on a question, or done and not yet seen), oldest wait first.
---
--- Download: https://github.com/MrBogomips/herdr-tools/tree/main/herdr-jump

local obj = {}
obj.__index = obj

obj.name = "HerdrJump"
obj.version = "0.3.0"
obj.author = "Giovanni Costagliola"
obj.homepage = "https://github.com/MrBogomips/herdr-tools/tree/main/herdr-jump"
obj.license = "MIT - https://opensource.org/licenses/MIT"

local function load(name)
  return dofile(hs.spoons.resourcePath(name .. ".lua"))
end

local attention = load("attention")
local herdr = load("herdr")
local icon = load("icon")
local iterm = load("iterm")
local since = load("since")

local SEEN_KEY = "HerdrJump.seen"
local SINCE_KEY = "HerdrJump.since"
local ORDER_KEY = "HerdrJump.order"
local HAMMERSPOON = "org.hammerspoon.Hammerspoon"

-- Styled text brings its own font and color, so the picker rows set both. Named system colors
-- follow the light or dark appearance.
local TEXT_FONT_SIZE, SUBTEXT_FONT_SIZE = 18, 12
local TEXT_COLOR = { list = "System", name = "labelColor" }
local SUBTEXT_COLOR = { list = "System", name = "secondaryLabelColor" }
-- The status icons, in points: the picker fits its row images to the row, the menu shows them as is.
local BADGE_SIZE = { chooser = 32, menu = 18 }

--- HerdrJump.herdrBin
--- Variable
--- The herdr binary (absolute: Hammerspoon's PATH does not include Homebrew).
obj.herdrBin = "/opt/homebrew/bin/herdr"

--- HerdrJump.socketPath
--- Variable
--- The Herdr server socket, passed to herdr as HERDR_SOCKET_PATH.
obj.socketPath = os.getenv("HOME") .. "/.config/herdr/herdr.sock"

--- HerdrJump.itermBundleID
--- Variable
--- The bundle id of iTerm2.
obj.itermBundleID = "com.googlecode.iterm2"

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
--- ⌃⌥⌘I back to iTerm (again: back to the previous app), ⌃⌥⌘A the agents picker.
obj.defaultHotkeys = {
  iterm = { { "ctrl", "alt", "cmd" }, "i" },
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
end

--- HerdrJump:bindHotkeys(mapping)
--- Method
--- Binds `iterm` and `agents`, e.g. `spoon.HerdrJump:bindHotkeys(spoon.HerdrJump.defaultHotkeys)`.
function obj:bindHotkeys(mapping)
  hs.spoons.bindHotkeysToSpec({
    iterm = function() self:toggleIterm() end,
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
  self.watcher = hs.application.watcher.new(function(_, event, app)
    if event ~= hs.application.watcher.activated or app == nil then
      return
    end
    local id = app:bundleID()
    -- The picker activates Hammerspoon: going "back" there would be useless.
    if id ~= self.itermBundleID and id ~= HAMMERSPOON then
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
  -- A wrong path would make hs.task log a launch failure on every poll: say it once, don't poll.
  local binary = hs.fs.attributes(self.herdrBin)
  if binary == nil or binary.mode ~= "file" then
    self.err = "herdr not found at " .. self.herdrBin
    self.logger.e(self.err .. ": set spoon.HerdrJump.herdrBin to the output of `which herdr`")
    hs.alert.show("HerdrJump: " .. self.err)
    self:_updateMenubar(0, self.err)
    return self
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
  for _, name in ipairs({ "sortKey", "menubar", "chooser" }) do
    if self[name] then
      self[name]:delete()
      self[name] = nil
    end
  end
  self.icons, self.iconState, self.badges = nil, nil, nil
  return self
end

-- The agents picker; the legend row is not valid, so choosing it leaves the picker open.
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

-- The status icons, per status, at the picker's and the menu's size; blank for the legend row.
function obj:_badges()
  local badges = { blank = icon.blank(BADGE_SIZE.chooser) }
  for use, size in pairs(BADGE_SIZE) do
    badges[use] = {}
    for status, color in pairs(attention.COLOR) do
      badges[use][status] = icon.status(status, color, size)
    end
  end
  return badges
end

function obj:_conn()
  return { bin = self.herdrBin, socket = self.socketPath }
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

local function itermInFront(bundleID)
  local front = hs.application.frontmostApplication()
  return front ~= nil and front:bundleID() == bundleID
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
      local seen = attention.updateSeen(self.seen, agents, itermInFront(self.itermBundleID))
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

local function styled(text, size, color)
  return hs.styledtext.new(text, { font = { name = hs.styledtext.defaultFonts.system.name, size = size }, color = color })
end

-- The picker entries: the status icon, the title, the status and its age in the status color, then
-- the legend.
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
  if #choices > 0 then
    choices[#choices + 1] = self:_legendChoice()
  end
  return choices
end

-- The legend row: each glyph in its status color, the order and the keys below.
function obj:_legendChoice()
  local legend = attention.legend(self.order)
  local text = styled("", SUBTEXT_FONT_SIZE, TEXT_COLOR)
  for i, part in ipairs(legend.parts) do
    text = text .. styled((i > 1 and "    " or "") .. part.glyph, SUBTEXT_FONT_SIZE, attention.COLOR[part.status])
      .. styled(" " .. part.meaning, SUBTEXT_FONT_SIZE, TEXT_COLOR)
  end
  return {
    text = text,
    subText = styled(legend.subText, SUBTEXT_FONT_SIZE, SUBTEXT_COLOR),
    image = self.badges.blank,
    valid = false,
  }
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
  return menu
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
    end
  end
  return self
end

function obj:_cycleOrder()
  self:setOrder(attention.nextOrder(self.order))
end

--- HerdrJump:toggleIterm()
--- Method
--- Brings iTerm forward; from iTerm, goes back to the app used before it.
function obj:toggleIterm()
  local front = hs.application.frontmostApplication()
  local previous = self.previousApp
  local hasPrevious = previous ~= nil and previous:isRunning()
  local action = iterm.toggleAction(front and front:bundleID(), self.itermBundleID, hasPrevious)
  if action == "show-iterm" then
    if not iterm.show(self.itermBundleID) then
      self.logger.e("cannot activate " .. self.itermBundleID)
      hs.alert.show("HerdrJump: cannot open iTerm (" .. self.itermBundleID .. ")")
    end
  elseif action == "back" and not previous:activate() then
    self.logger.w("cannot go back to " .. tostring(previous:name()))
  end
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
  self.chooser:refreshChoicesCallback()
  self.chooser:show()
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
--- Focuses the agent in Herdr, then brings forward the iTerm session that runs Herdr.
function obj:jump(paneId)
  herdr.focus(self:_conn(), paneId, function(err)
    if err then
      self.logger.e("focus " .. tostring(paneId) .. ": " .. err)
      hs.alert.show("HerdrJump: " .. err)
      return
    end
    local problem, blocked = iterm.raiseHerdr(self.itermBundleID)
    if problem then
      self.logger.w("raise: " .. problem)
      if blocked then
        hs.alert.show("HerdrJump: allow Hammerspoon to control iTerm2 in System Settings › Privacy & Security › Automation")
      else
        hs.alert.show("HerdrJump: " .. problem)
      end
    end
    self:refresh()
  end)
end

return obj
