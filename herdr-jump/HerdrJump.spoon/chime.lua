-- When HerdrJump plays a sound, and which one. Off unless `sound` is set: Herdr plays its own
-- sounds, for every pane of a kind of agent, sub-sessions included; HerdrJump can leave the
-- sub-sessions that are done out, once Herdr's sound is turned off.
-- Pure Lua apart from player(), which needs Hammerspoon when it plays.

local M = {}

M.DEFAULT = { blocked = "Ping", done = "Glass" }
local INVALID = "sound must be true, a sound name, a file path or { blocked = …, done = … }"
local WAITS = { blocked = true, done = true }

local function soundName(value)
  return type(value) == "string" and value ~= ""
end

-- The sounds to play, { blocked = name or path, done = name or path }, or nil when off; nil and a
-- message for a value it cannot use.
function M.settings(value)
  if value == nil or value == false then
    return nil
  end
  if value == true then
    return { blocked = M.DEFAULT.blocked, done = M.DEFAULT.done }
  end
  if soundName(value) then
    return { blocked = value, done = value }
  end
  if type(value) ~= "table" then
    return nil, INVALID
  end
  local sounds = {}
  for status in pairs(WAITS) do
    local chosen = value[status]
    if chosen ~= nil and not soundName(chosen) then
      return nil, INVALID
    end
    sounds[status] = chosen or M.DEFAULT[status]
  end
  return sounds
end

-- A sound with a slash is a file (an mp3, aiff, wav…); otherwise a system sound name.
function M.isFile(sound)
  return sound:find("/", 1, true) ~= nil
end

-- What the next poll compares with: each pane's status as the user sees it and its change counter.
function M.snapshot(agents, statusOf)
  local snap = {}
  for _, agent in ipairs(agents) do
    snap[agent.pane_id] = { status = statusOf(agent), seq = agent.state_change_seq }
  end
  return snap
end

-- The agents that started waiting since the previous snapshot: they entered blocked or done, or
-- waited again (their change counter moved between two polls), or appeared already waiting.
-- Without a previous snapshot (the first poll, or the first after Herdr was unreachable) it
-- only records. quiet(agent) and watched(agent) leave an agent out.
function M.events(previous, agents, statusOf, quiet, watched)
  local events = {}
  if previous == nil then
    return events
  end
  for _, agent in ipairs(agents) do
    local status = statusOf(agent)
    local before = previous[agent.pane_id]
    local changed = before == nil or before.status ~= status or before.seq ~= agent.state_change_seq
    if WAITS[status] and changed and not quiet(agent) and not watched(agent) then
      events[#events + 1] = { pane = agent.pane_id, status = status }
    end
  end
  return events
end

-- The one sound of a poll: blocked over done, or nil.
function M.sound(events)
  local found
  for _, event in ipairs(events) do
    if event.status == "blocked" then
      return "blocked"
    end
    found = "done"
  end
  return found
end

-- Herdr's config.toml for a socket: the default socket sits in Herdr's config folder, a named
-- session's in <config>/sessions/<name>/.
function M.herdrConfigPath(socketPath)
  if type(socketPath) ~= "string" then
    return nil
  end
  local folder = socketPath:match("^(.*)/[^/]*$")
  if folder == nil then
    return nil
  end
  folder = folder:match("^(.*)/sessions/[^/]+$") or folder
  return folder .. "/config.toml"
end

local function uncommented(line)
  return (line:gsub("#.*$", ""):gsub("^%s+", ""):gsub("%s+$", ""))
end

-- Whether ui.sound.enabled is false in this config.toml text, in any of its spellings: a [ui.sound]
-- table, a dotted key, an inline table. Not a TOML parser: enough for one boolean key.
local function soundOff(text)
  local table_ = ""
  for raw in (text .. "\n"):gmatch("([^\n]*)\n") do
    local line = uncommented(raw)
    local header = line:match("^%[%s*([%w_.%-]+)%s*%]$")
    if header then
      table_ = header
    else
      local key, value = line:match("^([%w_.%-]+)%s*=%s*(.-)$")
      if key then
        local full = table_ == "" and key or (table_ .. "." .. key)
        if full == "ui.sound.enabled" and value == "false" then
          return true
        end
        if full == "ui.sound" and value:match("[{,]%s*enabled%s*=%s*false") then
          return true
        end
      end
    end
  end
  return false
end

-- Whether Herdr plays its own sounds, from its config.toml text: on unless turned off; nil when
-- the file could not be read.
function M.herdrSoundOn(text)
  if type(text) ~= "string" then
    return nil
  end
  return not soundOff(text)
end

-- Whether Herdr plays its own sounds for this socket, from its config.toml; nil when the file
-- cannot be read.
function M.readHerdrSound(socketPath)
  local path = M.herdrConfigPath(socketPath)
  local file = path and io.open(path, "r")
  if not file then
    return nil
  end
  local text = file:read("a")
  file:close()
  return M.herdrSoundOn(text)
end

-- The sound setting as Diagnostics shows it: { on, sounds, problem, herdr, config }; herdr (whether
-- Herdr plays its own sounds) is read only while HerdrJump plays some.
function M.status(sounds, problem, socketPath)
  local herdr
  if sounds then
    herdr = M.readHerdrSound(socketPath)
  end
  return { on = sounds ~= nil, sounds = sounds, problem = problem, herdr = herdr, config = M.herdrConfigPath(socketPath) }
end

-- A function that plays a sound by system name or file path ("~/" is the home folder), loading
-- each once; a sound that cannot be loaded is reported through warn once, then skipped.
function M.player(warn)
  local loaded, missing = {}, {}
  return function(name)
    local sound = loaded[name]
    if sound == nil and not missing[name] then
      if M.isFile(name) then
        sound = hs.sound.getByFile((name:gsub("^~/", (os.getenv("HOME") or "") .. "/")))
      else
        sound = hs.sound.getByName(name)
      end
      loaded[name] = sound
      if sound == nil then
        missing[name] = true
        warn("no such sound: " .. name)
      end
    end
    if sound then
      sound:stop()
      sound:play()
    end
  end
end

return M
