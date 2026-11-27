local h = ...
local picker = h.load("picker")

local function row(pane, status, depth)
  return { paneId = pane, text = pane, subText = status .. " · x", when = status, status = status, depth = depth }
end

local function keys(model)
  local out = {}
  for i, r in ipairs(model.rows) do
    out[i] = r.key or 0
  end
  return out
end

local function model(rows)
  return picker.model(rows, { parts = {}, hint = "" }, "", {})
end

local SCREEN = { x = 0, y = 25, w = 1440, h = 875 }

return {
  shortcuts_go_to_waiting_rows_only_in_list_order = function()
    local rows = {
      row("a", "blocked"), row("b", "idle", 1), row("c", "done", 1), row("d", "working"), row("e", "done"),
    }
    h.eq(keys(model(rows)), { 1, 0, 2, 0, 3 })
  end,

  shortcuts_stop_at_nine = function()
    local rows = {}
    for i = 1, 11 do
      rows[i] = row("p" .. i, "done")
    end
    local out = model(rows).rows
    h.eq(out[9].key, 9)
    h.eq(out[10].key, nil)
  end,

  css_colors_come_from_hammerspoon_colors = function()
    h.eq(picker.css({ red = 1.0, green = 0.58, blue = 0.0, alpha = 1 }), "rgb(255, 148, 0)")
  end,

  the_model_carries_rows_legend_hint_and_colors = function()
    local legend = { parts = { { status = "done", glyph = "✓", meaning = "done, not seen" } }, hint = "Sorted FIFO · Tab: LIFO, name" }
    local rows = { row("w1:p1", "done"), row("w1:p2", "idle", 1) }
    local model = picker.model(rows, legend, "Filter agents", { done = { red = 0, green = 1, blue = 0 } },
      { { red = 1, green = 0, blue = 0 }, { red = 0, green = 0, blue = 1 } })
    h.eq(model.rows[1], {
      pane = "w1:p1", title = "w1:p1", sub = "done · x", when = "done", status = "done", depth = 0, key = 1, waits = true,
      mark = 0,
    })
    h.eq(model.rows[2].waits, false)
    h.eq(model.rows[2].depth, 1)
    h.eq(model.placeholder, "Filter agents")
    h.eq(model.legend, legend)
    h.eq(model.colors, { done = "rgb(0, 255, 0)" })
    h.eq(model.markColors, { "rgb(255, 0, 0)", "rgb(0, 0, 255)" })
  end,

  marked_rows_carry_their_mark_color_and_the_others_zero = function()
    local rows = { row("a", "done"), row("b", "working"), row("c", "blocked") }
    rows[2].markColor, rows[3].markColor = 3, 1
    local model = picker.model(rows, { parts = {}, hint = "" }, "", {}, {})
    h.eq({ model.rows[1].mark, model.rows[2].mark, model.rows[3].mark }, { 0, 3, 1 })
  end,

  waiting_rows_are_the_ones_with_shortcuts_and_beyond_the_ninth = function()
    local rows = {}
    -- Nine done rows (six between idle ones, three in a row), then a tenth waiting row: a blocked
    -- sub-session with no shortcut left.
    for i = 1, 11 do
      rows[i] = row("p" .. i, i % 2 == 0 and "idle" or "done")
    end
    rows[12] = row("d1", "done")
    rows[13] = row("d2", "done")
    rows[14] = row("d3", "done")
    rows[15] = row("b", "blocked", 1)
    rows[16] = row("w", "working", 1)
    local model = model(rows)
    for i, r in ipairs(model.rows) do
      h.eq(r.waits, r.status == "blocked" or r.status == "done", "row " .. i)
      if r.key then
        h.eq(r.waits, true, "row " .. i)
      end
    end
    h.eq(model.rows[14].key, 9)
    h.eq(model.rows[15].key, nil)
    h.eq(model.rows[15].waits, true)
  end,

  a_seen_done_row_reported_idle_does_not_wait = function()
    local model = picker.model({ row("a", "idle") }, { parts = {}, hint = "" }, "", {})
    h.eq(model.rows[1].waits, false)
  end,

  a_sub_session_row_is_lower_than_a_top_level_row = function()
    h.eq(picker.ROW[1] < picker.ROW[0], true)
  end,

  the_frame_fits_the_rows_and_sits_centred_in_the_upper_screen = function()
    local rows = { row("a", "idle"), row("b", "idle", 1), row("c", "idle", 1) }
    local frame = picker.frame(SCREEN, rows)
    h.eq(frame.h, picker.CHROME + picker.ROW[0] + 2 * picker.ROW[1])
    h.eq(frame.w, picker.WIDTH)
    h.eq(frame.x, (1440 - picker.WIDTH) // 2)
    h.eq(frame.y > SCREEN.y and frame.y < SCREEN.y + SCREEN.h / 4, true)
  end,

  the_frame_stops_at_what_the_screen_holds = function()
    local rows = {}
    for i = 1, 60 do
      rows[i] = row("p" .. i, "idle")
    end
    local frame = picker.frame(SCREEN, rows)
    h.eq(frame.y + frame.h <= SCREEN.y + SCREEN.h, true)
    h.eq(frame.h >= picker.CHROME + picker.ROW[0], true)
  end,

  the_frame_narrows_on_a_small_screen = function()
    h.eq(picker.frame({ x = 0, y = 0, w = 500, h = 400 }, {}).w <= 500 - 2 * picker.MARGIN, true)
  end,

  the_page_has_one_place_for_the_model_in_its_script = function()
    local here = debug.getinfo(1, "S").source:match("^@(.*)/[^/]*$") or "."
    local file = assert(io.open(here .. "/../HerdrJump.spoon/picker.html", "r"))
    local page = file:read("a")
    file:close()
    local _, count = page:gsub("__MODEL__", "")
    h.eq(count, 1)
    h.eq(page:find("let model = __MODEL__;", 1, true) ~= nil, true)
    local _, navs = page:gsub('<script id="nav">', "")
    h.eq(navs, 1)
  end,

  the_model_is_inlined_in_the_page_without_closing_its_script = function()
    local page = picker.inline("<script>let model = __MODEL__;</script>", '{"t":"</script><b>","p":"100%"}')
    h.eq(page, '<script>let model = {"t":"<\\/script><b>","p":"100%"};</script>')
  end,
}
