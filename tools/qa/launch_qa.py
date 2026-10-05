"""Launch QA against the production static build (tools/qa/serve.py on :8765).

  .venv/bin/python tools/qa/launch_qa.py <section>... [--out DIR]

Sections: deeplinks console failures search axe keyboard weight
Fresh browser context per check. Results append to <out>/results.jsonl and
print as PASS/FAIL lines; screenshots go to <out>/shots/. Expected values
are read from the shipped JSON and the built HTML, never hard-coded.

The Vercel analytics script (/_vercel/insights/*) only exists on Vercel;
it is answered with an empty script here so its absence is not counted as
a console error.
"""
from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
OUT_SITE = ROOT / "frontend" / "out"
DATA = ROOT / "frontend" / "public" / "data"
BASE = "http://127.0.0.1:8765"
AXE = (ROOT / "tools" / "qa" / "node_modules" / "axe-core" / "axe.min.js").read_text()
QA = Path.home() / "ResearchMap-private" / "launch-qa"
SHOTS = QA / "shots"
SHOTS.mkdir(parents=True, exist_ok=True)
RESULTS: list[dict] = []
BLOCK_STORAGE = """(() => { const thrower = { get() { throw new DOMException('blocked', 'SecurityError'); } };
  try { Object.defineProperty(window, 'localStorage', thrower); } catch (e) {}
  try { Object.defineProperty(window, 'sessionStorage', thrower); } catch (e) {} })();"""


def rec(section: str, ok: bool, label: str, detail: str = "") -> None:
    RESULTS.append({"section": section, "ok": ok, "label": label, "detail": detail})
    print(f"[{'PASS' if ok else 'FAIL'}] {section}: {label}" + (f" — {detail}" if detail and not ok else ""))


def manifest() -> dict:
    return json.loads((DATA / "libraries.json").read_text())


def lib_dir(slug: str) -> Path:
    lib = next(l for l in manifest()["libraries"] if l["slug"] == slug)
    return DATA if lib["snapshot_path"] == "/data" else DATA / lib["snapshot_path"].removeprefix("/data/")


def built_title(path: str) -> str:
    h = (OUT_SITE / path.strip("/") / "index.html").read_text()
    return re.search(r"<title>([^<]*)</title>", h).group(1).replace("&amp;", "&").replace("&#x27;", "'").replace("&quot;", '"')


def samples() -> list[dict]:
    out = []
    for lib in manifest()["libraries"]:
        d = lib_dir(lib["slug"])
        gaps = json.loads((d / "opportunities.json").read_text())["items"]
        papers = json.loads((d / "papers.json").read_text())["items"]
        item = {"lib": lib["slug"], "name": lib["name"]}
        if gaps:
            g = json.loads((d / "opportunity" / f"{gaps[0]['slug']}.json").read_text())
            h = g["consumer"]["headline"]
            item["gap"] = (gaps[0]["slug"], f"“{h}”" if g["consumer"].get("headline_is_quoted") else h)
        p = papers[0]
        item["paper"] = (p["wid"], p.get("title") or p["wid"])
        out.append(item)
    return out


def new_ctx(browser, *, block_storage=False, **kw):
    c = browser.new_context(**kw)
    c.route("**/_vercel/insights/**", lambda r: r.fulfill(status=200, body="", content_type="text/javascript"))
    if block_storage:
        c.add_init_script(BLOCK_STORAGE)
    return c


def settle(pg, ms=900):
    pg.wait_for_load_state("networkidle")
    pg.wait_for_timeout(ms)


# ---------------------------------------------------------------------------

