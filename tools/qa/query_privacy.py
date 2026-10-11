"""Does search text ever leave the browser? (Playwright, the built site)

  .venv/bin/python tools/qa/query_privacy.py http://127.0.0.1:8799

For every way of searching, records: every request URL and its Referer
header, the page URL, the hash and document.title, before and after the
search, and fails if the query text appears in any of them (in any common
encoding). Also checks that a query handed to another page actually
arrived there (so "no leak" cannot pass by the feature silently breaking).

Covered: type + Enter (in-domain, out-of-domain), type-ahead without Enter,
an example chip, the command palette (type; Enter on a result; Enter with no
results; "See what this library covers"), the "Maybe wrong library? Switch
and ask there" link, the out-of-domain panel's "switch and ask there" links,
and a health query. Developer mode (?dev=1, local builds only) is out of
scope by design: its build-cost panel sends the query to the local server.
Only the given base URL is reachable; every other request is aborted.
"""
from __future__ import annotations

import json
import sys
import urllib.parse

from playwright.sync_api import sync_playwright


def _forms(q: str) -> set[str]:
    return {q, urllib.parse.quote(q), urllib.parse.quote_plus(q), urllib.parse.quote(q, safe=""),
            q.replace(" ", "%20"), q.replace(" ", "+")}


def _contains(text: str, q: str) -> bool:
    text = text or ""
    return any(f and f in text for f in _forms(q)) or any(f.lower() in text.lower() for f in _forms(q))


# --- the ways of searching -------------------------------------------------

def _type_enter(pg, q):
    pg.click("#ask-input"); pg.keyboard.type(q, delay=25); pg.keyboard.press("Enter")


def _type_only(pg, q):
    pg.click("#ask-input"); pg.keyboard.type(q, delay=25); pg.wait_for_timeout(1200)


def _chip(pg, q):
    pg.locator(".example-chip", has_text=q).first.click()


def _palette_type(pg, q):
    pg.keyboard.press("ControlOrMeta+k"); pg.wait_for_timeout(300); pg.keyboard.type(q, delay=25)
    pg.wait_for_timeout(900)


def _palette_enter(pg, q):
    _palette_type(pg, q); pg.keyboard.press("Enter")


def _palette_see_what_covers(pg, q):
    _palette_type(pg, q)
    pg.locator(".cmdk-list a", has_text="See what this library covers").first.click()


def _maybe_wrong_library(pg, q):
    _type_enter(pg, q); pg.wait_for_timeout(1500)
    pg.locator(".caveat a", has_text="Switch and ask there").first.click()


def _ood_panel_switch(pg, q):
    _type_enter(pg, q); pg.wait_for_timeout(1500)
    pg.locator("li a", has_text="switch and ask there").first.click()


SCENARIOS = [
    # (name, start library, query, action, library the query should arrive in)
    ("type + Enter, in-domain", "ml-fairness", "demographic parity", _type_enter, None),
    ("type + Enter, out-of-domain", "ml-fairness", "volcano eruption forecasting", _type_enter, None),
    ("type-ahead, no Enter", "ml-fairness", "equalized odds", _type_only, None),
    ("example chip", "ml-fairness", "what is demographic parity", _chip, None),
    ("palette: type", "ml-fairness", "risk assessment", _palette_type, None),
    ("palette: Enter on a result", "ml-fairness", "risk assessment", _palette_enter, None),
    ("palette: Enter with no results", "ml-fairness", "volcano eruption forecasting", _palette_enter,
     "ml-fairness"),
    ("palette: 'See what this library covers'", "ml-fairness", "volcano eruption forecasting",
     _palette_see_what_covers, "ml-fairness"),
    ("'Maybe wrong library? Switch and ask there'", "ml-fairness", "social media and teenage loneliness",
     _maybe_wrong_library, "social-media-teen-mental-health"),
    ("out-of-domain panel: 'switch and ask there'", "ml-fairness", "volcano eruption forecasting",
     _ood_panel_switch, "*"),
    ("health query (distress check)", "social-media-teen-mental-health", "screen time and depression",
     _type_enter, None),
]


