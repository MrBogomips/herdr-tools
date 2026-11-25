local h = ...
local chime = h.load("chime")

local function agent(pane, status, seq, fields)
  local a = { pane_id = pane, agent_status = status, state_change_seq = seq, focused = false }
  for k, v in pairs(fields or {}) do
    a[k] = v
  end
  return a
end

local function statusOf(a)
  return a.agent_status
end

local never = function() return false end

return {
  settings_are_off_unless_set = function()
    h.eq(chime.settings(nil), nil)
    h.eq(chime.settings(false), nil)
  end,

  settings_true_takes_the_default_sounds = function()
    h.eq(chime.settings(true), { blocked = "Ping", done = "Glass" })
  end,

  settings_take_one_sound_for_both_or_one_per_status = function()
    h.eq(chime.settings("Hero"), { blocked = "Hero", done = "Hero" })
    h.eq(chime.settings({ done = "~/s/done.mp3" }), { blocked = "Ping", done = "~/s/done.mp3" })
  end,

  settings_refuse_anything_else = function()
    local value, err = chime.settings(42)
    h.eq(value, nil)
    h.eq(err, "sound must be true, a sound name, a file path or { blocked = …, done = … }")
    value, err = chime.settings({ blocked = 3 })
    h.eq(value, nil)
    h.eq(err ~= nil, true)
  end,

  a_sound_with_a_slash_is_a_file = function()
    h.eq(chime.isFile("Glass"), false)
    h.eq(chime.isFile("/x/done.mp3"), true)
    h.eq(chime.isFile("~/done.mp3"), true)
  end,

  the_first_poll_only_records = function()
    local agents = { agent("w1:p1", "blocked", 3) }
    h.eq(chime.events(nil, agents, statusOf, never, never), {})
  end,

  an_agent_entering_blocked_or_done_chimes = function()
    local before = chime.snapshot({ agent("w1:p1", "working", 3), agent("w1:p2", "working", 4) }, statusOf)
    local now = { agent("w1:p1", "blocked", 5), agent("w1:p2", "done", 6) }
    h.eq(chime.events(before, now, statusOf, never, never), { { pane = "w1:p1", status = "blocked" }, { pane = "w1:p2", status = "done" } })
  end,

  an_agent_waiting_as_before_does_not_chime_again = function()
    local before = chime.snapshot({ agent("w1:p1", "blocked", 5) }, statusOf)
    h.eq(chime.events(before, { agent("w1:p1", "blocked", 5) }, statusOf, never, never), {})
  end,

  a_new_wait_of_the_same_status_between_two_polls_chimes = function()
    local before = chime.snapshot({ agent("w1:p1", "done", 5) }, statusOf)
    h.eq(chime.events(before, { agent("w1:p1", "done", 8) }, statusOf, never, never), { { pane = "w1:p1", status = "done" } })
  end,

  a_new_pane_already_waiting_chimes = function()
    local before = chime.snapshot({}, statusOf)
    h.eq(chime.events(before, { agent("w1:p9", "blocked", 1) }, statusOf, never, never), { { pane = "w1:p9", status = "blocked" } })
  end,

  quiet_and_watched_agents_do_not_chime = function()
    local before = chime.snapshot({ agent("w1:p1", "working", 1), agent("w1:p2", "working", 2) }, statusOf)
    local now = { agent("w1:p1", "done", 3), agent("w1:p2", "blocked", 4) }
    local quiet = function(a) return a.pane_id == "w1:p1" end
    local watched = function(a) return a.pane_id == "w1:p2" end
    h.eq(chime.events(before, now, statusOf, quiet, watched), {})
  end,

  blocked_wins_the_one_sound_of_a_poll = function()
    h.eq(chime.sound({ { status = "done" }, { status = "blocked" } }), "blocked")
    h.eq(chime.sound({ { status = "done" } }), "done")
    h.eq(chime.sound({}), nil)
  end,

  herdr_config_sits_next_to_the_default_socket_or_above_a_session = function()
    h.eq(chime.herdrConfigPath("/u/.config/herdr/herdr.sock"), "/u/.config/herdr/config.toml")
    h.eq(chime.herdrConfigPath("/u/.config/herdr/sessions/work/herdr.sock"), "/u/.config/herdr/config.toml")
    h.eq(chime.herdrConfigPath(nil), nil)
  end,

  herdr_sound_is_on_unless_the_config_turns_it_off = function()
    h.eq(chime.herdrSoundOn(nil), nil)
    h.eq(chime.herdrSoundOn("[ui]\naccent = \"#fff\"\n"), true)
    h.eq(chime.herdrSoundOn("[ui.sound]\n# keep quiet\nenabled = false # herdr-jump\n"), false)
    h.eq(chime.herdrSoundOn("[ui.sound]\nenabled = true\n"), true)
    h.eq(chime.herdrSoundOn("[ui]\nsound.enabled = false\n"), false)
    h.eq(chime.herdrSoundOn("[ui]\nsound = { enabled = false, path = \"x.mp3\" }\n"), false)
    h.eq(chime.herdrSoundOn("ui.sound.enabled = false\n[keys]\n"), false)
    h.eq(chime.herdrSoundOn("[ui.sound]\n[keys]\nenabled = false\n"), true)
  end,

  herdr_sound_is_unknown_without_a_readable_config = function()
    h.eq(chime.readHerdrSound("/nonexistent-herdr-jump-test/herdr.sock"), nil)
  end,

  status_reads_herdr_only_while_sounds_play = function()
    h.eq(chime.status(nil, nil, "/nonexistent-herdr-jump-test/herdr.sock"),
      { on = false, config = "/nonexistent-herdr-jump-test/config.toml" })
    local sounds = { blocked = "Ping", done = "Glass" }
    h.eq(chime.status(sounds, nil, "/nonexistent-herdr-jump-test/herdr.sock").on, true)
  end,
}
