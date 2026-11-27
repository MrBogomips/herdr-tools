-- The agents picker's window: picker.html in an hs.webview that takes the keyboard, floats over
-- every app and Space, and closes when it loses focus. Needs Hammerspoon when used (not at load).
--
-- Not hs.chooser: its rows all have one height, and it puts ⌘1…⌘9 on the first nine rows
-- whatever they are; the picker lists sub-sessions on compact rows and keeps ⌘N for the agents
-- that wait.

local M = {}

local Panel = {}
Panel.__index = Panel

local PORT = "herdrJump"

-- template: picker.html's text; onMessage(message): a table posted by the page ({ action, pane }).
function M.new(template, inline, onMessage)
  local self = setmetatable({ template = template, inline = inline, ready = false }, Panel)
  self.port = hs.webview.usercontent.new(PORT):setCallback(function(message)
    if type(message) ~= "table" or type(message.body) ~= "table" then
      return
    end
    if message.body.action == "ready" then
      self:_ready()
    else
      onMessage(message.body)
    end
  end)
  self.view = hs.webview.new({ x = 0, y = 0, w = 10, h = 10 }, { developerExtrasEnabled = false }, self.port)
  self.view:windowStyle({ "borderless", "nonactivating" })
  self.view:allowTextEntry(true)
  self.view:transparent(true)
  self.view:shadow(true)
  self.view:level(hs.drawing.windowLevels.modalPanel)
  self.view:behaviorAsLabels({ "canJoinAllSpaces", "fullScreenAuxiliary" })
  -- Escape never reaches the page (hs.webview takes it before WebKit), so a hotkey bound only
  -- while the picker is shown closes it.
  self.escape = hs.hotkey.new({}, "escape", function() self:hide() end)
  self.view:windowCallback(function(action, _, focused)
    if action == "focusChange" and focused == false then
      self:hide()
    end
  end)
  return self
end

-- Loads the page with the model (JSON) at frame, shows it and gives it the keyboard.
-- The load takes some 80 ms, during which the view still runs the page it had: the new page says
-- "ready" when its script has run, and an update meant for it waits until then.
function Panel:show(frame, json)
  self.ready, self.pending = false, nil
  self.view:frame(frame)
  self.view:html(self.inline(self.template, json))
  self.view:show()
  self.view:bringToFront(true)
  self.escape:enable()
  local window = self.view:hswindow()
  if window then
    window:focus()
  end
end

-- New rows while open: the filter and the selection stay.
function Panel:update(frame, json)
  if not self:visible() then
    return
  end
  self.view:frame(frame)
  if self.ready then
    self.view:evaluateJavaScript("render(" .. json .. ")")
  else
    self.pending = json
  end
end

-- The page loaded by show() runs: it gets the update that arrived meanwhile, if any.
function Panel:_ready()
  self.ready = true
  local json = self.pending
  self.pending = nil
  if json and self:visible() then
    self.view:evaluateJavaScript("render(" .. json .. ")")
  end
end

function Panel:hide()
  self.escape:disable()
  if self:visible() then
    self.view:hide()
  end
end

function Panel:visible()
  return self.view ~= nil and self.view:isVisible()
end

function Panel:delete()
  self.escape:delete()
  if self.view then
    self.view:delete()
    self.view = nil
  end
end

return M
