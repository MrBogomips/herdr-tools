-- Where the agents picker's legend goes: a footer drawn over free space left at the bottom of the
-- hs.chooser window, so it cannot be selected like a choice.
-- Pure Lua: init.lua passes in what Hammerspoon reports and draws the result.
--
-- hs.chooser has no footer and no frame getter: its window is as tall as its `rows` setting,
-- whatever the number of choices, and hs.window.list() reports where it is.

local M = {}

-- hs.chooser's geometry on Hammerspoon 1.1.1 (macOS 26), in points: the window is the search field
-- and margins plus 42 per `rows`, but its first row starts 99 down and macOS draws a row every 44,
-- so each agent takes more than one `rows`. Rows drawn shorter would only leave more room.
local CHROME, ROW, LIST_TOP, ROW_DRAWN = 94, 42, 99, 44
-- The footer: its height (a separator line, then one line of text), the least room between it and
-- the last row, and the text's side margin, which lines it up with the status icons; the room
-- between the legend and the hint.
local FOOTER_HEIGHT, FOOTER_GAP, SEPARATOR, TEXT_INSET, HINT_GAP = 28, 6, 1, 18, 24

-- The chooser rows that fit on a screen this tall: at least one agent and the legend. A whole
-- number: hs.chooser:rows() sets no rows at all for 7.5.
function M.maxRows(screenHeight)
  return math.max(2, math.floor((screenHeight - CHROME) / ROW))
end

-- The chooser rows for this many agents with the legend under them, as many as fit.
function M.rows(count, maxRows)
  local needed = LIST_TOP - CHROME + ROW_DRAWN * count + FOOTER_GAP + FOOTER_HEIGHT
  return math.min(math.ceil(needed / ROW), maxRows)
end

-- The visible chooser window of this process, frontmost first, from hs.window.list(true) entries:
-- its frame and window level, or nil.
function M.chooserWindow(windows, pid)
  for _, w in ipairs(windows) do
    local b = w.kCGWindowBounds
    if w.kCGWindowOwnerPID == pid and w.kCGWindowName == "Chooser" and w.kCGWindowIsOnscreen == true
      and type(b) == "table" then
      return { x = b.X, y = b.Y, w = b.Width, h = b.Height, layer = w.kCGWindowLayer }
    end
  end
  return nil
end

-- Whether two chooser window frames have the same position and size. The window zooms in when it
-- opens, so its first frames are smaller.
function M.sameFrame(a, b)
  return b ~= nil and a.x == b.x and a.y == b.y and a.w == b.w and a.h == b.h
end

-- The footer of a chooser window: its frame on screen, the text frame inside it (the legend on the
-- left, the hint on the right), and whether the hint fits next to the legend.
function M.footer(bounds, legendSize, hintSize)
  local width = bounds.w - 2 * TEXT_INSET
  return {
    frame = { x = bounds.x, y = bounds.y + bounds.h - FOOTER_HEIGHT, w = bounds.w, h = FOOTER_HEIGHT },
    text = {
      x = TEXT_INSET,
      y = SEPARATOR + (FOOTER_HEIGHT - SEPARATOR - legendSize.h) // 2,
      w = width,
      h = legendSize.h,
    },
    hint = legendSize.w + HINT_GAP + hintSize.w <= width,
  }
end

return M
