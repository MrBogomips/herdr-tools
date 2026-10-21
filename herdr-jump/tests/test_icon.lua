local h = ...
local icon = h.load("icon")

local CLEAR = "destinationOut"

local function isClear(el)
  return el.compositeRule == CLEAR
end

-- "stroke", "fill" or "clear" for each element, in drawing order.
local function actions(elements)
  local out = {}
  for i, el in ipairs(elements) do
    out[i] = isClear(el) and "clear" or el.action
  end
  return out
end

-- The box an element paints, stroke included; an arc counts as the upper half of its disc (the
-- menu bar shoulders), which bounds a left half too when its centre is the box's.
local function extent(el)
  local pad = (el.strokeWidth or 0) / 2
  if el.type == "circle" or el.type == "arc" then
    local c, r = el.center, el.radius
    local bottom = el.type == "arc" and c.y or c.y + r
    return c.x - r - pad, c.y - r - pad, c.x + r + pad, bottom + pad
  end
  local f = el.frame
  return f.x - pad, f.y - pad, f.x + f.w + pad, f.y + f.h + pad
end

return {
  idle_outlines_the_two_figures = function()
    h.eq(actions(icon.elements("idle")), { "stroke", "stroke", "clear", "clear", "clear", "stroke", "stroke" })
  end,

  waiting_fills_the_two_figures = function()
    h.eq(actions(icon.elements("waiting")), { "fill", "fill", "clear", "clear", "clear", "fill", "fill" })
  end,

  down_looks_like_idle = function()
    h.eq(icon.elements("down"), icon.elements("idle"))
  end,

  shoulders_are_the_upper_half_of_a_disc = function()
    local arcs = 0
    for _, el in ipairs(icon.elements("idle")) do
      if el.type == "arc" then
        arcs = arcs + 1
        h.eq({ el.startAngle, el.endAngle, el.arcRadii }, { 270, 90, true }, "arc " .. arcs)
      end
    end
    h.eq(arcs, 3, "arcs drawn or cleared")
  end,

  everything_stays_inside_the_icon_box = function()
    for _, state in ipairs({ "idle", "waiting" }) do
      for i, el in ipairs(icon.elements(state)) do
        local x1, y1, x2, y2 = extent(el)
        local inside = x1 >= 0 and y1 >= 0 and x2 <= icon.SIZE and y2 <= icon.SIZE
        h.eq(inside, true, state .. " element " .. i .. " within " .. icon.SIZE .. ": " .. x1 .. "," .. y1 .. " to " .. x2 .. "," .. y2)
      end
    end
  end,

  drawing_is_black_so_macos_can_tint_the_template = function()
    for _, el in ipairs(icon.elements("waiting")) do
      h.eq(el.fillColor or el.strokeColor, { white = 0 })
    end
  end,

  a_scale_factor_multiplies_every_length = function()
    local ones, twos = icon.elements("waiting", 1), icon.elements("waiting", 2)
    h.eq(#twos, #ones)
    for i, el in ipairs(ones) do
      local big = twos[i]
      if el.center then
        h.eq({ big.center.x, big.center.y, big.radius }, { el.center.x * 2, el.center.y * 2, el.radius * 2 }, "element " .. i)
      else
        h.eq(big.frame, { x = el.frame.x * 2, y = el.frame.y * 2, w = el.frame.w * 2, h = el.frame.h * 2 }, "element " .. i)
      end
      h.eq(big.strokeWidth, el.strokeWidth and el.strokeWidth * 2, "stroke " .. i)
    end
  end,

  waiting_statuses_are_a_filled_disc_with_a_white_mark = function()
    local orange = { red = 1, green = 0.58, blue = 0, alpha = 1 }
    for _, status in ipairs({ "blocked", "done" }) do
      local elements = icon.statusElements(status, orange, 32)
      local disc = elements[1]
      h.eq({ disc.type, disc.action, disc.fillColor }, { "circle", "fill", orange }, status .. " disc")
      h.eq(#elements > 1, true, status .. " has a mark")
      for i = 2, #elements do
        h.eq(elements[i].fillColor or elements[i].strokeColor, { white = 1, alpha = 1 }, status .. " mark " .. i)
      end
    end
  end,

  other_statuses_are_a_ring_in_their_color = function()
    local blue = { red = 0, green = 0.5, blue = 1, alpha = 1 }
    for _, status in ipairs({ "working", "idle", "unknown" }) do
      local ring = icon.statusElements(status, blue, 32)[1]
      h.eq({ ring.type, ring.action, ring.strokeColor }, { "circle", "stroke", blue }, status .. " ring")
    end
  end,

  working_fills_half_of_its_ring_and_idle_nothing_more = function()
    local blue = { red = 0, green = 0.5, blue = 1, alpha = 1 }
    local working = icon.statusElements("working", blue, 32)
    h.eq(#working, 2)
    h.eq({ working[2].type, working[2].action, working[2].arcRadii }, { "arc", "fill", true })
    h.eq(#icon.statusElements("idle", blue, 32), 1)
  end,

  status_icons_stay_inside_their_box = function()
    local grey = { white = 0.5, alpha = 1 }
    for _, status in ipairs({ "blocked", "done", "working", "idle", "unknown" }) do
      for i, el in ipairs(icon.statusElements(status, grey, 32)) do
        if el.type == "segments" then
          for _, p in ipairs(el.coordinates) do
            h.eq(p.x >= 0 and p.y >= 0 and p.x <= 32 and p.y <= 32, true, status .. " point " .. i)
          end
        elseif el.type ~= "text" then
          local x1, y1, x2, y2 = extent(el)
          h.eq(x1 >= 0 and y1 >= 0 and x2 <= 32 and y2 <= 32, true, status .. " element " .. i)
        end
      end
    end
  end,

  an_unknown_status_icon_is_an_error = function()
    local ok, err = pcall(icon.statusElements, "bogus", { white = 0 }, 32)
    h.eq(ok, false)
    h.eq(tostring(err):find("bogus", 1, true) ~= nil, true, err)
  end,

  an_unknown_state_is_an_error = function()
    local ok, err = pcall(icon.elements, "bogus")
    h.eq(ok, false)
    h.eq(tostring(err):find("bogus", 1, true) ~= nil, true, err)
  end,
}
