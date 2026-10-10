"""Smoke checks against a running site (local build or production).

  .venv/bin/python tools/qa/smoke.py [BASE] [--engines chromium,webkit] [--quick]

Per engine, desktop and iPhone 13: a shared Diet link with no ?lib opens
Diet; then for EVERY library in libraries.json: its card, one settled search
with gap results (Diet "alc", ML fairness "fair", LLM calibration "halluc",
others their most distinctive in-domain title phrase), "melanoma treatment"
refused, /gaps lists results, one gap page with its headline and (desktop) a
working .bib export; axe finds zero serious/critical issues on the home
page, /gaps and a gap page; no console errors anywhere. Exit 1 on any failure. --quick: Chromium
desktop only (the daily health check).
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "frontend" / "public" / "data"
AXE_PATH = Path(os.environ.get("AXE_PATH") or ROOT / "tools" / "qa" / "node_modules" / "axe-core" / "axe.min.js")
R: list[tuple[bool, str, str]] = []


def rec(ok, label, detail=""):
    R.append((ok, label, detail))
    print(f"[{'PASS' if ok else 'FAIL'}] {label}" + (f" — {detail}" if detail and not ok else ""), flush=True)


LIBS = json.loads((DATA / "libraries.json").read_text())["libraries"]
FACTS = {l["slug"]: l for l in json.loads((DATA / "site-facts.json").read_text())["libraries"]}
SETTLED = {"diet-and-mortality": "alc", "ml-fairness": "fair", "llm-calibration": "halluc"}


def _lib_dir(lib):
    return DATA if lib["snapshot_path"] == "/data" else DATA / lib["snapshot_path"].removeprefix("/data/")


def _first_gap(lib):
    items = json.loads((_lib_dir(lib) / "opportunities.json").read_text())["items"]
    vis = [i for i in items if i.get("verdict") in (None, "genuine")]
    return vis[0] if vis else None


def _phrase(slug):
    """A settled search for a library without a hand-picked one: its most
    distinctive title phrase that the search answers in_domain."""
    sys.path.insert(0, str(ROOT))
    from backend.app.api.search_index import search
    from backend.app.api.search_phrases import INDEX, queries   # stdlib only (no pytest)
    for q in queries(slug):
        if search(INDEX[slug], q)["verdict"] == "in_domain":
            return q
    return slug.replace("-", " ")


def ctx(p, br, mobile):
    kw = {"accept_downloads": True}
    if mobile:
        kw = {**dict(p.devices["iPhone 13"]), "accept_downloads": True}
        kw.pop("default_browser_type", None)
    c = br.new_context(**kw)
    # Analytics is not part of the site under test (404s until enabled).
    c.route("**/_vercel/insights/**", lambda r: r.fulfill(status=200, body=""))
    return c


def page(c, errs):
    pg = c.new_page()
    pg.on("pageerror", lambda e: errs.append(f"pageerror {str(e)[:120]}"))
    pg.on("console", lambda m: errs.append(f"console {m.text[:120]}") if m.type == "error" else None)
    return pg


def settle(pg, ms=900):
    try:
        pg.wait_for_load_state("networkidle", timeout=20000)
    except Exception:
        pass
    pg.wait_for_timeout(ms)


def search(pg, q):
    """Type like a reader. On a busy machine (shared CI runners) typing can
    stall; then reload once and enter the query directly, so a slow runner
    never fails a weekly publish on its own."""
    try:
        pg.fill("#ask-input", "")
        pg.type("#ask-input", q, delay=110, timeout=20000)
    except Exception:  # noqa: BLE001
        pg.reload()
        settle(pg, 800)
        pg.fill("#ask-input", q, timeout=20000)
    pg.wait_for_timeout(1600)
    b = pg.inner_text("body").lower()
    gaps = pg.locator("section:has(> p.section-eyebrow:text-is('Gaps we found')) .results-list > *").count()
    return b, pg.locator(".results-list > *").count(), gaps


def run(p, base, engine, mobile, axe):
    tag = f"{engine}/{'iphone13' if mobile else 'desktop'}"
    try:
        br = getattr(p, engine).launch(headless=True)
    except Exception:
        if engine != "chromium":
            raise
        br = p.chromium.launch(headless=True, channel="chrome")   # installed Chrome
    errs: list[str] = []
    diet = json.loads((DATA / "library" / "diet-and-mortality" / "opportunities.json").read_text())["items"][0]
    c = ctx(p, br, mobile)
    pg = page(c, errs)
    pg.goto(f"{base}/gap/{diet['slug']}/")
    settle(pg)
    rec(pg.locator("h1").first.inner_text().strip() == diet["consumer"]["headline"]
        and pg.evaluate("new URLSearchParams(location.search).get('lib')") == "diet-and-mortality",
        f"{tag} shared Diet link with no ?lib opens Diet")
    c.close()
    for lib in LIBS:
        slug, q = lib["slug"], SETTLED.get(lib["slug"]) or _phrase(lib["slug"])
        c = ctx(p, br, mobile)
        pg = page(c, errs)
        pg.goto(f"{base}/?lib={slug}")
        settle(pg, 500)
        card = pg.locator(".about-card").first.inner_text() if pg.locator(".about-card").count() else ""
        rec(lib["name"] in card, f"{tag} {slug} library card shows its name", card[:80])
        b, n, g = search(pg, q)
        banner = "that's not in this library" in b or "at the edge of this library" in b
        # A small or brand-new library may have few visible results (e.g. all
        # its disagreements still await the owner's audit): gap hits are
        # required only when it has at least 3.
        need_gaps = FACTS.get(slug, {}).get("results_total", 0) >= 3
        rec(n > 0 and (g > 0 or not need_gaps) and not banner,
            f"{tag} {slug} '{q}' → results" + (" incl. gaps" if need_gaps else ""),
            f"results={n} gaps={g} banner={banner}")
        pg.goto(f"{base}/?lib={slug}")          # fresh page: no state from the first search
        settle(pg, 500)
        b, _, _ = search(pg, "melanoma treatment")
        rec("that's not in this library" in b, f"{tag} {slug} 'melanoma treatment' refuses")
        c.close()
        c = ctx(p, br, mobile)
        pg = page(c, errs)
        pg.goto(f"{base}/gaps/?lib={slug}")
        settle(pg)
        cards = pg.locator(".results-list > *").count()
        rec(cards > 0, f"{tag} {slug} /gaps lists results", str(cards))
        first = _first_gap(lib)
        if first:
            pg.goto(f"{base}/gap/{first['slug']}/")
            settle(pg)
            h1 = pg.locator("h1").first.inner_text().strip().strip("“”\"")   # quoted headlines
            rec(h1 == first["consumer"]["headline"], f"{tag} {slug} gap page shows its headline",
                f"{h1[:60]!r} vs {first['consumer']['headline'][:60]!r}")
            if not mobile:      # downloads are a desktop check
                with pg.expect_download(timeout=8000) as dl:
                    pg.get_by_role("button", name="Download .bib").first.click()
                ok = dl.value.suggested_filename.endswith(".bib")
                rec(ok, f"{tag} {slug} gap page export downloads a .bib", dl.value.suggested_filename)
        c.close()
    if axe:
        for path in ("/?lib=diet-and-mortality", "/gaps/?lib=ml-fairness", f"/gap/{diet['slug']}/"):
            c = ctx(p, br, mobile)
            pg = page(c, errs)
            pg.goto(base + path)
            settle(pg)
            pg.add_script_tag(content=axe)
            v = pg.evaluate("""async () => (await axe.run(document, {resultTypes: ['violations']}))
                .violations.filter(v => ['serious','critical'].includes(v.impact)).map(v => v.id)""")
            rec(not v, f"{tag} axe {path}: 0 serious/critical", str(v))
            c.close()
    rec(not errs, f"{tag} no console errors", "; ".join(errs[:3]))
    br.close()


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    base = (args[0] if args else os.environ.get("SMOKE_BASE", "http://127.0.0.1:8765")).rstrip("/")
    quick = "--quick" in sys.argv
    engines = ["chromium"] if quick else ["chromium", "webkit"]
    for a in sys.argv[1:]:
        if a.startswith("--engines="):
            engines = a.split("=", 1)[1].split(",")
    axe = AXE_PATH.read_text() if AXE_PATH.exists() else None
    if axe is None:
        rec(False, "axe-core available", f"missing {AXE_PATH.name} (npm install axe-core; set AXE_PATH)")
    with sync_playwright() as p:
        for engine in engines:
            for mobile in ((False,) if quick else (False, True)):
                run(p, base, engine, mobile, axe)
    n_fail = sum(not ok for ok, _, _ in R)
    print(f"\nsmoke {base}: PASS={len(R) - n_fail} FAIL={n_fail}")
    return 1 if n_fail else 0


if __name__ == "__main__":
    raise SystemExit(main())