def deeplinks(br) -> None:
    S = "deeplinks"
    libs = manifest()["libraries"]
    for s in samples():
        wrong = next(l["slug"] for l in libs if l["slug"] != s["lib"])
        for kind in ("gap", "paper"):
            if kind not in s:
                continue
            ident, heading = s[kind]
            path = f"/{kind}/{ident}/"
            want_title = built_title(path)
            for case, query, block in [("no ?lib", "", False), ("right ?lib", f"?lib={s['lib']}", False),
                                       ("wrong ?lib", f"?lib={wrong}", False),
                                       ("storage blocked", "", True)]:
                c = new_ctx(br, block_storage=block)
                pg = c.new_page()
                errors: list[str] = []
                pg.on("pageerror", lambda e: errors.append(str(e)))
                pg.goto(BASE + path + query)
                settle(pg)
                h1 = pg.locator("h1").first.inner_text().strip()
                lib_now = pg.evaluate("new URLSearchParams(location.search).get('lib')")
                notice = pg.locator(".lib-switch-notice").count() > 0
                expect_notice = case == "wrong ?lib" or (case in ("no ?lib", "storage blocked")
                                                         and s["lib"] != manifest()["default_slug"])
                ok = (h1 == heading and pg.title() == want_title and lib_now == s["lib"]
                      and notice == expect_notice and not errors)
                stored = None if block else pg.evaluate("localStorage.getItem('researchmap.library')")
                if not block and expect_notice:
                    ok = ok and stored == s["lib"]   # a switch updates the stored choice
                rec(S, ok, f"{s['lib']} {kind} · {case}",
                    f"h1={h1[:50]!r} want={heading[:50]!r} title_ok={pg.title() == want_title} "
                    f"lib={lib_now} notice={notice}/{expect_notice} stored={stored} errors={errors[:1]}")
                if case == "wrong ?lib" and kind == "gap" and s["lib"] == "diet-and-mortality":
                    pg.screenshot(path=str(SHOTS / "deeplink-diet-gap-wrong-lib.png"))
                c.close()
    for path in ("/gap/no-such-gap-id/", "/paper/W0000000000/"):
        c = new_ctx(br)
        pg = c.new_page()
        resp = pg.goto(BASE + path)
        settle(pg, 400)
        b = pg.inner_text("body").lower()
        ok = (resp.status == 404 and "isn't here" in b and pg.locator(".notfound a[href='/']").count() > 0
              and all(pg.locator(f".notfound a[href='/?lib={l['slug']}']").count() > 0 for l in libs))
        rec(S, ok, f"unknown id {path} → on-brand 404 with search and library links", f"status={resp.status}")
        if path.startswith("/gap"):
            pg.screenshot(path=str(SHOTS / "unknown-id-404.png"))
        c.close()


def page_types() -> list[tuple[str, str]]:
    out = []
    for s in samples():
        q = f"?lib={s['lib']}"
        out += [(s["lib"], "/" + q), (s["lib"], "/gaps/" + q), (s["lib"], "/papers/" + q),
                (s["lib"], "/library/" + q), (s["lib"], f"/paper/{s['paper'][0]}/" + q)]
        if "gap" in s:
            out.append((s["lib"], f"/gap/{s['gap'][0]}/" + q))
    findings = json.loads((DATA / "findings.json").read_text())["items"]
    out += [("-", p) for p in ("/about/", "/method/", "/privacy/", "/terms/", "/contact/",
                               f"/findings/{findings[0]['slug']}/", "/no-such-page/")]
    return out


def console(br) -> None:
    S = "console"
    for lib, path in page_types():
        c = new_ctx(br)
        pg = c.new_page()
        msgs: list[str] = []
        pg.on("console", lambda m: msgs.append(f"{m.type}: {m.text}") if m.type in ("error", "warning") else None)
        pg.on("pageerror", lambda e: msgs.append(f"pageerror: {e}"))
        pg.goto(BASE + path)
        settle(pg)
        errs = [m for m in msgs if m.startswith(("error", "pageerror"))
                and not (path == "/no-such-page/" and "404" in m)]
        hyd = [m for m in msgs if "hydrat" in m.lower() or "did not match" in m.lower()]
        rec(S, not errs and not hyd, f"{path}", "; ".join((errs + hyd)[:2]))
        c.close()


