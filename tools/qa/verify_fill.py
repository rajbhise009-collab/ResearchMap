"""Verify the filled libraries + simplified stats card on the production build.

  .venv/bin/python tools/qa/verify_fill.py      # server: tools/qa/serve.py on :8765

Chromium and WebKit, desktop and iPhone 13; fresh context per check; settled
waits. Expected values come from site-facts.json and the snapshots. Results
print as PASS/FAIL and are written to ~/ResearchMap-private/launch-qa/.
"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "frontend" / "public" / "data"
BASE = "http://127.0.0.1:8765"
AXE = (ROOT / "tools" / "qa" / "node_modules" / "axe-core" / "axe.min.js").read_text()
QA = Path.home() / "ResearchMap-private" / "launch-qa"
FACTS = {l["slug"]: l for l in json.loads((DATA / "site-facts.json").read_text())["libraries"]}
R: list[tuple[bool, str, str]] = []


def rec(ok, label, detail=""):
    R.append((ok, label, detail))
    print(f"[{'PASS' if ok else 'FAIL'}] {label}" + (f" — {detail}" if detail and not ok else ""), flush=True)


def lib_dir(slug):
    return DATA if slug == "llm-calibration" else DATA / "library" / slug


def ctx(br, p=None, mobile=False, **kw):
    if mobile:
        d = dict(p.devices["iPhone 13"])
        d.pop("default_browser_type", None)
        kw = {**d, **kw}
    c = br.new_context(**kw)
    c.route("**/_vercel/insights/**", lambda r: r.fulfill(status=200, body=""))
    return c


def settle(pg, ms=900):
    pg.wait_for_load_state("networkidle")
    pg.wait_for_timeout(ms)


def watch(pg, errs):
    pg.on("pageerror", lambda e: errs.append(f"pageerror {e}"))
    pg.on("console", lambda m: errs.append(f"console {m.text}") if m.type == "error" else None)


def plural(n, one, many):
    return f"{n} {one if n == 1 else many}"


def card_checks(p, br, engine, mobile):
    for slug, f in FACTS.items():
        c = ctx(br, p, mobile)
        pg = c.new_page()
        errs = []
        watch(pg, errs)
        pg.goto(f"{BASE}/?lib={slug}")
        settle(pg)
        want = f"{plural(f['papers'], 'paper', 'papers')} · {plural(f['results_total'], 'result', 'results')}"
        line = pg.locator(".about-card .lib-summary-line").first.inner_text().strip()
        btn = pg.locator(".about-card .lib-summary-toggle").first
        hidden_before = not pg.locator(".about-card .lib-summary-panel").first.is_visible()
        if mobile:
            btn.tap()
        else:
            btn.click()
        pg.wait_for_timeout(300)
        panel = pg.locator(".about-card .lib-summary-panel").first
        txt = panel.inner_text() if panel.is_visible() else ""
        ok = (line == want and hidden_before and btn.get_attribute("aria-expanded") == "true"
              and "Read in full" in txt and "Library built" in txt and not errs)
        body = pg.locator(".about-card").inner_text()
        dup = "Claims read from" in body or "Read in full" in body.split("How this library was built")[0]
        rec(ok and not dup, f"{engine}/{'mobile' if mobile else 'desktop'} {slug}: card '{want}' + working toggle",
            f"line={line!r} hidden_before={hidden_before} expanded={btn.get_attribute('aria-expanded')} dup={dup} errs={errs[:1]}")
        if engine == "chromium" and not mobile and slug == "diet-and-mortality":
            pg.screenshot(path=str(QA / "fill-diet-card-open.png"))
        c.close()


def gaps_checks(p, br):
    kinds = json.loads((DATA / "language.json").read_text())["kinds"]
    for slug, f in FACTS.items():
        c = ctx(br, p)
        pg = c.new_page()
        pg.goto(f"{BASE}/gaps/?lib={slug}")
        settle(pg, 1200)
        n_cards = pg.locator(".results-list > *").count()
        txt = pg.inner_text("main")
        types = {r["type"]: r["count"] for r in f["results"]}
        need = {"unresolved_contradictions": "disagreement", "persistent_limitations": "unaddressed_limitation",
                "structural_holes": "method_transfer", "orphaned_future_work": "unfollowed_future_work"}
        missing = [kinds[k]["name"] for t, k in need.items() if (types.get(t) or 0) > 0 and kinds[k]["name"] not in txt]
        rec(n_cards == f["results_total"] and not missing,
            f"/gaps {slug}: {n_cards} results listed with their type labels",
            f"cards={n_cards} want={f['results_total']} missing labels={missing}")
        c.close()


def detail_checks(p, br):
    for slug in ("diet-and-mortality", "ml-fairness"):
        items = json.loads((lib_dir(slug) / "opportunities.json").read_text())["items"]
        for it in [i for i in items if i["slug"].startswith(f"opp-{slug}-")]:
            c = ctx(br, p, accept_downloads=True)
            pg = c.new_page()
            errs = []
            watch(pg, errs)
            pg.goto(f"{BASE}/gap/{it['slug']}/")
            settle(pg)
            h1 = pg.locator("h1").first.inner_text().strip()
            want_h = it["consumer"]["headline"]
            ok_h = h1 == (f"“{want_h}”" if it["consumer"].get("headline_is_quoted") else want_h)
            strength = it["consumer"]["strength"].lower() in pg.inner_text("main").lower()
            bib_ok = False
            btn = pg.get_by_role("button", name="Download .bib")
            if btn.count():
                with pg.expect_download() as d:
                    btn.first.click()
                path = d.value.path()
                bib = Path(path).read_text()
                bib_ok = bool(re.search(r"@\w+\{", bib)) and "undefined" not in bib and "null" not in bib
            lib = pg.evaluate("new URLSearchParams(location.search).get('lib')")
            rec(ok_h and strength and bib_ok and lib == slug and not errs,
                f"detail {it['slug']}: renders, strength shown, BibTeX parses",
                f"h1_ok={ok_h} strength={strength} bib={bib_ok} lib={lib} errs={errs[:1]}")
            c.close()


def search(pg, q, mobile=False):
    pg.fill("#ask-input", "")
    if mobile:
        pg.focus("#ask-input")
        for ch in q:
            pg.evaluate("""([ch]) => { const el = document.querySelector('#ask-input');
              const set = Object.getOwnPropertyDescriptor(Object.getPrototypeOf(el), 'value').set;
              set.call(el, el.value + ch);
              el.dispatchEvent(new InputEvent('input', {bubbles: true, inputType: 'insertText', data: ch})); }""", [ch])
            pg.wait_for_timeout(120)
    else:
        pg.type("#ask-input", q, delay=120)
    pg.wait_for_timeout(1500)
    b = pg.inner_text("body").lower()
    gaps = pg.locator("section:has(> p.section-eyebrow:text-is('Gaps we found')) .results-list > *").count()
    return b, pg.locator(".results-list > *").count(), gaps


def regression(p, br, engine, mobile):
    tag = f"{engine}/{'mobile' if mobile else 'desktop'}"
    diet = json.loads((DATA / "library" / "diet-and-mortality" / "opportunities.json").read_text())["items"][0]
    c = ctx(br, p, mobile)
    pg = c.new_page()
    pg.goto(f"{BASE}/gap/{diet['slug']}/")
    settle(pg)
    rec(pg.locator("h1").first.inner_text().strip() == diet["consumer"]["headline"]
        and pg.evaluate("new URLSearchParams(location.search).get('lib')") == "diet-and-mortality",
        f"{tag} shared Diet link with no ?lib opens Diet")
    c.close()
    for slug, q, need_gaps in [("diet-and-mortality", "alc", True), ("ml-fairness", "fair", True),
                               ("llm-calibration", "halluc", True)]:
        c = ctx(br, p, mobile)
        pg = c.new_page()
        pg.goto(f"{BASE}/?lib={slug}")
        settle(pg, 500)
        b, n, g = search(pg, q, mobile)
        banner = "that's not in this library" in b or "at the edge of this library" in b
        rec(n > 0 and (g > 0 or not need_gaps) and not banner, f"{tag} {slug} '{q}' → results incl. gaps",
            f"results={n} gaps={g} banner={banner}")
        c.close()
    for slug in FACTS:
        c = ctx(br, p, mobile)
        pg = c.new_page()
        pg.goto(f"{BASE}/?lib={slug}")
        settle(pg, 500)
        b, _, _ = search(pg, "melanoma treatment", mobile)
        rec("that's not in this library" in b, f"{tag} {slug} 'melanoma treatment' refuses")
        c.close()


def axe_card(p, br):
    for scheme in ("light", "dark"):
        for slug in FACTS:
            for opened in (False, True):
                c = ctx(br, p, color_scheme=scheme)
                pg = c.new_page()
                pg.goto(f"{BASE}/?lib={slug}")
                settle(pg)
                if opened:
                    pg.locator(".about-card .lib-summary-toggle").first.click()
                    pg.wait_for_timeout(200)
                pg.add_script_tag(content=AXE)
                v = pg.evaluate("""async () => (await axe.run('.about-card', {runOnly: {type: 'tag',
                    values: ['wcag2a','wcag2aa','wcag21a','wcag21aa']}})).violations
                    .filter(x => ['serious','critical'].includes(x.impact)).map(x => x.id + ':' + x.nodes.length)""")
                rec(not v, f"axe {scheme} {slug} card ({'open' if opened else 'closed'}): 0 serious/critical", str(v))
                c.close()


def main() -> int:
    with sync_playwright() as p:
        chrome = p.chromium.launch(channel="chrome", headless=True)
        webkit = p.webkit.launch(headless=True)
        for engine, br in (("chromium", chrome), ("webkit", webkit)):
            for mobile in (False, True):
                card_checks(p, br, engine, mobile)
                regression(p, br, engine, mobile)
        gaps_checks(p, chrome)
        detail_checks(p, chrome)
        axe_card(p, chrome)
        chrome.close()
        webkit.close()
    (QA / "verify-fill.json").write_text(json.dumps([{"ok": a, "label": b, "detail": c} for a, b, c in R], indent=2))
    print(f"\nPASS={sum(a for a, _, _ in R)} FAIL={sum(not a for a, _, _ in R)}")
    return 0 if all(a for a, _, _ in R) else 1


if __name__ == "__main__":
    raise SystemExit(main())
