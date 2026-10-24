#!/bin/sh
# Installs or updates HerdrJump, the Hammerspoon Spoon of herdr-jump, straight from GitHub.
#
#   curl -fsSL https://raw.githubusercontent.com/MrBogomips/herdr-tools/main/herdr-jump/install.sh | sh
#   curl -fsSL https://raw.githubusercontent.com/MrBogomips/herdr-tools/main/herdr-jump/install.sh | sh -s -- --check
#
# Safe to run again: the Spoon is replaced, init.lua is kept. See README.md.
#
# Everything runs from main(), called on the last line: the shell parses the whole script before it
# acts, so a download cut short does nothing, and the commands it runs do not inherit the rest of
# the script as their stdin (bash reads a piped script line by line; the hs command line runs what
# it finds on stdin).
set -eu

REPO="${HERDR_JUMP_REPO:-MrBogomips/herdr-tools}"
# Hammerspoon's init.lua and the Spoons folder beside it; resolve_paths sets them.
INIT=""
SPOONS=""
SPOON=""
# Whether Hammerspoon's MJConfigFile setting moved init.lua away from ~/.hammerspoon.
MOVED=0
TERMINALS="iTerm Terminal Ghostty WezTerm kitty Alacritty Warp"
NL='
'

usage() {
  cat <<EOF
Usage: install.sh [--ref REF] [--force] [--check]

Installs or updates HerdrJump, the Hammerspoon Spoon of herdr-jump, from GitHub:
  - installs Hammerspoon with Homebrew when it is missing
  - copies HerdrJump.spoon into the Spoons folder of Hammerspoon's config (~/.hammerspoon unless
    its MJConfigFile setting says otherwise), replacing the previous copy
  - creates init.lua from init.example.lua, or appends the HerdrJump lines to yours, with the
    herdr and the Herdr socket this shell uses
  - reloads Hammerspoon, or starts it

Options:
  --ref REF   branch or tag of $REPO to install (default: main)
  --force     replace a HerdrJump.spoon that is a symbolic link (a development checkout)
  --check     only check what HerdrJump needs (Hammerspoon, herdr, the socket, a terminal), and
              change nothing
  --help      this text
EOF
}

say() {
  printf 'herdr-jump: %s\n' "$*"
}

fail() {
  printf 'herdr-jump: %s\n' "$*" >&2
  exit 1
}

# Hammerspoon reads init.lua from its MJConfigFile setting when there is one, and loads Spoons from
# the folder holding it.
resolve_paths() {
  config=$(defaults read org.hammerspoon.Hammerspoon MJConfigFile 2> /dev/null) || config=""
  # shellcheck disable=SC2088 # the setting holds a literal ~, as Hammerspoon's docs write it
  case "$config" in
    "~/"*) config="$HOME/${config#??}" ;;
  esac
  if [ -n "$config" ]; then
    MOVED=1
  fi
  INIT=${config:-$HOME/.hammerspoon/init.lua}
  SPOONS="$(dirname "$INIT")/Spoons"
  SPOON="$SPOONS/HerdrJump.spoon"
}

# Whether init.lua loads HerdrJump: an hs.loadSpoon("HerdrJump") before any -- on its line.
loads_herdrjump() {
  grep -Eq "^([^-]|-[^-])*hs\.loadSpoon[[:space:](]*[\"']HerdrJump[\"']" "$INIT"
}

# Hammerspoon, through Homebrew when it is missing. `open -Ra` only resolves the app: no window.
ensure_hammerspoon() {
  if open -Ra Hammerspoon > /dev/null 2>&1; then
    say "Hammerspoon is installed"
    return
  fi
  command -v brew > /dev/null 2>&1 \
    || fail "Hammerspoon is not installed and Homebrew is missing: install it from https://www.hammerspoon.org, then run this again"
  say "installing Hammerspoon with Homebrew"
  brew install --cask hammerspoon < /dev/null
}

