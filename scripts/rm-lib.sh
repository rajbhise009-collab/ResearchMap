#!/usr/bin/env bash
# ResearchMap launcher — shared shell library.
#
# This file is sourced by BOTH launchers — ResearchMap.command (double-
# clickable Terminal launcher) and ResearchMap.app (Finder-native bundle).
# It holds every side-effecting operation they share: prereq checks, npm
# install, static build, port picking, server lifecycle. Zero UI happens
# here — each caller supplies its own `ui_*` functions before sourcing.
#
# Required by the caller before sourcing:
#   REPO         absolute path to the repo root
#   ui_step "…"  a phase begins ("Starting a local web server")
#   ui_ok   "…"  a phase succeeded ("Site built (199 pages)")
#   ui_note "…"  informational aside (dim/subdued, non-fatal)
#   ui_fail "title" "body"   fatal error; MUST exit or return non-zero
#
# Sets, when done:
#   PORT         port the local server bound to
#   SERVER_PID   pid of the http.server process
#
# Everything sh(1)-portable: bash, python3, node/npm — no extra tooling.

# -- config ---------------------------------------------------------------
: "${REPO:?REPO must be set before sourcing rm-lib.sh}"
readonly RM_OUT_DIR="$REPO/frontend/out"
readonly RM_BUILT_MARK="$RM_OUT_DIR/index.html"
readonly RM_LOG="${RM_LOG:-$REPO/.launcher.log}"

# -- Node discovery -------------------------------------------------------
# On a fresh Mac the shell that launches us is often non-interactive, so
# nvm's shims aren't on PATH. Reproduce what an interactive login shell
# would give us.
rm_load_node_from_common_locations() {
  if command -v node >/dev/null 2>&1; then return 0; fi
  if [ -s "$HOME/.nvm/nvm.sh" ]; then
    # shellcheck disable=SC1091
    export NVM_DIR="$HOME/.nvm"; . "$HOME/.nvm/nvm.sh" >/dev/null 2>&1 || true
  fi
  for p in /opt/homebrew/bin /usr/local/bin; do
    [ -x "$p/node" ] && export PATH="$p:$PATH"
  done
}

# -- prereq checks --------------------------------------------------------
rm_check_prereqs() {
  ui_step "Checking what's installed"

  if ! command -v python3 >/dev/null 2>&1; then
    ui_fail "Python 3 isn't installed on this Mac." \
"ResearchMap needs Python 3. Open Terminal and run:

    xcode-select --install

macOS will offer to install the Command Line Tools, which includes Python 3.
Once that finishes, try this launcher again."
    return 1
  fi
  ui_ok "Python 3 ($(python3 --version 2>&1))"

  rm_load_node_from_common_locations
  if ! command -v node >/dev/null 2>&1 || ! command -v npm >/dev/null 2>&1; then
    ui_fail "Node.js isn't installed on this Mac." \
"ResearchMap needs Node.js (any version 18 or newer).

Install it from https://nodejs.org — pick the LTS build, run the .pkg
installer, then try this launcher again."
    return 1
  fi
  ui_ok "Node.js $(node --version 2>&1)"
  return 0
}

# -- one-time frontend install -------------------------------------------
rm_install_frontend_deps() {
  if [ -d "$REPO/frontend/node_modules" ]; then return 0; fi
  ui_step "First run: installing frontend dependencies (once)"
  ui_note "Downloading ~180 MB of Node modules; usually 30-90 seconds."
  ( cd "$REPO/frontend" && npm install --silent --no-audit --no-fund ) \
    >>"$RM_LOG" 2>&1
  if [ ! -d "$REPO/frontend/node_modules" ]; then
    ui_fail "npm install didn't finish." \
"The full log is at:
    $RM_LOG

A common cause is being offline. Check your connection and try again;
if it keeps failing, open Terminal and run:
    cd \"$REPO/frontend\" && npm install
so you can see the exact error npm reports."
    return 1
  fi
  ui_ok "Dependencies installed"
  return 0
}

# -- build if stale -------------------------------------------------------
rm_needs_build() {
  [ ! -f "$RM_BUILT_MARK" ] && return 0
  # "Did the developer edit something since last run" — mtime-based, not a
  # perfect graph, but the right check for a launcher.
  local newer
  newer=$(find "$REPO/frontend/app" "$REPO/frontend/lib" \
                "$REPO/frontend/public/data" \
                -newer "$RM_BUILT_MARK" -type f 2>/dev/null | head -1)
  [ -n "$newer" ] && return 0
  return 1
}

