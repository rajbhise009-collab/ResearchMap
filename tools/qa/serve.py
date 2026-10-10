"""Serve frontend/out like Vercel does for this project (trailingSlash +
cleanUrls): /x -> 308 /x/, /x/ -> x/index.html, unknown -> 404.html with a
404 status, plus the vercel.json headers. QA only.

  .venv/bin/python tools/qa/serve.py [port]
"""
import http.server
import json
import socketserver
import sys
import urllib.parse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "frontend" / "out"
HEADERS = [(h["key"], h["value"])
           for block in json.loads((ROOT / "vercel.json").read_text()).get("headers", [])
           for h in block["headers"]]


class H(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *a, **k):
        super().__init__(*a, directory=str(OUT), **k)

    def end_headers(self):
        for k, v in HEADERS:
            self.send_header(k, v)
        super().end_headers()

    def log_message(self, *a):
        pass

    def send_head(self):
        raw = self.path.split("?", 1)[0].split("#", 1)[0]
        path = urllib.parse.unquote(raw)
        fs = OUT / path.lstrip("/")
        if not path.endswith("/") and "." not in path.rsplit("/", 1)[-1] and (fs / "index.html").exists():
            self.send_response(308)
            q = self.path[len(raw):]
            self.send_header("Location", raw + "/" + q)
            self.end_headers()
            return None
        if (fs.is_dir() and (fs / "index.html").exists()) or fs.is_file():
            return super().send_head()
        body = (OUT / "404.html").read_bytes()
        self.send_response(404)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
        return None


class TS(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True
    # The default listen backlog (5) overflows when a page loads several
    # libraries' data in parallel: the OS then RESETS the extra connections
    # and the browser checks see "Failed to load resource:
    # net::ERR_CONNECTION_RESET" from this QA server, not from the site.
    request_queue_size = 128


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8765
    TS(("127.0.0.1", port), H).serve_forever()