# The Spoon and init.example.lua of the chosen ref, downloaded and unpacked under $1; sets SRC to
# the unpacked Spoon.
fetch_spoon() { # tmp, ref
  url="https://github.com/$REPO/archive/$2.tar.gz"
  say "downloading $url"
  curl -fsSL "$url" -o "$1/src.tar.gz" || fail "download failed: $url"
  mkdir "$1/src"
  tar -xzf "$1/src.tar.gz" -C "$1/src"
  SRC=$(find "$1/src" -type d -name HerdrJump.spoon -path '*/herdr-jump/*' | head -n 1)
  [ -n "$SRC" ] && [ -f "$SRC/init.lua" ] || fail "no herdr-jump/HerdrJump.spoon in $url"
  [ -f "$(dirname "$SRC")/init.example.lua" ] || fail "no herdr-jump/init.example.lua in $url"
}

# Replaces $SPOON with the unpacked Spoon $1.
install_spoon() {
  mkdir -p "$SPOONS"
  rm -rf "$SPOON.new"
  cp -R "$1" "$SPOON.new"
  rm -rf "$SPOON"
  mv "$SPOON.new" "$SPOON"
  say "installed $SPOON"
}

# The socket of the Herdr server this shell reaches, as herdr resolves it (HERDR_SOCKET_PATH,
# HERDR_SESSION, XDG_CONFIG_HOME); empty without herdr.
herdr_socket() {
  herdr status server < /dev/null 2> /dev/null | sed -n 's/^socket: //p' | head -n 1
}

# Whether a value can sit between double quotes in Lua as it is.
lua_safe() {
  case "$1" in
    *'"'* | *\\* | *"$NL"*) return 1 ;;
  esac
  return 0
}

# Lua lines pointing HerdrJump at the herdr of this shell and at its socket when it is not the
# default one, written to $1 (nothing without herdr on the PATH). Hammerspoon sees neither the
# shell's PATH nor its XDG_CONFIG_HOME.
write_settings() { # file
  : > "$1"
  bin=$(command -v herdr 2> /dev/null) || return 0
  socket=$(herdr_socket)
  lines=""
  if lua_safe "$bin"; then
    lines="spoon.HerdrJump.herdrBin = \"$bin\""
  else
    say "herdr is at $bin: set spoon.HerdrJump.herdrBin in init.lua by hand"
  fi
  if [ -n "$socket" ] && [ "$socket" != "$HOME/.config/herdr/herdr.sock" ]; then
    if lua_safe "$socket"; then
      lines="$lines${lines:+$NL}spoon.HerdrJump.socketPath = \"$socket\""
    else
      say "the Herdr socket is $socket: set spoon.HerdrJump.socketPath in init.lua by hand"
    fi
  fi
  if [ -n "$lines" ]; then
    printf -- '-- Found by install.sh in your shell: drop a line to let HerdrJump use its defaults.\n%s\n' "$lines" > "$1"
  fi
}

# init.lua: the example when there is none, the HerdrJump lines when yours lacks them; both with
# the settings of $2. An init.lua that loads HerdrJump already is not touched: a socket it lacks is
# printed instead.
configure_init() { # example, settings
  if [ ! -f "$INIT" ]; then
    mkdir -p "$(dirname "$INIT")"
    sed "/^hs\.loadSpoon(\"HerdrJump\")\$/r $2" "$1" > "$INIT"
    say "created $INIT from init.example.lua"
  elif loads_herdrjump; then
    say "$INIT already loads HerdrJump, left as it is"
    socket_line=$(grep '^spoon.HerdrJump.socketPath' "$2" || true)
    if [ -n "$socket_line" ] && ! grep -q socketPath "$INIT"; then
      say "your Herdr socket is not the default one: add this line before HerdrJump's start() in $INIT"
      say "  $socket_line"
    fi
  else
    {
      printf '\n-- HerdrJump, added by install.sh\nhs.loadSpoon("HerdrJump")\n'
      cat "$2"
      printf 'spoon.HerdrJump:bindHotkeys(spoon.HerdrJump.defaultHotkeys)\nspoon.HerdrJump:start()\n'
    } >> "$INIT"
    say "added HerdrJump to $INIT"
  fi
}

