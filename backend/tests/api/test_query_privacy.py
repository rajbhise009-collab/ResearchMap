"""Regression: search text never leaves the browser (Playwright, built site).

For every way of searching (typing, type-ahead, example chips, the command
palette and its hand-offs, both "switch and ask there" links, a health
query): no request URL, Referer header, page URL, hash or document.title may
contain the query; a handed-over query must arrive in the right library; the
sessionStorage hand-off must be cleared after it is read. An old shared ?q=
link is ignored: the box stays empty, the app never reads q, and from the
very first request on the value is in no request URL after the first
navigation. (It stays in the page's own address bar, where the visitor put
it; that is accepted.) The checks live in tools/qa/query_privacy.py.

Needs the production build (frontend/out) and Playwright's Chromium. On the
runner and in CI (CI=1) this module may not skip (backend/tests/conftest.py).
"""
from __future__ import annotations

import importlib.util
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
OUT = REPO / "frontend" / "out" / "index.html"


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _load():
    spec = importlib.util.spec_from_file_location("query_privacy", REPO / "tools" / "qa" / "query_privacy.py")
    qp = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(qp)
    return qp


def test_search_text_never_leaves_the_browser():
    if not OUT.exists():
        pytest.skip("no production build (frontend/out); run `npm run build` first")
    try:
        import playwright.sync_api  # noqa: F401
    except ImportError:
        pytest.skip("Playwright is not installed")
    qp = _load()
    port = _free_port()
    srv = subprocess.Popen([sys.executable, str(REPO / "tools" / "qa" / "serve.py"), str(port)],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        base = f"http://127.0.0.1:{port}"
        for _ in range(40):
            try:
                socket.create_connection(("127.0.0.1", port), timeout=0.25).close()
                break
            except OSError:
                time.sleep(0.25)
        try:
            results = qp.run(base)
        except Exception as e:  # noqa: BLE001
            if "Executable doesn't exist" in str(e):
                pytest.skip("Playwright's Chromium is not installed")
            raise
        assert len(results) >= 12, results
        bad = qp.failures(results)
        assert not bad, "\n".join(bad)
    finally:
        srv.terminate()
