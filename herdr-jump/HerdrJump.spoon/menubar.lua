-- What the menu bar and the picker's footer say: the counter title, the icon state, the drop-down
-- entries, the legend and the sort names.
-- Pure Lua: no hs.* calls, so it runs under plain Lua in the tests.
--
-- title and state need nothing. new(attention) returns legend, placeholder and menu, which read
-- the statuses and sort orders of the attention module (STATUSES, ORDERS, order, nextOrder).

local M = {}

-- The names of the bookmark colors an agent marked to review can have, in the order of
-- attention.MARK_COLORS.
M.MARK_NAMES = { "pink", "yellow", "teal" }

local ORDER_NAME = { fifo = "FIFO", lifo = "LIFO", name = "by name" }
local ORDER_SHORT = { fifo = "FIFO", lifo = "LIFO", name = "name" }
local SORT_TITLE = { fifo = "FIFO: oldest first", lifo = "LIFO: newest first", name = "By name" }
-- The legend's text glyphs, close to the symbol inside each status icon (icon.lua).
local GLYPH = { blocked = "⏸", done = "✓", unknown = "?", idle = "○", working = "◐" }
local MEANING = { done = "done, not seen" }
-- The picker's keys besides Tab, shown after the order: arrows with a modifier.
local NAV_HINT = "⌥↑↓ masters · ⇧↑↓ waiting"
-- The legend's last part: the bookmark of a marked agent, which the page draws itself.
local MARK_PART = { status = "mark", glyph = "", meaning = "to review" }

-- The menu bar title, shown next to the icon: the count when something waits, nothing otherwise.
-- With an error the count is unknown, which must not look like "nothing waits".
function M.title(count, err)
  if err then
    return "?"
  end
  if not count or count == 0 then
    return ""
  end
  return tostring(count)
end

-- Which icon the menu bar shows: "down" when Herdr cannot be read, "waiting" while agents wait.
function M.state(count, err)
  if err then
    return "down"
  end
  return (count or 0) > 0 and "waiting" or "idle"
end

-- The text builders for the statuses and orders of `attention`.
function M.new(attention)
  -- What each glyph means, most urgent first, as parts (to color each glyph).
  local function legendParts()
    local parts = {}
    for i, status in ipairs(attention.STATUSES) do
      parts[i] = { status = status, glyph = GLYPH[status], meaning = MEANING[status] or status }
    end
    return parts
  end

  -- The orders Tab moves to from this one, in cycle order.
  local function others(order)
    local names, following = {}, attention.nextOrder(order)
    while following ~= order do
      names[#names + 1] = ORDER_SHORT[following]
      following = attention.nextOrder(following)
    end
    return table.concat(names, ", ")
  end

  local bar = {}

  -- The picker's footer line: what the glyphs mean, then the order, where Tab goes and the arrows.
  function bar.legend(order)
    order = attention.order(order)
    local parts = legendParts()
    parts[#parts + 1] = MARK_PART
    return {
      parts = parts,
      hint = ("Sorted %s · Tab: %s · %s"):format(ORDER_NAME[order], others(order), NAV_HINT),
    }
  end

  -- The picker's filter field text while nothing is typed.
  function bar.placeholder(order)
    return ("Filter agents · sorted %s (Tab to change)"):format(ORDER_NAME[attention.order(order)])
  end

  -- Menu bar drop-down entries (hs.menubar format): the rows, the sort choices, the legend. The
  -- caller attaches the status icons and the click handlers: a jump for an entry with a paneId, a
  -- sort for one with an order. An error replaces the rows, which would be stale.
  function bar.menu(rows, err, order)
    if err then
      return { { title = err, disabled = true } }
    end
    if #rows == 0 then
      return { { title = "No Herdr agents", disabled = true } }
    end
    order = attention.order(order)
    local items = {}
    for i, row in ipairs(rows) do
      local title = row.age and (row.text .. " · " .. row.age) or row.text
      if row.markColor then
        title = ("%s · to review (%s)"):format(title, M.MARK_NAMES[row.markColor])
      end
      items[i] = { title = title, tooltip = row.subText, paneId = row.paneId, status = row.status, indent = row.depth }
    end
    local sorts, legend = {}, {}
    for i, name in ipairs(attention.ORDERS) do
      sorts[i] = { title = SORT_TITLE[name], order = name, checked = name == order }
    end
    for i, part in ipairs(legendParts()) do
      legend[i] = { title = part.meaning, status = part.status }
    end
    legend[#legend + 1] = { title = MARK_PART.meaning .. ": " .. table.concat(M.MARK_NAMES, ", ") }
    items[#items + 1] = { title = "-" }
    items[#items + 1] = { title = "Sort by", menu = sorts }
    items[#items + 1] = { title = "Legend", menu = legend }
    return items
  end

  return bar
end

return M