# Reloads a running Hammerspoon through its command line, restarts it without one, starts it
# when it is not running.
reload_hammerspoon() {
  if ! pgrep -xq Hammerspoon; then
    say "starting Hammerspoon"
    open -a Hammerspoon
    return
  fi
  if command -v hs > /dev/null 2>&1 && hs -c 'return 1' < /dev/null > /dev/null 2>&1; then
    # The command line loses its connection while Hammerspoon reloads and exits non-zero.
    hs -c 'hs.reload()' < /dev/null > /dev/null 2>&1 || true
    say "reloaded Hammerspoon"
    return
  fi
  say "restarting Hammerspoon"
  killall Hammerspoon || true
  # `open -a` on an instance still quitting does nothing: wait for it to go, 10 seconds at most.
  waited=0
  while pgrep -xq Hammerspoon && [ "$waited" -lt 10 ]; do
    sleep 1
    waited=$((waited + 1))
  done
  if pgrep -xq Hammerspoon; then
    say "Hammerspoon did not quit: quit it and open it again to load HerdrJump"
    return
  fi
  open -a Hammerspoon
}

# --- check ----------------------------------------------------------------------------------------

CHECK_FAILED=0

check_line() { # ok|warn|fail, text
  printf '%-5s %s\n' "$1" "$2"
  if [ "$1" = fail ]; then
    CHECK_FAILED=1
  fi
}

# A string field of a Spoon's init.lua, such as `obj.version = "0.4.0"`.
spoon_field() { # name, init.lua
  sed -n "s/^obj\\.$1 *= *\"\\([^\"]*\\)\".*/\\1/p" "$2" 2> /dev/null | head -n 1
}

# Whether version $1 is older than $2.
older_than() {
  awk -v a="$1" -v b="$2" 'BEGIN {
    split(a, x, "."); split(b, y, ".")
    for (i = 1; i <= 3; i++) { if (x[i] + 0 < y[i] + 0) exit 0; if (x[i] + 0 > y[i] + 0) exit 1 }
    exit 1
  }'
}

hammerspoon_version() {
  for app in /Applications/Hammerspoon.app "$HOME/Applications/Hammerspoon.app"; do
    defaults read "$app/Contents/Info" CFBundleShortVersionString 2> /dev/null && return
  done
  return 0
}

check_hammerspoon() {
  if ! open -Ra Hammerspoon > /dev/null 2>&1; then
    check_line fail "Hammerspoon is not installed: install.sh installs it with Homebrew, or get it from https://www.hammerspoon.org"
    return
  fi
  version=$(hammerspoon_version)
  check_line ok "Hammerspoon ${version:-is installed}"
  if pgrep -xq Hammerspoon; then
    check_line ok "Hammerspoon is running"
  else
    check_line warn "Hammerspoon is not running: open it, or run install.sh"
  fi
}

check_config() {
  if [ "$MOVED" = 1 ]; then
    check_line ok "Hammerspoon reads $INIT (its MJConfigFile setting)"
  fi
  if [ ! -f "$INIT" ]; then
    check_line warn "no $INIT yet: install.sh creates it"
  elif loads_herdrjump; then
    check_line ok "$INIT loads HerdrJump"
  else
    check_line warn "$INIT does not load HerdrJump: install.sh adds it"
  fi
  if [ -f "$SPOON/init.lua" ]; then
    link=""
    if [ -L "$SPOON" ]; then
      link=" (a symbolic link)"
    fi
    check_line ok "HerdrJump $(spoon_field version "$SPOON/init.lua") in $SPOON$link"
  else
    check_line warn "HerdrJump is not in $SPOONS: install.sh puts it there"
  fi
}

