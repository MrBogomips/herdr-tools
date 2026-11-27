local h = ...
local attention = h.load("attention")
local menubar = h.load("menubar")
local bar = menubar.new(attention)

return {
  legend_explains_the_glyphs_and_the_order = function()
    h.eq(bar.legend("fifo"), {
      hint = "Sorted FIFO · Tab: LIFO, name · ⌥↑↓ masters · ⇧↑↓ waiting",
      parts = {
        { status = "blocked", glyph = "⏸", meaning = "blocked" },
        { status = "done", glyph = "✓", meaning = "done, not seen" },
        { status = "unknown", glyph = "?", meaning = "unknown" },
        { status = "idle", glyph = "○", meaning = "idle" },
        { status = "working", glyph = "◐", meaning = "working" },
        { status = "mark", glyph = "", meaning = "to review" },
      },
    })
    h.eq(bar.legend("name").hint, "Sorted by name · Tab: FIFO, LIFO · ⌥↑↓ masters · ⇧↑↓ waiting")
  end,

  placeholder_names_the_order = function()
    h.eq(bar.placeholder("lifo"), "Filter agents · sorted LIFO (Tab to change)")
    h.eq(bar.placeholder("name"), "Filter agents · sorted by name (Tab to change)")
  end,

  menu_lists_the_rows_then_the_sort_choices_and_the_legend = function()
    local rows = {
      { text = "ACME", subText = "blocked 12m · acme-api", paneId = "w2:p3", status = "blocked", age = "12m" },
      { text = "Lumon", subText = "idle", paneId = "w1:p1", status = "idle" },
    }
    h.eq(bar.menu(rows, nil, "lifo"), {
      { title = "ACME · 12m", tooltip = "blocked 12m · acme-api", paneId = "w2:p3", status = "blocked" },
      { title = "Lumon", tooltip = "idle", paneId = "w1:p1", status = "idle" },
      { title = "-" },
      { title = "Sort by", menu = {
        { title = "FIFO: oldest first", order = "fifo", checked = false },
        { title = "LIFO: newest first", order = "lifo", checked = true },
        { title = "By name", order = "name", checked = false },
      } },
      { title = "Legend", menu = {
        { title = "blocked", status = "blocked" },
        { title = "done, not seen", status = "done" },
        { title = "unknown", status = "unknown" },
        { title = "idle", status = "idle" },
        { title = "working", status = "working" },
        { title = "to review: pink, yellow, teal" },
      } },
    })
  end,

  menu_says_when_there_is_no_agent = function()
    h.eq(bar.menu({}, nil), { { title = "No Herdr agents", disabled = true } })
  end,

  menu_shows_the_error_instead_of_stale_rows = function()
    local rows = { { text = "· Lumon", subText = "idle", paneId = "w1:p1", status = "idle" } }
    h.eq(bar.menu(rows, "Herdr is not running"), { { title = "Herdr is not running", disabled = true } })
  end,

  menubar_title_shows_the_count_only_when_something_waits = function()
    h.eq(menubar.title(0), "")
    h.eq(menubar.title(2), "2")
    h.eq(menubar.title(nil), "")
  end,

  menubar_title_says_it_cannot_tell_when_herdr_fails = function()
    h.eq(menubar.title(0, "Herdr is not running"), "?")
    h.eq(menubar.title(3, "Herdr is not answering"), "?")
  end,

  menubar_icon_state_follows_the_count_unless_herdr_fails = function()
    h.eq(menubar.state(0), "idle")
    h.eq(menubar.state(nil), "idle")
    h.eq(menubar.state(2), "waiting")
    h.eq(menubar.state(0, "Herdr is not running"), "down")
    h.eq(menubar.state(3, "Herdr is not answering"), "down")
  end,

  menu_says_a_marked_row_is_to_review_and_in_which_color = function()
    local rows = {
      { text = "Initech", subText = "idle 2h", paneId = "w1:p1", status = "idle", age = "2h", markColor = 2 },
    }
    h.eq(bar.menu(rows, nil, "fifo")[1],
      { title = "Initech · 2h · to review (yellow)", tooltip = "idle 2h", paneId = "w1:p1", status = "idle" })
  end,

  the_marks_have_names = function()
    h.eq(menubar.MARK_NAMES, { "pink", "yellow", "teal" })
    h.eq(#menubar.MARK_NAMES, #attention.MARK_COLORS)
  end,
}
