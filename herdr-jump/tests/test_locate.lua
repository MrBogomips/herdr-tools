local h = ...
local locate = h.load("locate")

local HOME = "/Users/acme"

local function files(list)
  local set = {}
  for _, path in ipairs(list) do
    set[path] = true
  end
  return function(path) return set[path] == true end
end

return {
  candidates_cover_homebrew_the_installer_cargo_nix_macports_and_mise = function()
    h.eq(locate.herdrCandidates(HOME, "acme"), {
      "/opt/homebrew/bin/herdr",
      "/usr/local/bin/herdr",
      "/Users/acme/.local/bin/herdr",
      "/Users/acme/.cargo/bin/herdr",
      "/etc/profiles/per-user/acme/bin/herdr",
      "/run/current-system/sw/bin/herdr",
      "/Users/acme/.nix-profile/bin/herdr",
      "/opt/local/bin/herdr",
      "/Users/acme/.local/share/mise/shims/herdr",
    })
  end,

  candidates_skip_what_needs_an_unknown_home_or_user = function()
    h.eq(locate.herdrCandidates(nil, nil), {
      "/opt/homebrew/bin/herdr",
      "/usr/local/bin/herdr",
      "/run/current-system/sw/bin/herdr",
      "/opt/local/bin/herdr",
    })
  end,

  the_setting_wins_when_it_is_there = function()
    local isFile = files({ "/opt/homebrew/bin/herdr", "/srv/herdr" })
    h.eq({ locate.herdr("/srv/herdr", locate.herdrCandidates(HOME, "acme"), isFile) }, { "/srv/herdr", "setting", {} })
  end,

  the_first_candidate_on_disk_is_found = function()
    local candidates = locate.herdrCandidates(HOME, "acme")
    h.eq({ locate.herdr(nil, candidates, files({ "/Users/acme/.local/bin/herdr", "/opt/local/bin/herdr" })) },
      { "/Users/acme/.local/bin/herdr", "found", {} })
  end,

  a_missing_setting_falls_back_to_the_candidates = function()
    local candidates = locate.herdrCandidates(HOME, "acme")
    h.eq({ locate.herdr("/old/herdr", candidates, files({ "/usr/local/bin/herdr" })) },
      { "/usr/local/bin/herdr", "found", { "/old/herdr" } })
  end,

  nothing_found_lists_every_place_tried = function()
    local candidates = { "/opt/homebrew/bin/herdr", "/usr/local/bin/herdr" }
    h.eq({ locate.herdr("/old/herdr", candidates, files({})) },
      { nil, nil, { "/old/herdr", "/opt/homebrew/bin/herdr", "/usr/local/bin/herdr" } })
  end,

  session_of_a_socket = function()
    h.eq(locate.sessionOf("/Users/acme/.config/herdr/sessions/globex/herdr.sock"), "globex")
    h.eq(locate.sessionOf("/Users/acme/.config/herdr/herdr.sock"), nil)
    h.eq(locate.sessionOf(nil), nil)
  end,

  version_comparison = function()
    h.eq(locate.older("0.9.3", "0.9.5"), true)
    h.eq(locate.older("0.9.5", "0.9.5"), false)
    h.eq(locate.older("0.10.0", "0.9.5"), false)
    h.eq(locate.older("1.0", "0.9.5"), false)
    h.eq(locate.older("nonsense", "0.9.5"), nil)
  end,

  version_from_the_command_line = function()
    h.eq(locate.version("herdr 0.9.5\n"), "0.9.5")
    h.eq(locate.version("herdr 0.10.0-preview.3"), "0.10.0")
    h.eq(locate.version(""), nil)
    h.eq(locate.version(nil), nil)
  end,
}