rm_build_site() {
  if ! rm_needs_build; then
    ui_ok "Site is already built ($(find "$RM_OUT_DIR" -name '*.html' | wc -l | tr -d ' ') pages)"
    return 0
  fi
  ui_step "Building the site"

  local py="python3"
  [ -x "$REPO/.venv/bin/python" ] && py="$REPO/.venv/bin/python"
  ( cd "$REPO" && "$py" -m backend.app.api.export ) >>"$RM_LOG" 2>&1
  if [ ! -f "$REPO/frontend/public/data/opportunities.json" ]; then
    ui_fail "Couldn't snapshot the reasoning output." \
"ResearchMap couldn't read its own reasoning output. The log is at:
    $RM_LOG

If you've just cloned the repo, data/reasoning/ may be empty and needs
to be regenerated first."
    return 1
  fi
  ui_ok "Snapshot refreshed"

  ui_note "Compiling the frontend; usually 15-30 seconds."
  ( cd "$REPO/frontend" && npm run build --silent ) >>"$RM_LOG" 2>&1
  if [ ! -f "$RM_BUILT_MARK" ]; then
    ui_fail "The frontend build didn't produce a site." \
"The build log is at:
    $RM_LOG"
    return 1
  fi
  ui_ok "Site built ($(find "$RM_OUT_DIR" -name '*.html' | wc -l | tr -d ' ') pages)"
  return 0
}

# -- port + server --------------------------------------------------------
rm_pick_free_port() {
  python3 - <<'PY'
import socket
s = socket.socket(); s.bind(("127.0.0.1", 0))
print(s.getsockname()[1]); s.close()
PY
}

# Serves out/ with a custom 404 handler so users never see Python's stock
# "Error response" body — they see our on-brand 404.html instead.
#
# Implementation note: the server program is written to a tempfile before
# launch. A `python3 - <<PY … PY &` heredoc into a backgrounded process
# is fragile inside a sourced library (the parent's file descriptor state
# leaks in strange ways). A separate tempfile is straightforward and
# self-contained; macOS clears /tmp on boot, so nothing to garbage-collect.
rm_start_server() {
  ui_step "Starting a local web server"
  PORT=$(rm_pick_free_port 2>/dev/null || true)
  if [ -z "$PORT" ]; then
    ui_fail "Couldn't find a free port to listen on." \
"This shouldn't normally happen. Try restarting your Mac and running this
launcher again."
    return 1
  fi

  local server_py
  server_py="$(mktemp -t rm-server.XXXXXX.py)"
  cat > "$server_py" <<'PY'
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
  python3 "$server_py" "$RM_OUT_DIR" "$PORT" >>"$RM_LOG" 2>&1 &
  SERVER_PID=$!
  # The tempfile stays for the server's lifetime — small, self-contained,
  # and macOS clears /tmp on boot.

  # Poll for readiness rather than sleeping a fixed interval.
  local URL="http://127.0.0.1:$PORT/"
  local i
  for i in 1 2 3 4 5 6 7 8 9 10; do
    if curl -s -o /dev/null "$URL"; then break; fi
    sleep 0.15
  done
  if ! kill -0 "$SERVER_PID" 2>/dev/null; then
    ui_fail "The web server died right after starting." \
"The full log is at $RM_LOG.
This is unusual — please paste that log if it keeps happening."
    return 1
  fi

  ui_ok "Serving $URL"
  open "$URL" 2>/dev/null || true
  return 0
}

# -- lifecycle ------------------------------------------------------------
rm_shutdown() {
  # Idempotent — trap can fire twice (e.g. ^C during a read).
  if [ -n "${RM_SHUTDOWN_DONE:-}" ]; then return; fi
  RM_SHUTDOWN_DONE=1
  if [ -n "${SERVER_PID:-}" ] && kill -0 "$SERVER_PID" 2>/dev/null; then
    kill "$SERVER_PID" 2>/dev/null || true
    local i
    for i in 1 2 3 4 5; do
      kill -0 "$SERVER_PID" 2>/dev/null || break
      sleep 0.1
    done
    kill -9 "$SERVER_PID" 2>/dev/null || true
    wait "$SERVER_PID" 2>/dev/null || true
  fi
}
