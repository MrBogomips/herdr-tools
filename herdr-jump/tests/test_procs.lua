local h = ...
local procs = h.load("procs")

-- Output of `ps -axo pid=,ppid=,tty=,command=` as macOS prints it: Herdr clients in iTerm2, in
-- Terminal, under an iTerm2 server left behind by a restart, and in tmux; then one-shot commands.
local PS = table.concat({
  "    1     0 ??       /sbin/launchd",
  "  500     1 ??       /Applications/iTerm.app/Contents/MacOS/iTerm2",
  "  510   500 ??       /Users/acme/Library/Application Support/iTerm2/iTermServer-3.7.6 /Users/acme/Library/Application Support/iTerm2/iterm2-daemon-1.socket",
  "  520   510 ttys005  /usr/bin/login -fpl acme /Applications/iTerm.app/Contents/MacOS/ShellLauncher --launch_shell",
  "  530   520 ttys005  -zsh",
  "  540   530 ttys005  /opt/homebrew/bin/herdr",
  "  600     1 ??       /System/Applications/Utilities/Terminal.app/Contents/MacOS/Terminal",
  "  610   600 ttys007  login -pf acme",
  "  620   610 ttys007  -zsh",
  "  630   620 ttys007  /Users/acme/.local/bin/herdr session attach globex",
  "  700     1 ??       /Users/acme/Library/Application Support/iTerm2/iTermServer-3.7.6 /Users/acme/x.socket",
  "  710   700 ttys009  /usr/bin/login -fpl acme /Applications/iTerm.app/Contents/MacOS/ShellLauncher",
  "  720   710 ttys009  -zsh",
  "  730   720 ttys009  herdr --session lumon",
  "  800     1 ??       tmux new -s acme",
  "  810   800 ttys011  -zsh",
  "  820   810 ttys011  herdr",
  "  900   530 ttys005  herdr agent list",
  "  910   530 ttys005  herdr --remote build-box",
  "  920   530 ttys005  herdr --machine lumon agent list",
  "  930   530 ttys005  herdr --version",
  "  940   530 ttys005  herdrx",
  "  950     1 ??       /opt/homebrew/bin/herdr server",
  "  960   530 ttys005  herdr --session=acme --handoff",
  "not a process line",
  "",
}, "\n")

local function pids(list)
  local out = {}
  for i, proc in ipairs(list) do
    out[i] = proc.pid
  end
  return out
end

return {
  parse_reads_pid_parent_tty_and_the_whole_command = function()
    local parsed = procs.parse(PS)
    h.eq(parsed.byPid[510].command,
      "/Users/acme/Library/Application Support/iTerm2/iTermServer-3.7.6 /Users/acme/Library/Application Support/iTerm2/iterm2-daemon-1.socket")
    h.eq(parsed.byPid[540], { pid = 540, ppid = 530, tty = "ttys005", command = "/opt/homebrew/bin/herdr" })
    h.eq(parsed.byPid[500].tty, nil)
  end,

  parse_skips_lines_that_are_not_processes = function()
    h.eq(#procs.parse(PS).list, 24)
    h.eq(#procs.parse(nil).list, 0)
  end,

  client_is_herdr_alone_with_options_or_attaching_a_session = function()
    h.eq({ procs.client("/opt/homebrew/bin/herdr") }, { true })
    h.eq({ procs.client("herdr --session acme") }, { true, "acme" })
    h.eq({ procs.client("herdr --session=acme --handoff") }, { true, "acme" })
    h.eq({ procs.client("herdr session attach globex") }, { true, "globex" })
  end,

  client_is_not_the_server_a_one_shot_command_or_another_machine = function()
    for _, command in ipairs({
      "herdr server", "herdr agent list", "herdr --remote build-box", "herdr --remote=build-box",
      "herdr --machine lumon agent list", "herdr --version", "herdr -V", "herdr --default-config",
      "herdr session attach", "herdrx", "-zsh", "",
    }) do
      h.eq(procs.client(command), false, command)
    end
  end,

  clients_of_the_default_session_in_ps_order = function()
    local clients = procs.clients(procs.parse(PS), nil)
    h.eq(pids(clients), { 540, 820 })
    h.eq(clients[1].tty, "/dev/ttys005")
  end,

  clients_of_a_named_session = function()
    h.eq(pids(procs.clients(procs.parse(PS), "globex")), { 630 })
    h.eq(pids(procs.clients(procs.parse(PS), "default")), { 540, 820 })
  end,

  clients_of_an_unseen_session_are_all_of_them = function()
    -- A client can pick its session through HERDR_SESSION, which ps does not show.
    h.eq(pids(procs.clients(procs.parse(PS), "initech")), { 540, 630, 730, 820, 960 })
  end,

  ttys_lists_each_terminal_once = function()
    local clients = procs.clients(procs.parse(PS), "initech")
    h.eq(procs.ttys(clients), { "/dev/ttys005", "/dev/ttys007", "/dev/ttys009", "/dev/ttys011" })
  end,

  ancestry_climbs_to_the_last_process_before_launchd = function()
    h.eq(pids(procs.ancestry(procs.parse(PS), 540)), { 530, 520, 510, 500 })
    h.eq(pids(procs.ancestry(procs.parse(PS), 820)), { 810, 800 })
  end,

  ancestry_stops_at_a_loop_or_a_missing_parent = function()
    local looped = procs.parse("10 11 ?? a\n11 10 ?? b\n12 10 ttys001 herdr\n")
    h.eq(pids(procs.ancestry(looped, 12)), { 10, 11 })
    h.eq(pids(procs.ancestry(procs.parse("12 99 ttys001 herdr\n"), 12)), {})
    h.eq(pids(procs.ancestry(procs.parse(PS), 4242)), {})
  end,
}