def failures(br) -> None:
    S = "failures"
    for s in samples():
        for path, file in (("/", "stats.json"), ("/gaps/", "opportunities.json"),
                           (f"/paper/{s['paper'][0]}/", f"paper/{s['paper'][0]}.json")):
            c = new_ctx(br)
            pg = c.new_page()
            snap = "/data" if s["lib"] == manifest()["default_slug"] else f"/data/library/{s['lib']}"
            pg.route(f"**{snap}/{file}", lambda r: r.fulfill(status=404, body="not found"))
            errors: list[str] = []
            pg.on("pageerror", lambda e: errors.append(str(e)))
            pg.goto(f"{BASE}{path}?lib={s['lib']}")
            settle(pg)
            b = pg.inner_text("body")
            ok = (len(b.strip()) > 200 and "Application error" not in b and "Unhandled" not in b
                  and not errors and pg.locator("header.masthead").count() == 1)
            rec(S, ok, f"{s['lib']} {path} with {file} → 404", f"errors={errors[:1]} len={len(b)}")
            c.close()
    # slow 3G (Chromium only) and blocked storage on a heavy page
    c = new_ctx(br)
    pg = c.new_page()
    cdp = c.new_cdp_session(pg)
    cdp.send("Network.enable")
    cdp.send("Network.emulateNetworkConditions", {"offline": False, "latency": 400,
             "downloadThroughput": 400 * 1024 / 8, "uploadThroughput": 400 * 1024 / 8})
    t0 = time.time()
    pg.goto(BASE + "/gaps/?lib=diet-and-mortality", wait_until="domcontentloaded")
    early = pg.inner_text("body")
    pg.screenshot(path=str(SHOTS / "slow3g-early.png"))
    pg.wait_for_load_state("networkidle", timeout=120000)
    late = pg.inner_text("body")
    rec(S, len(early.strip()) > 100 and len(late.strip()) > 200,
        f"slow 3G: /gaps shows content or a loading message before data arrives "
        f"(network idle after {time.time() - t0:.1f}s)", early[:120])
    c.close()
    c = new_ctx(br, block_storage=True)
    pg = c.new_page()
    errors = []
    pg.on("pageerror", lambda e: errors.append(str(e)))
    pg.goto(BASE + "/?lib=ml-fairness")
    settle(pg)
    pg.fill("#ask-input", "")
    pg.type("#ask-input", "fair", delay=80)
    pg.wait_for_timeout(1500)
    n = pg.locator(".results-list > *").count()
    rec(S, not errors and n > 0, "blocked storage: home + search still work via ?lib", f"errors={errors[:1]} results={n}")
    c.close()


def type_settled(pg, text: str, mobile: bool = False) -> None:
    sel = "#ask-input"
    pg.wait_for_selector(sel)
    pg.fill(sel, "")
    if mobile:
        pg.focus(sel)
        for ch in text:
            pg.evaluate("""([s, ch]) => { const el = document.querySelector(s);
              const set = Object.getOwnPropertyDescriptor(Object.getPrototypeOf(el), 'value').set;
              set.call(el, el.value + ch);
              el.dispatchEvent(new InputEvent('input', {bubbles: true, inputType: 'insertText', data: ch})); }""",
                        [sel, ch])
            pg.wait_for_timeout(120)
    else:
        pg.type(sel, text, delay=120)
    pg.wait_for_timeout(1500)


def search(p, engines=("chromium", "webkit")) -> None:
    S = "search"
    for engine in engines:
        bt = getattr(p, engine)
        br = bt.launch(channel="chrome", headless=True) if engine == "chromium" else bt.launch(headless=True)
        for mode in ("desktop", "mobile"):
            kw = dict(p.devices["iPhone 13"]) if mode == "mobile" else {}
            if engine == "chromium" and mode == "mobile":
                kw.pop("default_browser_type", None)
            for slug, q, kind in [("diet-and-mortality", "alc", "results"), ("ml-fairness", "fair", "results"),
                                  ("llm-calibration", "halluc", "results"),
                                  *[(l["slug"], qq, "refuse") for l in manifest()["libraries"]
                                    for qq in ("melanoma treatment", "camera cal")]]:
                c = new_ctx(br, **kw)
                pg = c.new_page()
                pg.goto(f"{BASE}/?lib={slug}")
                settle(pg, 500)
                type_settled(pg, q, mobile=(mode == "mobile"))
                b = pg.inner_text("body").lower()
                refused = "that's not in this library" in b
                edge = "at the edge of this library" in b
                n = pg.locator(".results-list > *").count()
                if kind == "results":
                    ok = n > 0 and not refused and not edge
                else:
                    ok = (refused or "gaps we found" not in b) and not edge
                rec(S, ok, f"{engine}/{mode} {slug} '{q}' → {kind}", f"results={n} refused={refused} edge={edge}")
                c.close()
        br.close()


