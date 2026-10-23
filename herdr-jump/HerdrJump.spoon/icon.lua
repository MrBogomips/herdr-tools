-- The menu bar icon: two agents, outlined while nothing waits and solid while some do, as
-- hs.canvas elements; and the colored status icons of the agent rows. elements() and
-- statusElements() are pure Lua, so they run in the tests; image() and status() need Hammerspoon.
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

-- Status icons, as shares of their box. A status that waits for the user is a filled disc with a
-- white mark (pause bars, check mark); the others are a ring (half filled while working, a "?" for
-- an unknown status). Filled means "waiting", as in the menu bar icon.
local BADGE = { radius = 0.34, ring = 0.07, bar = 0.075, barHeight = 0.28, barGap = 0.08, check = 0.075 }
local WHITE = { white = 1, alpha = 1 }
local QUESTION_FONT = "Helvetica-Bold"

local function disc(c, s, color)
  return { type = "circle", center = { x = c, y = c }, radius = s * BADGE.radius, action = "fill", fillColor = color }
end

local function ring(c, s, color)
  local width = s * BADGE.ring
  return { type = "circle", center = { x = c, y = c }, radius = s * BADGE.radius - width / 2,
    action = "stroke", strokeColor = color, strokeWidth = width }
end

local function pauseBars(c, s)
  local w, h, gap = s * BADGE.bar, s * BADGE.barHeight, s * BADGE.barGap
  local bars = {}
  for i, x in ipairs({ c - gap / 2 - w, c + gap / 2 }) do
    bars[i] = { type = "rectangle", frame = { x = x, y = c - h / 2, w = w, h = h },
      roundedRectRadii = { xRadius = w / 2, yRadius = w / 2 }, action = "fill", fillColor = WHITE }
  end
  return bars
end

local function checkMark(c, s)
  return { type = "segments", closed = false, action = "stroke", strokeColor = WHITE,
    strokeWidth = s * BADGE.check, strokeCapStyle = "round", strokeJoinStyle = "round",
    coordinates = { { x = c - 0.16 * s, y = c + 0.01 * s }, { x = c - 0.05 * s, y = c + 0.12 * s },
      { x = c + 0.16 * s, y = c - 0.11 * s } } }
end

-- The left half of the disc inside the ring, flat side right.
local function leftHalf(c, s, color)
  return { type = "arc", center = { x = c, y = c }, radius = s * (BADGE.radius - BADGE.ring / 2),
    startAngle = 180, endAngle = 360, arcRadii = true, action = "fill", fillColor = color }
end

local function question(c, s, color)
  local size = s * 0.42
  return { type = "text", text = "?", textFont = QUESTION_FONT, textSize = size, textColor = color,
    textAlignment = "center", frame = { x = 0, y = c - size * 0.62, w = s, h = size * 1.3 } }
end

local STATUS = {
  blocked = function(c, s, color)
    local bars = pauseBars(c, s)
    return { disc(c, s, color), bars[1], bars[2] }
  end,
  done = function(c, s, color) return { disc(c, s, color), checkMark(c, s) } end,
  working = function(c, s, color) return { ring(c, s, color), leftHalf(c, s, color) } end,
  idle = function(c, s, color) return { ring(c, s, color) } end,
  unknown = function(c, s, color) return { ring(c, s, color), question(c, s, color) } end,
}

-- The hs.canvas elements of a status icon in a color, centred in a box of the given side.
function M.statusElements(status, color, size)
  local draw = STATUS[status]
  if draw == nil then
    error("unknown agent status '" .. tostring(status) .. "'", 2)
  end
  return draw(size / 2, size, color)
end

local function render(elements, size)
  local canvas = hs.canvas.new({ x = 0, y = 0, w = size, h = size })
  for _, el in ipairs(elements) do
    canvas[#canvas + 1] = el
  end
  local image = canvas:imageFromCanvas()
  canvas:delete()
  return image
end

-- The icon of a state as a template image, for hs.menubar:setIcon. Needs Hammerspoon.
function M.image(state)
  local image = render(M.elements(state), M.SIZE)
  image:template(true)
  return image
end

-- A status icon as an image that keeps its colors (not a template). Needs Hammerspoon.
function M.status(status, color, size)
  return render(M.statusElements(status, color, size), size)
end

return M
