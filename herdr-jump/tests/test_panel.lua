local h = ...

-- A stand-in for the parts of Hammerspoon panel.lua uses: the webview records what it is asked to
-- load and evaluate, and post() plays a message from the page.
local function fakeHs()
  local view = { loaded = {}, evaluated = {}, shown = false }
  local chain = { "windowStyle", "allowTextEntry", "transparent", "shadow", "level", "behaviorAsLabels",
    "windowCallback", "frame", "bringToFront" }
  for _, name in ipairs(chain) do
    view[name] = function(self) return self end
  end
  function view:html(text) self.loaded[#self.loaded + 1] = text end
  function view:show() self.shown = true end
  function view:hide() self.shown = false end
  function view:isVisible() return self.shown end
  function view:hswindow() return nil end
  function view:evaluateJavaScript(script) self.evaluated[#self.evaluated + 1] = script end
  local port = {}
  function port:setCallback(fn)
    self.callback = fn
    return self
  end
  local hotkey = { enable = function() end, disable = function() end, delete = function() end }
  local hs = {
    webview = { new = function() return view end, usercontent = { new = function() return port end } },
    hotkey = { new = function() return hotkey end },
    drawing = { windowLevels = { modalPanel = 8 } },
  }
  return hs, view, function(body) port.callback({ body = body }) end
end

-- A panel over the fake, the fake's webview, post() and the messages the panel passed on.
local function newPanel()
  local hs, view, post = fakeHs()
  _G.hs = hs
  local messages = {}
  local panel = h.load("panel").new("<page>", function(_, json) return "page:" .. json end,
    function(message) messages[#messages + 1] = message end)
  return panel, view, post, messages
end

local FRAME = { x = 0, y = 0, w = 10, h = 10 }

return {
  show_loads_the_page_with_the_model = function()
    local panel, view = newPanel()
    panel:show(FRAME, "1")
    h.eq(view.loaded, { "page:1" })
    h.eq(panel:visible(), true)
  end,

  an_update_before_the_page_is_ready_waits_for_it = function()
    local panel, view, post = newPanel()
    panel:show(FRAME, "1")
    panel:update(FRAME, "2")
    h.eq(view.evaluated, {}, "the page that is loading would lose it")
    post({ action = "ready" })
    h.eq(view.evaluated, { "render(2)" })
  end,

  only_the_last_update_before_ready_is_rendered = function()
    local panel, view, post = newPanel()
    panel:show(FRAME, "1")
    panel:update(FRAME, "2")
    panel:update(FRAME, "3")
    post({ action = "ready" })
    h.eq(view.evaluated, { "render(3)" })
  end,

  ready_without_an_update_renders_nothing = function()
    local panel, view, post = newPanel()
    panel:show(FRAME, "1")
    post({ action = "ready" })
    h.eq(view.evaluated, {})
  end,

  an_update_after_ready_is_rendered_at_once = function()
    local panel, view, post = newPanel()
    panel:show(FRAME, "1")
    post({ action = "ready" })
    panel:update(FRAME, "2")
    h.eq(view.evaluated, { "render(2)" })
  end,

  showing_again_waits_for_the_new_page = function()
    local panel, view, post = newPanel()
    panel:show(FRAME, "1")
    post({ action = "ready" })
    panel:hide()
    panel:show(FRAME, "2")
    panel:update(FRAME, "3")
    h.eq(view.evaluated, {}, "the old page is still the current one")
    post({ action = "ready" })
    h.eq(view.evaluated, { "render(3)" })
  end,

  ready_is_not_passed_on_and_other_messages_are = function()
    local panel, _, post, messages = newPanel()
    panel:show(FRAME, "1")
    post({ action = "ready" })
    post({ action = "close" })
    h.eq(messages, { { action = "close" } })
  end,

  an_update_while_hidden_is_dropped = function()
    local panel, view = newPanel()
    panel:update(FRAME, "2")
    h.eq(view.evaluated, {})
  end,
}
