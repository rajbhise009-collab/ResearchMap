#!/usr/bin/env bash
#
# ResearchMap — double-click launcher for macOS Finder.
#
# What this does, in order:
#   1. Move into the repo (Finder launches .command scripts with your home
#      as $PWD; almost no failure path is more baffling than that).
#   2. Check the two things it needs — Node and Python 3 — and if either is
#      missing, say so in plain English with exactly where to get it. Never
#      a stack trace, never a mystery.
#   3. Install frontend dependencies if this is the first run.
#   4. Build the static site if it hasn't been built (or if source is newer
#      than the last build).
#   5. Pick a free port, start a static server bound to it, open the
#      browser at that URL.
#   6. Wait for the user to press a key; on any key, or on Ctrl-C, or on
#      Terminal being closed, shut the server down cleanly.
#
# Only bash, coreutils, python3, node/npm — no extra tooling required.

set -u
# Deliberately NOT set -e: this script's job is to keep going and explain,
# not to die silently on the first non-zero return code.

readonly SELF_DIR="$(cd "$(dirname "$0")" && pwd)"
readonly OUT_DIR="$SELF_DIR/frontend/out"
readonly BUILT_MARK="$OUT_DIR/index.html"
readonly LOG="$SELF_DIR/.launcher.log"

# ANSI codes only when stdout is a terminal — Terminal.app supports them,
# but redirecting to a file shouldn't fill it with escape sequences.
if [ -t 1 ]; then
  B=$'\033[1m'; DIM=$'\033[2m'; GREEN=$'\033[32m'; YELLOW=$'\033[33m'
  RED=$'\033[31m'; RESET=$'\033[0m'
else
  B=""; DIM=""; GREEN=""; YELLOW=""; RED=""; RESET=""
fi

say()   { printf "%s\n" "$*"; }
step()  { printf "\n${B}→${RESET} %s\n" "$*"; }
ok()    { printf "  ${GREEN}✓${RESET} %s\n" "$*"; }
warn()  { printf "  ${YELLOW}!${RESET} %s\n" "$*"; }
fail()  { printf "\n${RED}${B}Couldn't start.${RESET} %s\n\n" "$*"; }

pause_and_exit() {
  # If a fatal error hit, don't let Terminal close and swallow the message.
  local code="${1:-1}"
  printf "${DIM}Press return to close this window.${RESET} "
  read -r _ || true
  exit "$code"
}

banner() {
  printf "\n"
  printf "  ${B}ResearchMap${RESET}\n"
  printf "  ${DIM}Find research questions nobody has answered yet.${RESET}\n"
}

# ---------- prerequisite checks ----------

# Reproduce what Terminal.app finds on a fresh Mac: nvm's shims live in the
# user's login shell setup, so a plain non-interactive script may not see
# node without sourcing them.
load_node_from_common_locations() {
  if command -v node >/dev/null 2>&1; then return 0; fi
  # nvm
  if [ -s "$HOME/.nvm/nvm.sh" ]; then
    # shellcheck disable=SC1091
    export NVM_DIR="$HOME/.nvm"; . "$HOME/.nvm/nvm.sh" >/dev/null 2>&1 || true
  fi
  # Homebrew common locations
  for p in /opt/homebrew/bin /usr/local/bin; do
    [ -x "$p/node" ] && export PATH="$p:$PATH"
  done
}

check_prereqs() {
  step "Checking what's installed"

  if ! command -v python3 >/dev/null 2>&1; then
    fail "Python 3 isn't installed on this Mac."
    say "  ResearchMap needs Python 3. The quickest way is to open"
    say "  Terminal and run:"
    say ""
    say "    ${B}xcode-select --install${RESET}"
    say ""
    say "  macOS will offer to install the Command Line Tools, which"
    say "  includes Python 3. Once that finishes, try this launcher again."
    pause_and_exit 1
  fi
  ok "Python 3 ($(python3 --version 2>&1))"

  load_node_from_common_locations
  if ! command -v node >/dev/null 2>&1 || ! command -v npm >/dev/null 2>&1; then
    fail "Node.js isn't installed on this Mac."
    say "  ResearchMap needs Node.js (any version 18 or newer)."
    say "  Install it from ${B}https://nodejs.org${RESET} — pick the LTS"
    say "  build, run the .pkg installer, then try this launcher again."
    pause_and_exit 1
  fi
  ok "Node.js $(node --version 2>&1)"
}

# ---------- one-time frontend install ----------

install_frontend_deps() {
  if [ -d "$SELF_DIR/frontend/node_modules" ]; then return 0; fi
  step "First run: installing frontend dependencies (this happens once)"
  say "  ${DIM}Downloading ~180 MB of Node modules; usually 30-90 seconds…${RESET}"
  ( cd "$SELF_DIR/frontend" && npm install --silent --no-audit --no-fund ) \
    >>"$LOG" 2>&1
  if [ ! -d "$SELF_DIR/frontend/node_modules" ]; then
    fail "npm install didn't finish."
    say "  The full log is at:"
    say "    ${B}$LOG${RESET}"
    say ""
    say "  A common cause is being offline. Check your connection and try"
    say "  again; if it keeps failing, open Terminal, run:"
    say "    ${B}cd \"$SELF_DIR/frontend\" && npm install${RESET}"
    say "  and paste the error you see."
    pause_and_exit 1
  fi
  ok "Dependencies installed"
}

# ---------- build the static site if it's stale ----------

needs_build() {
  [ ! -f "$BUILT_MARK" ] && return 0
  # If any source file is newer than the built index, rebuild. This isn't
  # a perfect dependency graph — it's a "did the developer edit something
  # since last run" check, which is what a user of the launcher needs.
  local newer
  newer=$(find "$SELF_DIR/frontend/app" "$SELF_DIR/frontend/lib" \
                "$SELF_DIR/frontend/public/data" \
                -newer "$BUILT_MARK" -type f 2>/dev/null | head -1)
  [ -n "$newer" ] && return 0
  return 1
}