def run(base: str) -> list[dict]:
    base = base.rstrip("/")
    results = []
    with sync_playwright() as p:
        br = p.chromium.launch()
        for name, lib, q, action, arrives_in in SCENARIOS:
            ctx = br.new_context(viewport={"width": 1440, "height": 900})
            ctx.route("**/*", lambda r: r.continue_() if r.request.url.startswith(base) else r.abort())
            seen = []
            ctx.on("request", lambda r: seen.append({"url": r.url, "referer": r.headers.get("referer", ""),
                                                      "body": r.post_data or ""}))
            pg = ctx.new_page()
            pg.goto(f"{base}/?lib={lib}", wait_until="networkidle")
            pg.wait_for_timeout(700)
            states = []
            action(pg, q)
            for _ in range(3):                       # sample the page as it settles
                pg.wait_for_timeout(700)
                states.append({"url": pg.url, "hash": pg.evaluate("location.hash"),
                               "title": pg.evaluate("document.title")})
            leaks = [f"request {r['url'][:120]}" for r in seen if _contains(r["url"], q)]
            leaks += [f"Referer of {r['url'][:80]}" for r in seen if _contains(r["referer"], q)]
            leaks += [f"request body to {r['url'][:80]}" for r in seen if _contains(r["body"], q)]
            for s in states:
                if _contains(s["url"], q):
                    leaks.append(f"page URL {s['url'][:120]}")
                if _contains(s["hash"], q):
                    leaks.append(f"hash {s['hash'][:80]}")
                if _contains(s["title"], q):
                    leaks.append(f"document.title {s['title'][:80]}")
            left = pg.evaluate("(() => { try { return sessionStorage.getItem('rm.handoff.query'); } catch (e) { return null; } })()")
            arrived = None
            if arrives_in:
                arrived_lib = pg.evaluate("new URLSearchParams(location.search).get('lib')")
                box = pg.locator("#ask-input")
                arrived = {"lib": arrived_lib, "query_in_box": box.input_value() if box.count() else None}
            results.append({"scenario": name, "query": q, "requests": len(seen),
                            "insights_requests": sum("/_vercel/insights" in r["url"] for r in seen),
                            "leaks": sorted(set(leaks)), "arrived": arrived, "expected_lib": arrives_in,
                            "left_in_session_storage": left,
                            "final_url": states[-1]["url"].replace(base, "")})
            ctx.close()
        # An old shared link with ?q=: the query is honoured once, then removed
        # from the address bar, so nothing loaded afterwards carries it.
        q = "demographic parity"
        ctx = br.new_context(viewport={"width": 1440, "height": 900})
        ctx.route("**/*", lambda r: r.continue_() if r.request.url.startswith(base) else r.abort())
        pg = ctx.new_page()
        pg.goto(f"{base}/?lib=ml-fairness&q={urllib.parse.quote(q)}", wait_until="networkidle")
        pg.wait_for_timeout(1200)
        later = []
        ctx.on("request", lambda r: later.append({"url": r.url, "referer": r.headers.get("referer", "")}))
        pg.locator("a[href*='/gaps']").first.click()
        pg.wait_for_timeout(1500)
        results.append({"scenario": "old shared ?q= link (honoured once, then stripped)", "query": q,
                        "requests": len(later), "insights_requests": 0, "expected_lib": None, "arrived": None,
                        "left_in_session_storage": None, "final_url": pg.url.replace(base, ""),
                        "leaks": sorted({f"Referer of {r['url'][:80]}" for r in later if _contains(r["referer"], q)}
                                        | {f"request {r['url'][:80]}" for r in later if _contains(r["url"], q)})})
        ctx.close()
        br.close()
    return results


def failures(results: list[dict]) -> list[str]:
    out = []
    for r in results:
        if r["leaks"]:
            out.append(f"{r['scenario']}: query text left the page via {r['leaks'][:3]}")
        if r.get("left_in_session_storage"):
            out.append(f"{r['scenario']}: the hand-off was not cleared after it was read")
        if r["expected_lib"]:
            a = r["arrived"] or {}
            if a.get("query_in_box") != r["query"]:
                out.append(f"{r['scenario']}: the query did not arrive on the next page ({a})")
            if r["expected_lib"] != "*" and a.get("lib") != r["expected_lib"]:
                out.append(f"{r['scenario']}: arrived in library {a.get('lib')}, expected {r['expected_lib']}")
    return out


if __name__ == "__main__":
    res = run(sys.argv[1])
    print(json.dumps(res, indent=1))
    bad = failures(res)
    print("\n".join(bad) if bad else f"query privacy: OK ({len(res)} ways of searching, no leak)")
    sys.exit(1 if bad else 0)