check_herdr() {
  if ! bin=$(command -v herdr 2> /dev/null); then
    check_line fail "herdr is not on your PATH: install it from https://herdr.dev"
    return
  fi
  version=$(herdr --version < /dev/null 2> /dev/null | sed -n 's/^herdr \([0-9][0-9.]*\).*/\1/p' | head -n 1)
  minimum=$(spoon_field minHerdrVersion "$SPOON/init.lua")
  if [ -n "$version" ] && [ -n "$minimum" ] && older_than "$version" "$minimum"; then
    check_line warn "herdr $version at $bin is older than $minimum, the oldest HerdrJump is verified with"
  else
    check_line ok "herdr ${version:-?} at $bin"
  fi
  socket=$(herdr_socket)
  if [ -n "$socket" ] && [ -S "$socket" ]; then
    check_line ok "the Herdr server listens on $socket"
  else
    check_line warn "no Herdr server on ${socket:-its socket}: start herdr"
  fi
}

check_terminals() {
  found=""
  for app in $TERMINALS; do
    if open -Ra "$app" > /dev/null 2>&1; then
      found="$found, $app"
    fi
  done
  if [ -z "$found" ]; then
    check_line warn "none of $TERMINALS is installed: a jump brings your terminal forward as an app"
    return
  fi
  check_line ok "terminals: ${found#, } (a jump selects the Herdr tab in iTerm and Terminal, brings the others forward)"
}

# What the running Spoon finds itself: the terminal of the Herdr client above all.
check_spoon() {
  if pgrep -xq Hammerspoon && command -v hs > /dev/null 2>&1 && hs -c 'return 1' < /dev/null > /dev/null 2>&1; then
    say "what the running HerdrJump finds:"
    hs -c 'return spoon.HerdrJump and spoon.HerdrJump:diagnostics() or "HerdrJump is not loaded"' < /dev/null 2>&1 \
      | sed 's/^/      /'
  else
    check_line warn "no hs command line to ask HerdrJump: see Diagnostics in its menu bar menu"
  fi
}

# Reports what HerdrJump needs, changes nothing, and fails when something blocks it.
check() {
  check_line ok "macOS $(sw_vers -productVersion 2> /dev/null || echo)"
  check_hammerspoon
  check_config
  check_herdr
  check_terminals
  check_spoon
  [ "$CHECK_FAILED" = 0 ]
}

main() {
  ref=main
  force=0
  only_check=0
  while [ $# -gt 0 ]; do
    case "$1" in
      --ref)
        [ $# -ge 2 ] || fail "--ref needs a branch or tag (try --help)"
        ref=$2
        shift 2
        ;;
      --ref=*)
        ref=${1#--ref=}
        shift
        ;;
      --force)
        force=1
        shift
        ;;
      --check)
        only_check=1
        shift
        ;;
      -h | --help)
        usage
        exit 0
        ;;
      *)
        fail "unknown option '$1' (try --help)"
        ;;
    esac
  done

  [ "$(uname -s)" = Darwin ] || fail "HerdrJump runs in Hammerspoon, on macOS only"
  resolve_paths
  if [ "$only_check" = 1 ]; then
    if check; then
      exit 0
    fi
    exit 1
  fi
  command -v curl > /dev/null 2>&1 || fail "curl is required"
  command -v tar > /dev/null 2>&1 || fail "tar is required"
  if [ -L "$SPOON" ] && [ "$force" = 0 ]; then
    fail "$SPOON is a symbolic link (a development checkout?): remove it, or pass --force to replace it"
  fi

  ensure_hammerspoon

  tmp=$(mktemp -d "${TMPDIR:-/tmp}/herdr-jump.XXXXXX")
  trap 'rm -rf "$tmp"' EXIT
  fetch_spoon "$tmp" "$ref"
  install_spoon "$SRC"
  write_settings "$tmp/settings.lua"
  configure_init "$(dirname "$SRC")/init.example.lua" "$tmp/settings.lua"
  reload_hammerspoon

  say "done: ⌃⌥⌘I goes back to your terminal, ⌃⌥⌘A opens the agents picker"
  say "macOS asks for Accessibility when Hammerspoon first starts, and for Automation of iTerm2 or Terminal on the first jump"
  say "install.sh --check, or Diagnostics in HerdrJump's menu, shows what it found"
}

main "$@"
