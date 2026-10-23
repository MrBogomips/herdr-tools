local h = ...
local picker = h.load("picker")

local HAMMERSPOON = 42

-- An entry of hs.window.list(true), as CGWindowListCopyWindowInfo describes a window.
local function window(pid, name, onscreen, bounds)
  return {
    kCGWindowOwnerPID = pid,
    kCGWindowName = name,
    kCGWindowIsOnscreen = onscreen or nil,
    kCGWindowLayer = 27,
    kCGWindowBounds = bounds,
  }
end

local BOUNDS = { X = -1344, Y = 207, Width = 768, Height = 346 }

return {
  rows_leave_room_under_the_agents_for_the_legend = function()
    -- The window grows 42 points per row, the list draws one every 44 from 99 points down; the
    -- legend needs 28 points and 6 more above it: 5 agents end at 319, 6 rows give 346, 7 give 388.
    h.eq(picker.rows(1, 22), 2)
    h.eq(picker.rows(5, 22), 7)
    h.eq(picker.rows(7, 22), 9)
    h.eq(picker.rows(10, 22), 12)
  end,

  rows_stop_at_what_the_screen_holds = function()
    h.eq(picker.rows(30, 22), 22)
  end,

  max_rows_fit_the_picker_on_the_screen = function()
    -- 94 points of search field and margins, then 42 per row.
    h.eq(picker.maxRows(1049), 22)
    h.eq(picker.maxRows(94 + 42 * 3), 3)
  end,

  max_rows_are_whole_for_a_float_screen_height = function()
    -- hs.chooser:rows() takes a whole number: 7.5 would set no rows at all.
    h.eq(math.type(picker.maxRows(1049.0)), "integer")
    h.eq(math.type(picker.rows(30, picker.maxRows(1049.0))), "integer")
  end,

  max_rows_keep_room_for_an_agent_and_the_legend = function()
    h.eq(picker.maxRows(100), 2)
  end,

  finds_the_frontmost_visible_chooser_of_hammerspoon = function()
    local windows = {
      window(7, "Chooser", true, { X = 0, Y = 0, Width = 10, Height = 10 }),
      window(HAMMERSPOON, "Hammerspoon Console", true, { X = 0, Y = 0, Width = 500, Height = 400 }),
      window(HAMMERSPOON, "Chooser", false, { X = 0, Y = 0, Width = 20, Height = 20 }),
      window(HAMMERSPOON, "Chooser", true, BOUNDS),
      window(HAMMERSPOON, "Chooser", true, { X = 1, Y = 1, Width = 30, Height = 30 }),
    }
    h.eq(picker.chooserWindow(windows, HAMMERSPOON), { x = -1344, y = 207, w = 768, h = 346, layer = 27 })
  end,

  no_chooser_window_when_none_is_visible = function()
    h.eq(picker.chooserWindow({ window(HAMMERSPOON, "Chooser", false, BOUNDS) }, HAMMERSPOON), nil)
    h.eq(picker.chooserWindow({}, HAMMERSPOON), nil)
  end,

  a_chooser_entry_without_bounds_is_skipped = function()
    local windows = { window(HAMMERSPOON, "Chooser", true, nil), window(HAMMERSPOON, "Chooser", true, BOUNDS) }
    h.eq(picker.chooserWindow(windows, HAMMERSPOON).h, 346)
  end,

  same_frame_compares_position_and_size = function()
    local frame = { x = 576, y = 207, w = 768, h = 346, layer = 27 }
    h.eq(picker.sameFrame(frame, { x = 576, y = 207, w = 768, h = 346, layer = 27 }), true)
    h.eq(picker.sameFrame(frame, { x = 580, y = 209, w = 760, h = 342, layer = 27 }), false)
    h.eq(picker.sameFrame(frame, nil), false)
  end,

  footer_covers_the_bottom_of_the_picker_with_the_text_centered = function()
    local footer = picker.footer({ x = -1344, y = 207, w = 768, h = 346 }, { w = 362, h = 15 }, { w = 170, h = 15 })
    h.eq(footer, {
      frame = { x = -1344, y = 525, w = 768, h = 28 },
      text = { x = 18, y = 7, w = 732, h = 15 },
      hint = true,
    })
  end,

  footer_drops_the_hint_when_it_does_not_fit_next_to_the_legend = function()
    local footer = picker.footer({ x = 0, y = 0, w = 576, h = 346 }, { w = 362, h = 15 }, { w = 170, h = 15 })
    h.eq(footer.hint, false)
  end,
}
