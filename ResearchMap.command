#!/usr/bin/env bash
#
# ResearchMap — double-click launcher for macOS Finder.
#
# Everything happens in this window: prereq check → install if first run
# → refresh snapshot → static build → start server → open browser.
# Press any key to stop the server and quit.
#
# The install/build/serve logic lives in scripts/rm-lib.sh so the .app
# bundle can reuse it — this file is just the terminal UI wrapping it.

set -u

readonly SELF_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO="$SELF_DIR"
export REPO

# ANSI codes when stdout is a terminal — nothing when redirected.
if [ -t 1 ]; then
  B=$'\033[1m'; DIM=$'\033[2m'; GREEN=$'\033[32m'; RED=$'\033[31m'; RESET=$'\033[0m'
else
  B=""; DIM=""; GREEN=""; RED=""; RESET=""
fi

banner() {
  printf "\n"
  printf "  ${B}ResearchMap${RESET}\n"
  printf "  ${DIM}Find research questions nobody has answered yet.${RESET}\n"
}

# UI contract for rm-lib.sh
ui_step()  { printf "\n${B}→${RESET} %s\n" "$*"; }
ui_ok()    { printf "  ${GREEN}✓${RESET} %s\n" "$*"; }
ui_note()  { printf "  ${DIM}%s${RESET}\n" "$*"; }
ui_fail()  {
  local title="$1"; local body="${2:-}"
  printf "\n${RED}${B}Couldn't start.${RESET} %s\n\n" "$title"
  [ -n "$body" ] && printf "%s\n\n" "$body"
  printf "${DIM}Press return to close this window.${RESET} "
  read -r _ || true
  exit 1
}

# shellcheck disable=SC1091
. "$SELF_DIR/scripts/rm-lib.sh"

# Fresh log per run so users see this run, not three ago.
: > "$RM_LOG"

trap 'rm_shutdown; printf "  ${GREEN}✓${RESET} Stopped.\n"' EXIT INT TERM HUP

banner
rm_check_prereqs
rm_install_frontend_deps
rm_build_site
rm_start_server

printf "\n${GREEN}ResearchMap is open in your browser.${RESET}\n"
printf "${DIM}Keep this window open while you use it.${RESET}\n\n"
printf "  Press ${B}any key${RESET} in this window to stop the server and quit.\n\n"

# Any key triggers shutdown, not just Enter.
IFS= read -r -s -n 1 _ || true
