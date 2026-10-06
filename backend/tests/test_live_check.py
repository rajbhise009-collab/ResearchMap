"""tools/live-check.py against a local mock HTTP server: a healthy site
passes (analytics 404 is only a warning); a missing security header, a
foreign canonical host, or a broken og:image each fail."""

from __future__ import annotations

import importlib.util
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location("live_check", REPO / "tools" / "live-check.py")
live_check = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(live_check)

SEC = {"X-Content-Type-Options": "nosniff", "Referrer-Policy": "strict-origin-when-cross-origin",
       "Permissions-Policy": "camera=()", "X-Frame-Options": "DENY"}


def _site(base: str, *, drop_header=None, canon_host=None, og_status=200):
    ch = canon_host or base

    def page(path):
        return (f'<html><head><link rel="canonical" href="{ch}{path}"/>'
                f'<meta property="og:url" content="{ch}{path}"/>'
                f'<meta property="og:image" content="{base}/og/default.png"/></head></html>')
    routes = {
        "/": (200, page("/")),
        "/gap/x/": (200, page("/gap/x/")),
        "/sitemap.xml": (200, f"<urlset><url><loc>{base}/</loc></url><url><loc>{base}/gap/x/</loc></url></urlset>"),
        "/robots.txt": (200, f"User-Agent: *\nAllow: /\n\nSitemap: {base}/sitemap.xml\n"),
        "/og/default.png": (og_status, "png"),
    }
    headers = {k: v for k, v in SEC.items() if k != drop_header}
    return routes, headers


@pytest.fixture
def server():
    state = {}

    class H(BaseHTTPRequestHandler):
        def do_GET(self):
            status, body = state["routes"].get(self.path, (404, "not found"))
            self.send_response(status)
            for k, v in state["headers"].items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(body.encode())

        def log_message(self, *a):
            pass

    srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_address[1]}"
    yield base, state
    srv.shutdown()


def _run(base, state, **kw):
    state["routes"], state["headers"] = _site(base, **kw)
    code = live_check.main([base, "--vercel-host", ""])
    return code, list(live_check.results)


def test_healthy_site_passes_with_analytics_warning(server):
    base, state = server
    code, res = _run(base, state)
    assert code == 0, res
    assert ("WARN", "analytics script (/_vercel/insights/script.js)") in [(s, l) for s, l, _ in res]
    assert all(s != "FAIL" for s, _, _ in res)


def test_missing_security_header_fails(server):
    base, state = server
    code, res = _run(base, state, drop_header="X-Frame-Options")
    assert code == 1
    assert any(s == "FAIL" and "security headers" in l for s, l, _ in res)


def test_foreign_canonical_host_fails(server):
    base, state = server
    code, res = _run(base, state, canon_host="https://researchmap-one.vercel.app")
    assert code == 1
    assert any(s == "FAIL" and "canonical" in l for s, l, _ in res)


def test_broken_og_image_fails(server):
    base, state = server
    code, res = _run(base, state, og_status=404)
    assert code == 1
    assert any(s == "FAIL" and "og:image" in l for s, l, _ in res)



def test_fetch_follows_308_on_any_python(server):
    """Python 3.9's urllib does not follow 308; live-check follows it itself."""
    base, state = server
    state["routes"], state["headers"] = _site(base)
    state["routes"]["/old"] = (308, "")
    state["headers"] = {**state["headers"], "Location": base + "/"}  # used only by the 308
    status, _, _, final = live_check.fetch(base + "/old")
    assert status == 200 and final.rstrip("/") == base
