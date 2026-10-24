-- Talks to the Herdr server through the `herdr` command line, which prints one JSON envelope
-- ({id, result} or {id, error}) on stdout and exits non-zero on errors.
--
-- Not hs.socket: connecting it to a Unix socket aborts Hammerspoon 1.1.1 (GCDAsyncSocket builds an
-- NSURL from the empty peer address and throws).
--
-- conn = { bin = path of the herdr binary, socket = Herdr server socket (HERDR_SOCKET_PATH) }.
-- The argument and reply helpers are pure; run() needs Hammerspoon.

local M = {}

local UNEXPECTED = "unexpected reply from Herdr"
-- Pane ids look like "wR:p1": letters, digits, "_" or "-" on both sides of the colon, never a
-- leading "-", which the command line would read as an option.
local PANE_ID = "^[%w_][%w_%-]*:[%w_%-]+$"
-- Error codes with a shorter message than Herdr's own.
local PLAIN = { server_not_running = "Herdr is not running" }

function M.listArgs()
  return { "agent", "list" }
end

function M.focusArgs(paneId)
  if type(paneId) ~= "string" or not paneId:match(PANE_ID) then
    return nil, "not a Herdr pane id: " .. tostring(paneId)
  end
  return { "agent", "focus", paneId }
end

local function text(value)
  return type(value) == "string" and value ~= "" and value or nil
end

-- The message of an error reply: {message, code}, either one alone, or plain text.
local function errorMessage(err)
  if type(err) == "string" then
    return text(err)
  end
  if type(err) ~= "table" then
    return nil
  end
  local message, code = text(err.message), text(err.code)
  if code and PLAIN[code] then
    return PLAIN[code]
  end
  if message and code then
    return ("%s (%s)"):format(message, code)
  end
  return message or (code and ("Herdr error (%s)"):format(code))
end

-- The result of a decoded reply, or nil and a message for the user.
function M.parse(reply)
  if type(reply) ~= "table" then
    return nil, UNEXPECTED
  end
  if reply.error ~= nil then
    return nil, errorMessage(reply.error) or UNEXPECTED
  end
  if type(reply.result) ~= "table" then
    return nil, UNEXPECTED
  end
  return reply.result
end

local function decodeTable(decode, output)
  if output == "" then
    return nil
  end
  local ok, value = pcall(decode, output)
  return ok and type(value) == "table" and value or nil
end

local function failed(exitCode)
  return ("herdr failed (exit %s)"):format(tostring(exitCode))
end

-- The outcome of a finished herdr run: the result, or nil, a message for the user and a detail
-- for the log. herdr prints results on stdout and error envelopes on stderr. decode is
-- hs.json.decode (injected so the tests run without Hammerspoon).
function M.reply(exitCode, stdout, stderr, decode)
  local out, errOut = tostring(stdout or ""), tostring(stderr or "")
  local detail = ("exit %s: %s"):format(tostring(exitCode), out:sub(1, 200))
  if errOut ~= "" then
    detail = detail .. " stderr: " .. errOut:sub(1, 200)
  end
  local reply = decodeTable(decode, out) or decodeTable(decode, errOut)
  if reply == nil then
    return nil, exitCode ~= 0 and failed(exitCode) or UNEXPECTED, detail
  end
  local result, err = M.parse(reply)
  if err then
    return nil, err, err == UNEXPECTED and detail or nil
  end
  if exitCode ~= 0 then
    return nil, failed(exitCode), detail
  end
  return result
end

local function optionalNumber(value)
  return value == nil or type(value) == "number"
end

-- An agent HerdrJump can rank and jump to: a well-formed pane id and numeric sequences.
local function wellFormed(agent)
  return type(agent) == "table"
    and type(agent.pane_id) == "string"
    and agent.pane_id:match(PANE_ID) ~= nil
    and optionalNumber(agent.completion_seq)
    and optionalNumber(agent.state_change_seq)
end

-- The agents of an agent_list result, without malformed entries; also returns how many were dropped.
function M.agents(result)
  if type(result) ~= "table" or result.type ~= "agent_list" then
    return nil, UNEXPECTED
  end
  if result.agents == nil then
    return {}, nil, 0
  end
  if type(result.agents) ~= "table" then
    return nil, UNEXPECTED
  end
  local agents, dropped = {}, 0
  for _, agent in ipairs(result.agents) do
    if wellFormed(agent) then
      agents[#agents + 1] = agent
    else
      dropped = dropped + 1
    end
  end
  return agents, nil, dropped
end

-- The task and timer of each running herdr call, by call number. This table is their only owner:
-- the callbacks capture the number, never the objects. Hammerspoon holds callbacks strongly until
-- the object is collected, so a callback that captured its own task or timer would keep it alive
-- forever, and a poll every few seconds would leak one of each per poll.
local inFlight = {}
local lastCall = 0

-- Runs `herdr <args>` and calls callback(result, err, detail) exactly once.
-- hs.task reads the output only after the process exits, so an output over the 64 KB pipe buffer
-- would block herdr until the timeout: about 95 agents at today's ~700 bytes each.
function M.run(conn, args, callback, timeoutSeconds)
  -- hs.task.new raises on a nil path instead of returning nil.
  if type(conn.bin) ~= "string" then
    callback(nil, "herdr not found", "no herdr binary: see Diagnostics")
    return
  end
  lastCall = lastCall + 1
  local id = lastCall
  local function finish(result, err, detail)
    local live = inFlight[id]
    if live == nil then
      return
    end
    inFlight[id] = nil
    live.timer:stop()
    callback(result, err, detail)
  end
  local task = hs.task.new(conn.bin, function(exitCode, stdout, stderr)
    finish(M.reply(exitCode, stdout, stderr, hs.json.decode))
  end, args)
  if task == nil then
    callback(nil, "cannot run " .. tostring(conn.bin), "hs.task.new failed")
    return
  end
  local environment = task:environment()
  environment.HERDR_SOCKET_PATH = conn.socket
  task:setEnvironment(environment)
  local timer = hs.timer.doAfter(timeoutSeconds or 3, function()
    local live = inFlight[id]
    if live then
      live.task:terminate()
    end
    finish(nil, "Herdr is not answering", "herdr " .. table.concat(args, " ") .. " timed out")
  end)
  inFlight[id] = { task = task, timer = timer }
  if not task:start() then
    finish(nil, "cannot run " .. tostring(conn.bin), "hs.task start failed")
  end
end

-- callback(agents, err, detail): detail is for the log (what went wrong, what was dropped).
function M.listAgents(conn, callback)
  M.run(conn, M.listArgs(), function(result, err, detail)
    if err then
      callback(nil, err, detail)
      return
    end
    local agents, invalid, dropped = M.agents(result)
    if invalid then
      callback(nil, invalid)
      return
    end
    callback(agents, nil, dropped > 0 and ("dropped %d malformed agent(s)"):format(dropped) or nil)
  end)
end

-- callback(err): nil on success.
function M.focus(conn, paneId, callback)
  local args, invalid = M.focusArgs(paneId)
  if not args then
    callback(invalid)
    return
  end
  M.run(conn, args, function(_, err)
    callback(err)
  end)
end

return M
