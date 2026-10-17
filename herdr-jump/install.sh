#!/bin/sh
# Installs or updates HerdrJump, the Hammerspoon Spoon of herdr-jump, straight from GitHub.
#
#   curl -fsSL https://raw.githubusercontent.com/MrBogomips/herdr-tools/main/herdr-jump/install.sh | sh
#
# Safe to run again: the Spoon is replaced, init.lua is kept. See README.md.
#
# Everything runs from main(), called on the last line: the shell parses the whole script before it
# acts, so a download cut short does nothing, and the commands it runs do not inherit the rest of
# the script as their stdin (bash reads a piped script line by line; the hs command line runs what
# it finds on stdin).
set -eu

REPO="${HERDR_JUMP_REPO:-MrBogomips/herdr-tools}"
SPOONS="$HOME/.hammerspoon/Spoons"
SPOON="$SPOONS/HerdrJump.spoon"
INIT="$HOME/.hammerspoon/init.lua"

usage() {
  cat <<EOF
Usage: install.sh [--ref REF] [--force]

Installs or updates HerdrJump, the Hammerspoon Spoon of herdr-jump, from GitHub:
  - installs Hammerspoon with Homebrew when it is missing
  - copies HerdrJump.spoon into ~/.hammerspoon/Spoons, replacing the previous copy
  - creates ~/.hammerspoon/init.lua from init.example.lua, or appends the HerdrJump lines to yours
  - reloads Hammerspoon, or starts it

Options:
  --ref REF   branch or tag of $REPO to install (default: main)
  --force     replace a HerdrJump.spoon that is a symbolic link (a development checkout)
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

# init.lua: the example when there is none, the three HerdrJump lines when yours lacks them.
configure_init() { # example
  if [ ! -f "$INIT" ]; then
    cp "$1" "$INIT"
    say "created $INIT from init.example.lua"
  elif grep -q HerdrJump "$INIT"; then
    say "$INIT already loads HerdrJump, left as it is"
  else
    cat >> "$INIT" <<'EOF'

-- HerdrJump, added by install.sh
hs.loadSpoon("HerdrJump")
spoon.HerdrJump:bindHotkeys(spoon.HerdrJump.defaultHotkeys)
spoon.HerdrJump:start()
EOF
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
  else
    say "restarting Hammerspoon"
    killall Hammerspoon
    sleep 1
    open -a Hammerspoon
  fi
}

main() {
  ref=main
  force=0
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
  configure_init "$(dirname "$SRC")/init.example.lua"
  reload_hammerspoon

  say "done: ⌃⌥⌘I goes back to iTerm, ⌃⌥⌘A opens the agents picker"
  say "macOS asks for Accessibility when Hammerspoon first starts, and for Automation of iTerm2 on the first jump"
}

main "$@"