def axe(br) -> None:
    S = "axe"
    s = {x["lib"]: x for x in samples()}
    diet = s["diet-and-mortality"]
    pages = ["/", "/gaps/", f"/gap/{diet['gap'][0]}/", f"/paper/{diet['paper'][0]}/", "/about/",
             "/method/", "/privacy/", "/terms/", "/contact/", "/no-such-page/"]
    for scheme in ("light", "dark"):
        for path in pages:
            c = new_ctx(br, color_scheme=scheme)
            pg = c.new_page()
            pg.goto(BASE + path)
            settle(pg)
            pg.add_script_tag(content=AXE)
            r = pg.evaluate("""async () => { const r = await axe.run(document, {runOnly: {type: 'tag',
                values: ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa']}});
                return r.violations.map(v => ({id: v.id, impact: v.impact, n: v.nodes.length,
                  target: v.nodes[0] && v.nodes[0].target.join(' '), help: v.help})); }""")
            bad = [v for v in r if v["impact"] in ("serious", "critical")]
            rec(S, not bad, f"{scheme} {path}",
                "; ".join(f"{v['id']}({v['impact']},{v['n']}) {v['target']}" for v in bad[:3]))
            minor = [v for v in r if v["impact"] not in ("serious", "critical")]
            if minor:
                RESULTS.append({"section": "axe-minor", "ok": True, "label": f"{scheme} {path}",
                                "detail": "; ".join(f"{v['id']}({v['impact']})" for v in minor)})
            c.close()


def keyboard(br) -> None:
    S = "keyboard"

    def focused(pg):
        return pg.evaluate("""() => { const e = document.activeElement; if (!e) return null;
          const cs = getComputedStyle(e);
          return {tag: e.tagName, id: e.id, cls: e.className, text: (e.innerText||e.value||'').slice(0,40),
                  outline: cs.outlineStyle !== 'none' && parseFloat(cs.outlineWidth) > 0,
                  shadow: cs.boxShadow !== 'none'}; }""")

    c = new_ctx(br)
    pg = c.new_page()
    pg.goto(BASE + "/?lib=diet-and-mortality")
    settle(pg)
    pg.keyboard.press("Tab")
    f = focused(pg)
    rec(S, f and "skip" in str(f["cls"]) and (f["outline"] or f["shadow"]), "first Tab reaches a visible skip link", str(f))
    seen_input = seen_select = False
    vis_fail = []
    for _ in range(40):
        pg.keyboard.press("Tab")
        f = focused(pg)
        if not f or f["tag"] == "BODY":   # focus wrapped past the end of the page
            continue
        if not (f["outline"] or f["shadow"]):
            vis_fail.append(f"{f['tag']}#{f['id']}.{str(f['cls'])[:20]}")
        seen_input |= f["id"] == "ask-input"
        seen_select |= f["tag"] == "SELECT"
    rec(S, seen_input, "Tab reaches the search box")
    rec(S, seen_select, "Tab reaches the library switcher")
    rec(S, not vis_fail, "every Tab stop on home shows a visible focus indicator", "; ".join(vis_fail[:4]))
    pg.focus("#ask-input")
    pg.keyboard.type("alc", delay=100)
    pg.wait_for_timeout(1500)
    first = pg.locator(".results-list a").first
    first.focus()
    href = first.get_attribute("href")
    pg.keyboard.press("Enter")
    settle(pg)
    rec(S, "/gap/" in pg.url or "/paper/" in pg.url, "search → result opened with Enter only", f"href={href} url={pg.url}")
    stops = 0
    novis = []
    for _ in range(25):
        pg.keyboard.press("Tab")
        f = focused(pg)
        if f and f["tag"] != "BODY":
            stops += 1
            if not (f["outline"] or f["shadow"]):
                novis.append(f"{f['tag']}.{str(f['cls'])[:20]}")
    rec(S, stops > 5 and not novis, "gap page: Tab moves through links with visible focus", "; ".join(novis[:4]))
    c.close()
    c = new_ctx(br)
    pg = c.new_page()
    pg.goto(BASE + "/?lib=llm-calibration")
    settle(pg)
    sel = pg.locator("select").first
    sel.focus()
    sel.select_option("ml-fairness")
    pg.wait_for_load_state("networkidle")
    pg.wait_for_timeout(800)
    rec(S, "lib=ml-fairness" in pg.url, "library switch by keyboard (select + change)", pg.url)
    c.close()
    c = new_ctx(br, reduced_motion="reduce")
    pg = c.new_page()
    pg.goto(BASE + "/")
    settle(pg)
    d = pg.evaluate("""() => { const all = [...document.querySelectorAll('*')];
      let worst = 0; for (const e of all) { const cs = getComputedStyle(e);
        for (const v of [cs.transitionDuration, cs.animationDuration]) for (const x of v.split(','))
          worst = Math.max(worst, parseFloat(x) * (x.trim().endsWith('ms') ? 1 : 1000)); }
      return {reduce: matchMedia('(prefers-reduced-motion: reduce)').matches, worst_ms: worst}; }""")
    rec(S, d["reduce"] and d["worst_ms"] <= 1, "prefers-reduced-motion: no transition/animation longer than 1 ms", str(d))
    c.close()


