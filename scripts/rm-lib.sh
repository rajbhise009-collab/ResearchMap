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
# Callers may have already exported RM_LOG (the .app writes to
# ~/Library/Logs; the .command writes to the repo). Assign only if unset,
# and don't mark readonly so re-sourcing this lib is harmless.
: "${RM_LOG:=$REPO/.launcher.log}"
export RM_LOG

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

# -- Python venv for the FastAPI stack ------------------------------------
# The launcher used to serve static files with `python3 -m http.server`,
# which needs no Python packages at all. Now the "genuine app" path serves
# both the frontend AND live /api/* endpoints from one uvicorn process, so
# we need a small Python env with fastapi + uvicorn + pydantic + numpy.
#
# On first run, create .venv with just those four packages (~30 MB). If a
# venv already exists (e.g. developer already installed all of
# requirements.txt), we leave it alone.
rm_ensure_python_env() {
  local venv="$REPO/.venv"
  local uv="$venv/bin/uvicorn"
  if [ -x "$uv" ]; then return 0; fi

  ui_step "First run: setting up the Python backend (once)"
  ui_note "Installing fastapi + uvicorn + pydantic + numpy (~30 MB)."
  if [ ! -d "$venv" ]; then
    ( cd "$REPO" && python3 -m venv .venv ) >>"$RM_LOG" 2>&1
  fi
  if [ ! -x "$venv/bin/pip" ]; then
    ui_fail "Couldn't create a Python virtual environment." \
"macOS ships with python3 (via Xcode Command Line Tools), but the 'venv'
module didn't produce a working install. The full log is at:
    $RM_LOG

Try running 'xcode-select --install' in Terminal and launching again."
    return 1
  fi
  "$venv/bin/pip" install --quiet --upgrade pip >>"$RM_LOG" 2>&1
  "$venv/bin/pip" install --quiet \
      "fastapi>=0.100" "uvicorn>=0.20" "pydantic>=2" "numpy>=1.26" \
      >>"$RM_LOG" 2>&1
  if [ ! -x "$uv" ]; then
    ui_fail "Couldn't install the Python backend." \
"The full log is at:
    $RM_LOG

A common cause is being offline. Try again with a network connection."
    return 1
  fi
  ui_ok "Backend installed"
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
  # ENABLE_DEV=1 turns on ?dev=1 in the local build only. Public deploys
  # (Vercel, GitHub Pages workflow) don't set this, so their bundle can't
  # activate dev mode from the URL.
  ( cd "$REPO/frontend" && ENABLE_DEV=1 npm run build --silent ) >>"$RM_LOG" 2>&1
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

# Start the local web server.
#
# Two backends, one interface:
#   - uvicorn (when the Python env exists) serves the FastAPI app, which
#     itself mounts frontend/out/ at / — one process, /api/* and / from
#     the same origin. This is the "complete application" path.
#   - python3 -m http.server (fallback, static-only) — serves the built
#     frontend but exposes no live /api endpoints. Used when the Python
#     backend can't be installed.
#
# Sets SERVER_PID and URL for the caller.
rm_start_server() {
  ui_step "Starting a local web server"
  PORT=$(rm_pick_free_port 2>/dev/null || true)
  if [ -z "$PORT" ]; then
    ui_fail "Couldn't find a free port to listen on." \
"This shouldn't normally happen. Try restarting your Mac and running this
launcher again."
    return 1
  fi

  URL="http://127.0.0.1:$PORT/"
  local uv="$REPO/.venv/bin/uvicorn"

  if [ -x "$uv" ]; then
    # Full-stack: uvicorn serves frontend + /api/*.
    # `exec` inside the subshell REPLACES the subshell with uvicorn, so
    # $! becomes uvicorn's own PID — not a wrapper subshell whose child
    # keeps running after we kill the wrapper.
    ( cd "$REPO" && exec "$uv" backend.app.api.app:app \
        --host 127.0.0.1 --port "$PORT" --log-level warning \
        >>"$RM_LOG" 2>&1 ) &
    SERVER_PID=$!
    SERVER_KIND="uvicorn"
  else
    # Fallback: static-only via the stdlib http.server with our on-brand
    # 404 handler. Fires when rm_ensure_python_env couldn't run (e.g.
    # offline first launch). The URL still works and shows the site;
    # only the /api/* endpoints are absent.
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
    SERVER_KIND="static"
  fi

  # Poll for readiness rather than sleeping a fixed interval. uvicorn
  # takes ~1s to bind on a cold start; http.server is instant.
  local i
  for i in $(seq 1 40); do
    if curl -s -o /dev/null "$URL"; then break; fi
    sleep 0.15
  done
  if ! kill -0 "$SERVER_PID" 2>/dev/null; then
    ui_fail "The web server died right after starting." \
"The full log is at $RM_LOG.
This is unusual — please paste that log if it keeps happening."
    return 1
  fi

  case "$SERVER_KIND" in
    uvicorn) ui_ok "Serving $URL  (full stack — /api endpoints included)" ;;
    static)  ui_ok "Serving $URL  (frontend only — /api endpoints unavailable)" ;;
  esac
  return 0
}

# -- opening the app window ---------------------------------------------
# Two modes, one interface:
#   window  — Chrome's --app=URL: chromeless standalone window with its
#             own Dock icon and favicon in the title bar. Feels like a
#             native app. Falls back to a normal browser tab if Chrome
#             isn't installed.
#   browser — default browser tab (the launcher's classic behaviour).
#
# Sets APP_WINDOW_PID when a Chrome app window was launched (so callers
# that care about window lifecycle can wait on it).
rm_open() {
  local mode="${1:-browser}"
  local url="${2:-$URL}"
  local chrome="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

  if [ "$mode" = "window" ] && [ -x "$chrome" ]; then
    # A dedicated user-data-dir keeps this window separate from the user's
    # main Chrome profile — no logged-in accounts leak in, extensions don't
    # run, and Chrome treats each launch as its own "installed" app.
    local udd="$HOME/Library/Application Support/ResearchMap/chrome-app"
    mkdir -p "$udd"
    "$chrome" --app="$url" --user-data-dir="$udd" \
      --no-first-run --no-default-browser-check >>"$RM_LOG" 2>&1 &
    APP_WINDOW_PID=$!
    return 0
  fi

  # Fallback: whatever the user set as their default browser.
  open "$url" 2>/dev/null || true
  return 0
}

# -- lifecycle ------------------------------------------------------------
rm_shutdown() {
  # Idempotent — trap can fire twice (e.g. ^C during a read).
  if [ -n "${RM_SHUTDOWN_DONE:-}" ]; then return; fi
  RM_SHUTDOWN_DONE=1
  # Kill the Chrome app window first so its "connection refused" alert
  # doesn't flash for a beat while the server is being torn down.
  if [ -n "${APP_WINDOW_PID:-}" ] && kill -0 "$APP_WINDOW_PID" 2>/dev/null; then
    kill "$APP_WINDOW_PID" 2>/dev/null || true
  fi
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