build_site() {
  if ! needs_build; then
    ok "Site is already built ($(ls "$OUT_DIR" 2>/dev/null | wc -l | tr -d ' ') files)"
    return 0
  fi
  step "Building the site"

  # 1. Snapshot from the reasoning cache (uses the repo's .venv if present,
  #    otherwise the system python3 — the export module has no exotic deps).
  local py="python3"
  if [ -x "$SELF_DIR/.venv/bin/python" ]; then
    py="$SELF_DIR/.venv/bin/python"
  fi
  ( cd "$SELF_DIR" && "$py" -m backend.app.api.export ) >>"$LOG" 2>&1
  if [ ! -f "$SELF_DIR/frontend/public/data/opportunities.json" ]; then
    fail "The data snapshot didn't get produced."
    say "  ResearchMap couldn't read its own reasoning output. The log is at:"
    say "    ${B}$LOG${RESET}"
    say "  If you've just cloned the repo, ${B}data/reasoning/${RESET} may"
    say "  be empty and needs to be regenerated first."
    pause_and_exit 1
  fi
  ok "Snapshot refreshed"

  # 2. Static build.
  say "  ${DIM}Compiling the frontend; usually 15-30 seconds…${RESET}"
  ( cd "$SELF_DIR/frontend" && npm run build --silent ) >>"$LOG" 2>&1
  if [ ! -f "$BUILT_MARK" ]; then
    fail "The frontend build didn't produce a site."
    say "  The build log is at:"
    say "    ${B}$LOG${RESET}"
    pause_and_exit 1
  fi
  ok "Site built ($(find "$OUT_DIR" -name '*.html' | wc -l | tr -d ' ') pages)"
}

# ---------- pick a port and serve ----------

pick_free_port() {
  python3 - <<'PY'
import socket
s = socket.socket(); s.bind(("127.0.0.1", 0))
print(s.getsockname()[1]); s.close()
PY
}

start_server() {
  step "Starting a local web server"
  PORT=$(pick_free_port 2>/dev/null || true)
  if [ -z "$PORT" ]; then
    fail "Couldn't find a free port to listen on."
    say "  This shouldn't normally happen. Restart your Mac and try again."
    pause_and_exit 1
  fi

  # Serve with a tiny custom handler that returns out/404.html for unknown
  # paths — Python's stock http.server hard-codes its own 404 body, which
  # is a jarring break out of the app's design. The rest of the behaviour
  # is identical to `python3 -m http.server`.
  python3 - "$OUT_DIR" "$PORT" >>"$LOG" 2>&1 <<'PY' &
import functools, http.server, os, socketserver, sys
root, port = sys.argv[1], int(sys.argv[2])
NF = os.path.join(root, "404.html")
class H(http.server.SimpleHTTPRequestHandler):
    def send_error(self, code, message=None, explain=None):
        if code == 404 and os.path.isfile(NF):
            with open(NF, "rb") as f: body = f.read()
            self.send_response(404)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        super().send_error(code, message, explain)
socketserver.TCPServer.allow_reuse_address = True
Handler = functools.partial(H, directory=root)
with socketserver.TCPServer(("127.0.0.1", port), Handler) as httpd:
    httpd.serve_forever()
PY
  SERVER_PID=$!

  # Give the server a moment to bind. Poll instead of a fixed sleep so we
  # don't add latency for no reason.
  local URL="http://127.0.0.1:$PORT/"
  for _ in 1 2 3 4 5 6 7 8 9 10; do
    if curl -s -o /dev/null "$URL"; then break; fi
    sleep 0.15
  done
  if ! kill -0 "$SERVER_PID" 2>/dev/null; then
    fail "The web server died right after starting."
    say "  The full log is at ${B}$LOG${RESET}. This is unusual — please"
    say "  paste that log if it keeps happening."
    pause_and_exit 1
  fi

  ok "Serving http://127.0.0.1:$PORT/"
  # Open in the default browser. `open` is macOS-native.
  open "$URL" 2>/dev/null || true

  printf "\n${GREEN}ResearchMap is open in your browser.${RESET}\n"
  printf "${DIM}Keep this window open while you use it.${RESET}\n\n"
  printf "  Press ${B}any key${RESET} in this window to stop the server and quit.\n\n"
}

shutdown() {
  # Idempotent — trap can fire twice on ^C during read.
  if [ -n "${SHUTDOWN_DONE:-}" ]; then return; fi
  SHUTDOWN_DONE=1
  printf "\n${DIM}Shutting down…${RESET}\n"
  if [ -n "${SERVER_PID:-}" ] && kill -0 "$SERVER_PID" 2>/dev/null; then
    kill "$SERVER_PID" 2>/dev/null || true
    # Give it a beat, then force if it hasn't gone.
    for _ in 1 2 3 4 5; do
      kill -0 "$SERVER_PID" 2>/dev/null || break
      sleep 0.1
    done
    kill -9 "$SERVER_PID" 2>/dev/null || true
    wait "$SERVER_PID" 2>/dev/null || true
  fi
  ok "Stopped."
}

# ---------- run ----------

trap shutdown EXIT INT TERM HUP

# Fresh log per run so users can see what just happened, not what happened
# three launches ago.
: > "$LOG"

banner
check_prereqs
install_frontend_deps
build_site
start_server

# Read a single character in raw mode so ANY key triggers shutdown, not
# just Enter. `-n 1` needs -r to keep escape sequences intact.
IFS= read -r -s -n 1 _ || true
# `trap shutdown EXIT` handles the cleanup path.
