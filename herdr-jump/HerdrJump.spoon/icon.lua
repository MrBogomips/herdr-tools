-- The menu bar icon: two agents, outlined while nothing waits and solid while some do, as
-- hs.canvas elements. elements() is pure Lua, so it runs in the tests; image() needs Hammerspoon.
--
-- The drawing is black on a transparent canvas and the image is flagged as a template, so macOS
-- tints it for light and dark menu bars. The front figure erases what it covers (compositing rule
-- "destinationOut") before it is drawn, which keeps a gap between the two outlines.

local M = {}

M.SIZE = 18 -- points on a side; a menu bar icon
local STROKE = 1.4
local GAP = 0.9 -- erased around the front figure
local BLACK = { white = 0 }

-- Head centre and radius, the gap to the shoulders, the shoulders' radius.
local BACK = { x = 12, y = 5.2, head = 2.8, gap = 1.0, shoulders = 4.6 }
local FRONT = { x = 6.5, y = 6.4, head = 3.3, gap = 1.2, shoulders = 5.6 }

local MODE = { idle = "stroke", waiting = "fill", down = "stroke" }

-- Appends elements scaled by k; a mode is "fill", "stroke" or "clear".
local function painter(k, elements)
  local function add(el, mode)
    if mode == "fill" then
      el.action, el.fillColor = "fill", BLACK
    elseif mode == "stroke" then
      el.action, el.strokeColor, el.strokeWidth = "stroke", BLACK, STROKE * k
    else
      el.action, el.fillColor, el.compositeRule = "fill", BLACK, "destinationOut"
    end
    elements[#elements + 1] = el
  end
  local p = {}
  function p.circle(cx, cy, r, mode)
    add({ type = "circle", center = { x = cx * k, y = cy * k }, radius = r * k }, mode)
  end
  -- The upper half of a disc, flat side down.
  function p.halfDisc(cx, cy, r, mode)
    add({ type = "arc", center = { x = cx * k, y = cy * k }, radius = r * k,
      startAngle = 270, endAngle = 90, arcRadii = true }, mode)
  end
  function p.rect(x, y, w, h, mode)
    add({ type = "rectangle", frame = { x = x * k, y = y * k, w = w * k, h = h * k } }, mode)
  end
  return p
end

-- A person: a head over shoulders. Clearing also erases the gap between them.
local function figure(p, f, mode)
  local cy = f.y + f.head + f.gap + f.shoulders
  if mode == "clear" then
    p.circle(f.x, f.y, f.head + GAP, "clear")
    p.halfDisc(f.x, cy, f.shoulders + GAP, "clear")
    p.rect(f.x - f.head, f.y, 2 * f.head, cy - f.y, "clear")
    return
  end
  p.circle(f.x, f.y, f.head, mode)
  p.halfDisc(f.x, cy, f.shoulders, mode)
end

-- The hs.canvas elements of the icon for a state ("idle", "waiting" or "down"), in drawing
-- order, for a canvas SIZE * scale points on a side.
function M.elements(state, scale)
  local mode = MODE[state]
  if mode == nil then
    error("unknown icon state '" .. tostring(state) .. "'", 2)
  end
  local elements = {}
  local p = painter(scale or 1, elements)
  figure(p, BACK, mode)
  figure(p, FRONT, "clear")
  figure(p, FRONT, mode)
  return elements
end

-- The icon of a state as a template image, for hs.menubar:setIcon. Needs Hammerspoon.
function M.image(state)
  local canvas = hs.canvas.new({ x = 0, y = 0, w = M.SIZE, h = M.SIZE })
  for _, el in ipairs(M.elements(state)) do
    canvas[#canvas + 1] = el
  end
  local image = canvas:imageFromCanvas()
  canvas:delete()
  image:template(true)
  return image
end

return M
