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

An old shared link carrying ?q= is ignored: the page opens with an empty box,
and the value reaches no request after the first navigation and no Referer
header (every request is watched, from the first one). Both vercel.json
files must send Referrer-Policy: strict-origin (referrer_policy_problems).

The developer-mode note about OpenAlex (DEV_OPENALEX_NOTE) must not appear
outside developer mode: the public build is checked with and without ?dev=1
(dev_note_visible; run it against an ENABLE_DEV=1 build to see it appear).
"""
from __future__ import annotations

import json
import sys
import urllib.parse
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
# The root copy is what tools/qa/serve.py serves; Vercel deploys frontend/.
VERCEL_CONFIGS = (REPO / "vercel.json", REPO / "frontend" / "vercel.json")
REFERRER_POLICY = "strict-origin"   # origin only: never a path or query string
DEV_OPENALEX_NOTE = ("In developer mode, opening this panel sends your question, through the local "
                     "server, to OpenAlex (api.openalex.org), a public catalogue of research papers, "
                     "to estimate how much literature exists on it.")


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


def referrer_policy_problems(configs=VERCEL_CONFIGS) -> list[str]:
    """Each config must set Referrer-Policy to exactly strict-origin, on every
    route that sets it, and set it on at least one route."""
    out = []
    for path in configs:
        values = [h.get("value") for rule in json.loads(Path(path).read_text()).get("headers", [])
                  for h in rule.get("headers", []) if str(h.get("key", "")).lower() == "referrer-policy"]
        if not values:
            out.append(f"{path}: no Referrer-Policy header")
        out += [f"{path}: Referrer-Policy is {v!r}, expected {REFERRER_POLICY!r}"
                for v in values if v != REFERRER_POLICY]
    return out


def dev_note_visible(br, base: str, path: str) -> dict:
    """Open the out-of-domain "build a library" panel at `path` and report
    whether the developer-mode OpenAlex note is on the page. Requests leave
    only for `base` (a static server answers /api/preflight with 404)."""
    ctx = br.new_context(viewport={"width": 1440, "height": 900})
    ctx.route("**/*", lambda r: r.continue_() if r.request.url.startswith(base) else r.abort())
    pg = ctx.new_page()
    pg.goto(f"{base}{path}", wait_until="networkidle")
    pg.wait_for_timeout(700)
    _type_enter(pg, "volcano eruption forecasting")
    pg.wait_for_timeout(1500)
    before = pg.locator("body").inner_text()
    pg.locator("button.cta").first.click()
    pg.wait_for_timeout(1200)
    panel = pg.locator(".panel").first.inner_text() if pg.locator(".panel").count() else ""
    after = pg.locator("body").inner_text()
    ctx.close()
    return {"path": path, "panel_opened": bool(panel), "before_click": DEV_OPENALEX_NOTE in before,
            "after_click": DEV_OPENALEX_NOTE in after}


def run(base: str) -> list[dict]:
    from playwright.sync_api import sync_playwright

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
        # An old shared link with ?q=. The app ignores q: the box stays empty
        # and the value is never read into the page. Every request is watched
        # from the first one, so scripts fetched before hydration count too.
        # The value DOES remain in this page's own address bar (the visitor
        # put it there and the app does not rewrite the URL); that is accepted.
        # With Referrer-Policy: strict-origin no Referer carries it, and the
        # only request whose URL may contain it is the first navigation.
        q = "zzqlegacy probe"
        ctx = br.new_context(viewport={"width": 1440, "height": 900})
        ctx.route("**/*", lambda r: r.continue_() if r.request.url.startswith(base) else r.abort())
        seen = []
        ctx.on("request", lambda r: seen.append({"url": r.url, "referer": r.headers.get("referer", ""),
                                                  "body": r.post_data or ""}))
        pg = ctx.new_page()
        link = f"{base}/?lib=ml-fairness&q={urllib.parse.quote(q)}"
        pg.goto(link, wait_until="networkidle")
        pg.wait_for_timeout(1200)
        box = pg.locator("#ask-input")
        box_value = box.input_value() if box.count() else None
        page_state = pg.evaluate("""() => {
            const all = s => { try { return JSON.stringify(Object.entries(s)); } catch (e) { return ''; } };
            return { session: all(sessionStorage), local: all(localStorage), title: document.title,
                     text: document.body.innerText,
                     inputs: [...document.querySelectorAll('input,textarea')].map(e => e.value).join('\\n'),
                     url: location.href, lib: new URLSearchParams(location.search).get('lib') };
        }""")
        pg.locator("a[href*='/gaps']").first.click()       # requests made after a click count too
        pg.wait_for_timeout(1500)
        first, rest = (seen[0] if seen else {"url": ""}), seen[1:]
        leaks = [f"Referer of {r['url'][:80]}" for r in seen if _contains(r["referer"], q)]
        leaks += [f"request {r['url'][:80]}" for r in rest if _contains(r["url"], q)]
        leaks += [f"request body to {r['url'][:80]}" for r in seen if _contains(r["body"], q)]
        read = [k for k in ("session", "local", "title", "text", "inputs") if _contains(page_state[k], q)]
        if page_state["url"] != link:
            read.append(f"address bar rewritten to {page_state['url'].replace(base, '')}")
        results.append({"scenario": "old shared ?q= link (ignored)", "query": q, "legacy": True,
                        "requests": len(seen), "insights_requests": sum("/_vercel/insights" in r["url"] for r in seen),
                        "first_request_is_the_link": first["url"] == link,
                        "box_value": box_value, "q_read_into": read, "lib": page_state["lib"],
                        "expected_lib": None, "arrived": None, "left_in_session_storage": None,
                        "final_url": pg.url.replace(base, ""), "leaks": sorted(set(leaks))})
        ctx.close()
        # The developer-mode note must not show on a public (non-ENABLE_DEV)
        # build, whether or not the URL asks for ?dev=1.
        for path in ("/?lib=ml-fairness", "/?lib=ml-fairness&dev=1"):
            d = dev_note_visible(br, base, path)
            results.append({"scenario": f"developer-mode note hidden ({path})", "query": "", "dev_note": d,
                            "requests": 0, "insights_requests": 0, "expected_lib": None, "arrived": None,
                            "left_in_session_storage": None, "final_url": path, "leaks": []})
        br.close()
    return results


def failures(results: list[dict]) -> list[str]:
    out = []
    for r in results:
        if r["leaks"]:
            out.append(f"{r['scenario']}: query text left the page via {r['leaks'][:3]}")
        if r.get("left_in_session_storage"):
            out.append(f"{r['scenario']}: the hand-off was not cleared after it was read")
        if r.get("legacy"):
            if r["box_value"] != "":
                out.append(f"{r['scenario']}: the search box is not empty ({r['box_value']!r})")
            if r["q_read_into"]:
                out.append(f"{r['scenario']}: the app read q (found in {r['q_read_into']})")
            if r["lib"] != "ml-fairness":
                out.append(f"{r['scenario']}: ?lib= was not kept ({r['lib']!r})")
            if not r["first_request_is_the_link"]:
                out.append(f"{r['scenario']}: requests were not watched from the first navigation")
        if r.get("dev_note"):
            d = r["dev_note"]
            if not d["panel_opened"]:
                out.append(f"{r['scenario']}: the build panel did not open")
            if d["before_click"] or d["after_click"]:
                out.append(f"{r['scenario']}: the developer-mode OpenAlex note is visible outside developer mode")
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
    bad = failures(res) + referrer_policy_problems()
    print("\n".join(bad) if bad else f"query privacy: OK ({len(res)} ways of searching, no leak)")
    sys.exit(1 if bad else 0)
