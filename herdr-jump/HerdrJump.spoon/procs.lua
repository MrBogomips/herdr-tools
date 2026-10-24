-- The process table of `ps -axo pid=,ppid=,tty=,command=`: which processes are Herdr clients, on
-- which terminal device, and the chain of parents from a client up to the app that started it.
-- Pure: init.lua runs ps.

local M = {}

local PROC = "^%s*(%d+)%s+(%d+)%s+(%S+)%s+(.-)%s*$"
local TTY = "^ttys%d+$"
local DEFAULT_SESSION = "default"
-- Options after which `herdr` runs a one-shot command or talks to another machine.
local NOT_A_LOCAL_CLIENT = {
  ["--remote"] = true, ["--machine"] = true, ["--version"] = true, ["-V"] = true, ["--help"] = true,
  ["-h"] = true, ["--default-config"] = true, ["--skill"] = true,
}
-- Options that take the next word as their value.
local WITH_VALUE = { ["--session"] = true, ["--remote-keybindings"] = true }
-- Parents climbed at most: a guard against a table that loops.
local MAX_ANCESTRY = 64

-- { list = {proc...}, byPid = {[pid] = proc} }, proc = { pid, ppid, tty (nil for "??"), command }.
function M.parse(ps)
  local list, byPid = {}, {}
  for line in (ps or ""):gmatch("[^\n]+") do
    local pid, ppid, tty, command = line:match(PROC)
    if pid then
      local proc = { pid = tonumber(pid), ppid = tonumber(ppid), tty = tty ~= "??" and tty or nil, command = command }
      list[#list + 1] = proc
      byPid[proc.pid] = proc
    end
  end
  return { list = list, byPid = byPid }
end

-- Whether a command line is a Herdr client of this Mac (`herdr`, with options, or
-- `herdr session attach <name>`), and the session it names, if any.
function M.client(command)
  local words = {}
  for word in (command or ""):gmatch("%S+") do
    words[#words + 1] = word
  end
  if words[1] == nil or words[1]:match("[^/]+$") ~= "herdr" then
    return false
  end
  local session
  local i = 2
  while words[i] and words[i]:sub(1, 1) == "-" do
    local option, value = words[i]:match("^(%-%-[^=]+)=(.*)$")
    option = option or words[i]
    if NOT_A_LOCAL_CLIENT[option] then
      return false
    end
    if WITH_VALUE[option] and value == nil then
      i = i + 1
      value = words[i]
    end
    if option == "--session" then
      session = value
    end
    i = i + 1
  end
  if words[i] == nil then
    return true, session
  end
  if words[i] == "session" and words[i + 1] == "attach" and words[i + 2] then
    return true, words[i + 2]
  end
  return false
end

-- The Herdr clients on a terminal, in ps order, as { pid, tty = "/dev/ttysNNN", session }: those of
-- `session` (nil for the default one), or all of them when none matches, since a client can pick
-- its session through HERDR_SESSION, which ps does not show.
function M.clients(parsed, session)
  local wanted = session or DEFAULT_SESSION
  local all, matching = {}, {}
  for _, proc in ipairs(parsed.list) do
    local isClient, named = M.client(proc.command)
    if isClient and proc.tty and proc.tty:match(TTY) then
      local client = { pid = proc.pid, tty = "/dev/" .. proc.tty, session = named }
      all[#all + 1] = client
      if (named or DEFAULT_SESSION) == wanted then
        matching[#matching + 1] = client
      end
    end
  end
  return #matching > 0 and matching or all
end

-- The terminal devices of the clients, each once, first seen first.
function M.ttys(clients)
  local ttys, listed = {}, {}
  for _, client in ipairs(clients) do
    if not listed[client.tty] then
      listed[client.tty] = true
      ttys[#ttys + 1] = client.tty
    end
  end
  return ttys
end

-- The parents of a process, nearest first, up to the one launchd (pid 1) started.
function M.ancestry(parsed, pid)
  local chain, visited = {}, {}
  local proc = parsed.byPid[pid]
  local parent = proc and parsed.byPid[proc.ppid]
  while parent and parent.pid > 1 and not visited[parent.pid] and #chain < MAX_ANCESTRY do
    visited[parent.pid] = true
    chain[#chain + 1] = parent
    parent = parsed.byPid[parent.ppid]
  end
  return chain
end

return M