def weight(br) -> None:
    S = "weight"
    diet = {x["lib"]: x for x in samples()}["diet-and-mortality"]
    flows = {"home": "/?lib=diet-and-mortality", "gaps": "/gaps/?lib=diet-and-mortality",
             "gap": f"/gap/{diet['gap'][0]}/?lib=diet-and-mortality",
             "paper": f"/paper/{diet['paper'][0]}/?lib=diet-and-mortality", "about": "/about/"}
    for name, path in flows.items():
        c = new_ctx(br)
        pg = c.new_page()
        reqs = []
        pg.on("requestfinished", lambda r: reqs.append(r))
        pg.goto(BASE + path)
        settle(pg)
        total = 0
        for r in reqs:
            try:
                total += r.sizes()["responseBodySize"]
            except Exception:
                pass
        RESULTS.append({"section": S, "ok": True, "label": name, "detail": f"{len(reqs)} requests, {total/1000:.0f} KB"})
        print(f"[INFO] weight {name}: {len(reqs)} requests, {total/1000:.0f} KB")
        c.close()
    # A typical visit in one browser session: home -> search -> gap page.
    c = new_ctx(br)
    pg = c.new_page()
    reqs = []
    pg.on("requestfinished", lambda r: reqs.append(r.url))
    pg.goto(BASE + "/?lib=diet-and-mortality")
    settle(pg)
    type_settled(pg, "alc")
    pg.locator(".results-list a").first.click()
    settle(pg)
    edge = [u for u in reqs if u.startswith(BASE)]
    RESULTS.append({"section": S, "ok": True, "label": "visit home→search→gap (cold cache)",
                    "detail": f"{len(edge)} same-origin requests (edge requests), {len(reqs) - len(edge)} other"})
    print(f"[INFO] visit home→search→gap: {len(edge)} edge requests, {len(reqs) - len(edge)} other")
    c.close()


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    with sync_playwright() as p:
        br = p.chromium.launch(channel="chrome", headless=True)
        for sec in args:
            if sec == "search":
                search(p)
            else:
                globals()[sec](br)
        br.close()
    with (QA / "results.jsonl").open("a") as f:
        for r in RESULTS:
            f.write(json.dumps({**r, "ts": time.time()}) + "\n")
    bad = [r for r in RESULTS if not r["ok"]]
    print(f"\nPASS={sum(r['ok'] for r in RESULTS if r['section'] not in ('weight', 'axe-minor'))} FAIL={len(bad)}")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
