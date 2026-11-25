-- The agents picker: what its page shows (the model init.lua sends to picker.html), which rows
-- get ⌘1…⌘9, and where its window goes.
-- Pure Lua: panel.lua draws the page in an hs.webview.

local M = {}

-- Row heights in points, by depth, as picker.html draws them: a sub-session is one compact line.
M.ROW = { [0] = 46, [1] = 24 }
-- The rest of the window: the filter field, the list's padding, the legend footer and the border.
M.CHROME = 56 + 12 + 30 + 2
-- The window's width, the room left around it on a small screen, and how far down it sits.
M.WIDTH, M.MARGIN, M.TOP = 780, 24, 0.12

local WAITING = { blocked = true, done = true }

-- New rows where each waiting one (blocked, or done and not seen) gets a shortcut key, 1 to 9 in
-- list order; the others are chosen by hand.
function M.shortcuts(rows)
  local out, next = {}, 1
  for i, row in ipairs(rows) do
    local copy = {}
    for k, v in pairs(row) do
      copy[k] = v
    end
    if WAITING[row.status] and next <= 9 then
      copy.key = next
      next = next + 1
    end
    out[i] = copy
  end
  return out
end

-- An hs.drawing color (components 0 to 1) as CSS.
function M.css(color)
  local function byte(v)
    return math.floor((v or 0) * 255 + 0.5)
  end
  return ("rgb(%d, %d, %d)"):format(byte(color.red), byte(color.green), byte(color.blue))
end

-- What picker.html renders: rows (from attention.rows, with shortcuts), the legend and its hint,
-- the filter's placeholder and the status colors.
function M.model(rows, legend, placeholder, colors)
  local out, css = {}, {}
  for i, row in ipairs(rows) do
    out[i] = {
      pane = row.paneId, title = row.text, sub = row.subText, when = row.when, status = row.status,
      depth = row.depth or 0, key = row.key,
    }
  end
  for status, color in pairs(colors) do
    css[status] = M.css(color)
  end
  return { rows = out, legend = legend, placeholder = placeholder, colors = css }
end

-- The window for these rows on a screen frame: centred, in the upper part, as tall as the rows
-- and no taller than the screen allows (the list scrolls then).
function M.frame(screen, rows)
  local height = M.CHROME
  for _, row in ipairs(rows) do
    height = height + (M.ROW[row.depth or 0] or M.ROW[1])
  end
  local width = math.min(M.WIDTH, screen.w - 2 * M.MARGIN)
  local top = math.floor(screen.h * M.TOP)
  height = math.max(M.CHROME + M.ROW[0], math.min(height, screen.h - top - M.MARGIN))
  return { x = screen.x + (screen.w - width) // 2, y = screen.y + top, w = width, h = height }
end

-- The page with the model's JSON in place of __MODEL__; "</" is escaped so that no text in the
-- model can close the page's script.
function M.inline(template, json)
  local safe = json:gsub("</", "<\\/")
  local start, finish = template:find("__MODEL__", 1, true)
  if start == nil then
    return template
  end
  return template:sub(1, start - 1) .. safe .. template:sub(finish + 1)
end

return M
