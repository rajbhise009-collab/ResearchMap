"""The curious-user hunt: browser checks against the production build.

  .venv/bin/python tools/qa/hunt.py [section ...]   # server: tools/qa/serve.py on :8765

Sections: inject url dev medical distress offensive races env keyboard network
(default: all). Fresh context per check. Prints PASS/FAIL; writes
~/ResearchMap-private/launch-qa/hunt.json.
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = os.environ.get("HUNT_BASE", "http://127.0.0.1:8765")
ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "frontend" / "public" / "data"
QA = Path.home() / "ResearchMap-private" / "launch-qa"
R: list[tuple[str, bool, str, str]] = []
NOTES: list[str] = []


def rec(sec, ok, label, detail=""):
    R.append((sec, ok, label, detail))
    print(f"[{'PASS' if ok else 'FAIL'}] {sec}: {label}" + (f" — {detail}" if detail and not ok else ""), flush=True)


def ctx(br, **kw):
    c = br.new_context(**kw)
    c.route("**/_vercel/insights/**", lambda r: r.fulfill(status=200, body=""))
    return c


def settle(pg, ms=900):
    try:
        pg.wait_for_load_state("networkidle", timeout=20000)
    except Exception:
        pass
    pg.wait_for_timeout(ms)


def guard(pg):
    """Collect dialogs (an alert() means script ran) and page errors."""
    ev = {"dialogs": [], "errors": []}
    pg.on("dialog", lambda d: (ev["dialogs"].append(d.message), d.dismiss()))
    pg.on("pageerror", lambda e: ev["errors"].append(str(e)[:120]))
    return ev


def body(pg):
    return pg.inner_text("body")


def type_q(pg, q, settle_ms=1600):
    pg.fill("#ask-input", "")
    pg.fill("#ask-input", q)
    pg.press("#ask-input", "Enter")
    pg.wait_for_timeout(settle_ms)


# ---------------------------------------------------------------------------

def inject(br):
    S = "inject"
    cases = ["<script>alert(1)</script>", '<img src=x onerror="alert(2)">',
             "**bold** [x](javascript:alert(3))", "javascript:alert(4)", "x" * 10000,
             "🔬🧪 alcohol 🍷", "الكحول والسكتة", "al​co‮hol", "a\u0000b alcohol",
             "{{constructor.constructor('alert(5)')()}}"]
    for q in cases:
        c = ctx(br)
        pg = c.new_page()
        ev = guard(pg)
        pg.goto(f"{BASE}/?lib=diet-and-mortality")
        settle(pg, 500)
        title0 = pg.title()
        type_q(pg, q)
        val = pg.input_value("#ask-input")
        echo = pg.locator(".verdict-line .query").first.inner_text() if pg.locator(".verdict-line .query").count() else ""
        injected = pg.evaluate("document.querySelectorAll('main img[src=\"x\"], main script:not([src])').length")
        ok = (not ev["dialogs"] and not ev["errors"] and len(val) <= 200 and len(echo) <= 84
              and pg.title() == title0 and injected == 0 and "‮" not in val and "\u0000" not in val)
        rec(S, ok, f"query {q[:28]!r}{'…' if len(q) > 28 else ''} → escaped, capped, no script",
            f"dialogs={ev['dialogs']} errors={ev['errors'][:1]} val={len(val)} echo={len(echo)} injected={injected}")
        c.close()
    c = ctx(br)
    pg = c.new_page()
    ev = guard(pg)
    pg.goto(f"{BASE}/?lib=diet-and-mortality&q=%3Cscript%3Ealert(9)%3C%2Fscript%3E%3Cimg%20src%3Dx%20onerror%3Dalert(8)%3E")
    settle(pg, 1800)
    rec(S, not ev["dialogs"] and not ev["errors"], "?q= with script/HTML in the URL is inert", str(ev))
    c.close()


def url(br):
    S = "url"
    paths = ["/?lib=%3Cscript%3Ealert(1)%3C%2Fscript%3E", "/?lib=../../etc/passwd", "/gaps/?lib=NOPE",
             "/gap/no-such-gap/", "/gap/%00/", "/gap/..%2f..%2fetc%2fpasswd/", "/paper/w123/",
             "/paper/W2109401990x/", "/GAPS/", "/About/", "/gaps", "/gaps//", "/data/../../etc/passwd",
             "/?" + "a=" + "x" * 6000, "/gaps/#<img src=x onerror=alert(1)>", "/findings/does-not-exist/",
             "/gap/opp-contra-diet-and-mortality-01-openalex-w2109401990-openalex-w2513212958"]
    for p in paths:
        c = ctx(br)
        pg = c.new_page()
        ev = guard(pg)
        edge = None
        try:
            resp = pg.goto(BASE + p)
            status = resp.status if resp else 0
            edge = resp.headers.get("x-vercel-error") if resp else None
            if resp and not edge and resp.status == 403 and resp.headers.get("server") == "Vercel" \
                    and resp.headers.get("x-vercel-id") and "masthead" not in (resp.text() or ""):
                edge = "FIREWALL_FORBIDDEN"
        except Exception as e:  # noqa: BLE001
            status = -1
            ev["errors"].append(str(e)[:80])
        settle(pg, 700)
        if edge and status in (400, 403):
            # Refused by the hosting platform's edge before any site code runs
            # (plain "Bad request" + request id). Not configurable on a static
            # site; checked to contain nothing internal.
            b = body(pg)
            ok = len(b) < 400 and not any(k in b.lower() for k in ("traceback", "/users/", "error:", " at "))
            rec(S, ok, f"{p[:60]} → refused by the hosting platform ({status} {edge}); no internals")
            NOTES.append(f"{p}: platform edge {status} {edge} (not the site's 404 page)")
            c.close()
            continue
        b = body(pg)
        notfound = "isn't here" in b
        ok = (len(b.strip()) > 150 and "Application error" not in b and not ev["dialogs"]
              and not ev["errors"] and pg.locator("header.masthead").count() == 1
              and (notfound or status in (200, 304)))
        rec(S, ok, f"{p[:60]}{'…' if len(p) > 60 else ''} → {'404 page' if notfound else 'page'} ({status})",
            f"len={len(b.strip())} errors={ev['errors'][:1]}")
        c.close()


def dev(br):
    S = "dev"
    markers = ["Developer mode", "Raw values", "Component scores", "Pipeline provenance",
               "Underlying JSON", "Cumulative spend", "Raw counts", "/Users/", "gemini",
               "manifest_hash", "confidence_tier"]
    for p in ["/?dev=1", "/gaps/?dev=1&lib=diet-and-mortality", "/library/?dev=1&lib=ml-fairness",
              "/gap/opp-contra-diet-and-mortality-01-openalex-w2109401990-openalex-w2513212958/?dev=1"]:
        c = ctx(br)
        pg = c.new_page()
        pg.goto(BASE + p)
        settle(pg)
        b = body(pg)
        shown = [m for m in markers if m.lower() in b.lower()]
        rec(S, not shown, f"production {p[:50]} shows no developer view", str(shown))
        c.close()


ADVICE = ["should I eat red meat", "is alcohol safe", "how much alcohol is healthy",
          "should we stop eating eggs", "is red meat bad for me", "how many drinks per day is ok",
          "can i eat processed meat", "what is a safe amount of sodium", "is coffee good for my heart",
          "recommended diet plan to lose weight"]


LEAD = "This is research literature, not medical or parenting advice."


def _distress_state(pg):
    note = pg.locator(".distress-note")
    link = pg.locator(".distress-note a[href='https://findahelpline.com']")
    return {"note": note.count() == 1 and note.first.is_visible(), "link": link.count() == 1,
            "results": pg.locator(".results-list > *").count(),
            "offer": pg.get_by_role("button", name="Want a library on this subject?").count(),
            "refused_panel": "that's not in this library" in body(pg).lower()}


def medical(br):
    S = "medical"
    for q in ADVICE:
        c = ctx(br)
        pg = c.new_page()
        pg.goto(f"{BASE}/?lib=diet-and-mortality")
        settle(pg, 500)
        type_q(pg, q)
        b = body(pg)
        refused = "that's not in this library" in b.lower()
        advice_words = [w for w in ("you should eat", "you should drink", "is safe to", "we recommend")
                        if w in b.lower()]
        ok = (LEAD in b or refused) and not advice_words and "not dietary or medical advice" in b
        rec(S, ok, f"Diet {q!r} → research-not-advice note {'(refused)' if refused else 'leads results'}",
            f"lead={LEAD in b} refused={refused} advice_words={advice_words}")
        c.close()
    for q in ("should my teen have a smartphone", "is screen time bad for my kid", "is tiktok safe for kids"):
        c = ctx(br)
        pg = c.new_page()
        pg.goto(f"{BASE}/?lib=social-media-teen-mental-health")
        settle(pg, 500)
        type_q(pg, q)
        b = body(pg)
        refused = "that's not in this library" in b.lower()
        rec(S, (LEAD in b or refused) and "not medical, parenting or mental-health advice" in b,
            f"Social media {q!r} → research-not-advice note {'(refused)' if refused else 'leads results'}",
            f"lead={LEAD in b} refused={refused}")
        c.close()


def distress(br):
    """Personal distress on every health-adjacent library (and one other):
    one calm message with a helpline link; no results; no library offer."""
    S = "distress"
    cases = [("diet-and-mortality", "i'm so depressed i can't eat"), ("diet-and-mortality", "i can't cope anymore"),
             ("diet-and-mortality", "how to kill myself"),
             ("social-media-teen-mental-health", "i'm depressed because of instagram"),
             ("social-media-teen-mental-health", "i feel hopeless and alone"),
             ("social-media-teen-mental-health", "i want to end my life"),
             ("llm-calibration", "i want to die")]
    for slug, q in cases:
        c = ctx(br)
        pg = c.new_page()
        pg.goto(f"{BASE}/?lib={slug}")
        settle(pg, 500)
        type_q(pg, q, 2200)
        st = _distress_state(pg)
        ok = st["note"] and st["link"] and st["results"] == 0 and st["offer"] == 0 and not st["refused_panel"]
        rec(S, ok, f"{slug} {q!r} → one calm message + helpline; no results, no offer", str(st))
        c.close()
    for slug, q in (("social-media-teen-mental-health", "self-harm and social media"),
                    ("social-media-teen-mental-health", "social media and adolescent depression")):
        c = ctx(br)
        pg = c.new_page()
        pg.goto(f"{BASE}/?lib={slug}")
        settle(pg, 500)
        type_q(pg, q, 2200)
        st = _distress_state(pg)
        rec(S, not st["note"] and st["results"] > 0, f"research question {q!r} → answered, no distress message",
            str(st))
        c.close()
    r = None
    try:
        import urllib.request
        r = urllib.request.urlopen(urllib.request.Request("https://findahelpline.com",
                                                          headers={"User-Agent": "ResearchMap-hunt"}), timeout=20).status
    except Exception as e:  # noqa: BLE001
        r = repr(e)[:80]
    rec(S, r == 200, "findahelpline.com resolves", str(r))


def offensive(br):
    S = "offensive"
    for q in ("porn videos free", "Jane Doe", "retard jokes", "nude photos"):
        c = ctx(br)
        pg = c.new_page()
        pg.goto(f"{BASE}/?lib=llm-calibration")
        settle(pg, 500)
        type_q(pg, q, 2200)
        b = body(pg)
        refused = "that's not in this library" in b.lower()
        offer = pg.get_by_role("button", name="Want a library on this subject?").count()
        rec(S, refused and offer == 0, f"{q!r} → refused, no library offer", f"refused={refused} offer={offer}")
        c.close()
    c = ctx(br)
    pg = c.new_page()
    pg.goto(f"{BASE}/?lib=llm-calibration")
    settle(pg, 500)
    type_q(pg, "quantum computing error correction", 2200)
    rec(S, pg.get_by_role("button", name="Want a library on this subject?").count() == 1,
        "an ordinary off-topic subject still gets the library offer")
    c.close()


def races(br):
    S = "races"
    c = ctx(br)
    pg = c.new_page()
    ev = guard(pg)
    pg.goto(f"{BASE}/?lib=diet-and-mortality")
    pg.wait_for_timeout(150)
    pg.fill("#ask-input", "alcohol")
    for slug in ("ml-fairness", "llm-calibration", "diet-and-mortality", "ml-fairness"):
        try:
            pg.select_option(".lib-switcher select", slug, timeout=3000)
        except Exception:
            pass
        pg.wait_for_timeout(120)
    settle(pg, 1200)
    lib = pg.evaluate("new URLSearchParams(location.search).get('lib')")
    card = pg.locator(".about-card dd").first.inner_text() if pg.locator(".about-card dd").count() else ""
    rec(S, not ev["errors"] and lib == "ml-fairness" and "fairness" in card.lower(),
        "rapid library switching while loading ends on the last choice", f"lib={lib} card={card!r} {ev['errors'][:1]}")
    c.close()

    gap = "/gap/opp-contra-diet-and-mortality-01-openalex-w2109401990-openalex-w2513212958/"
    c = ctx(br, accept_downloads=True)
    pg = c.new_page()
    pg.goto(BASE + gap)
    settle(pg)
    downloads = []
    pg.on("download", lambda d: downloads.append(d))
    pg.get_by_role("button", name="Download .bib").first.dblclick()
    pg.wait_for_timeout(1500)
    rec(S, len(downloads) == 1, "double-click on Download .bib gives one file", f"downloads={len(downloads)}")
    c.close()

    c = ctx(br)
    pg = c.new_page()
    pg.add_init_script("""Object.defineProperty(navigator, 'clipboard', {value: {writeText: () =>
        Promise.reject(new DOMException('denied', 'NotAllowedError'))}});""")
    ev = guard(pg)
    pg.goto(BASE + gap)
    settle(pg)
    pg.locator("summary:has-text('How to cite')").first.click()
    pg.get_by_role("button", name="Copy link").first.click()
    pg.wait_for_timeout(400)
    rec(S, "blocked copying" in body(pg) and not ev["errors"],
        "clipboard permission denied → plain message, no error", str(ev["errors"][:1]))
    c.close()

    c = ctx(br, accept_downloads=False)
    pg = c.new_page()
    ev = guard(pg)
    pg.goto(BASE + gap)
    settle(pg)
    pg.get_by_role("button", name="Download .bib").first.click()
    pg.wait_for_timeout(600)
    rec(S, not ev["errors"], "downloads blocked by the browser → no error")
    c.close()

    c = ctx(br)
    pg = c.new_page()
    ev = guard(pg)
    pg.goto(f"{BASE}/?lib=diet-and-mortality")
    settle(pg, 500)
    type_q(pg, "alcohol")
    pg.locator(".results-list a").first.click()
    settle(pg)
    pg.go_back()
    settle(pg)
    b1 = body(pg)
    pg.go_forward()
    settle(pg)
    b2 = body(pg)
    rec(S, len(b1.strip()) > 200 and len(b2.strip()) > 200 and not ev["errors"],
        "back/forward through search → result → search renders", str(ev["errors"][:1]))
    c.close()

    c = ctx(br)
    a, b = c.new_page(), c.new_page()
    a.goto(f"{BASE}/?lib=diet-and-mortality")
    b.goto(f"{BASE}/?lib=ml-fairness")
    settle(a)
    settle(b)
    a.reload()
    settle(a)
    rec(S, "Diet" in a.locator(".about-card").inner_text() and "fairness" in b.locator(".about-card").inner_text().lower(),
        "two tabs on different libraries keep their own library")
    c.close()


def env(p, br):
    S = "env"
    c = ctx(br, java_script_enabled=False)
    pg = c.new_page()
    pg.goto(f"{BASE}/")
    b = body(pg)
    rec(S, "This site needs JavaScript" in b, "JavaScript disabled → plain noscript message")
    c.close()
    for label, vp in [("320px wide", {"width": 320, "height": 700}),
                      ("200% zoom (640×400 CSS px)", {"width": 640, "height": 400}),
                      ("landscape phone 844×390", {"width": 844, "height": 390})]:
        for path in ("/?lib=diet-and-mortality", "/gaps/?lib=ml-fairness",
                     "/gap/opp-contra-diet-and-mortality-01-openalex-w2109401990-openalex-w2513212958/",
                     "/method/"):
            c = ctx(br, viewport=vp)
            pg = c.new_page()
            pg.goto(BASE + path)
            settle(pg)
            over = pg.evaluate("document.documentElement.scrollWidth - window.innerWidth")
            rec(S, over <= 1, f"{label} {path[:40]} → no horizontal scroll", f"overflow={over}px")
            c.close()
    c = ctx(br)
    pg = c.new_page()
    pg.goto(f"{BASE}/gap/opp-contra-diet-and-mortality-01-openalex-w2109401990-openalex-w2513212958/")
    settle(pg)
    pg.emulate_media(media="print")
    hidden = pg.evaluate("getComputedStyle(document.querySelector('header.masthead')).display")
    rec(S, hidden == "none" and "Red meat" in body(pg), "print stylesheet hides chrome, keeps content", f"masthead={hidden}")
    c.close()
    c = ctx(br, forced_colors="active")
    pg = c.new_page()
    ev = guard(pg)
    pg.goto(f"{BASE}/?lib=diet-and-mortality")
    settle(pg)
    pg.keyboard.press("Tab")
    pg.keyboard.press("Tab")
    out = pg.evaluate("(() => { const e = document.activeElement; const cs = getComputedStyle(e); "
                      "return cs.outlineStyle + ' ' + cs.outlineWidth; })()")
    rec(S, not ev["errors"] and "none" not in out, "forced colors: focus outline visible", out)
    c.close()
    c = ctx(br)
    pg = c.new_page()
    ev = guard(pg)
    pg.goto(f"{BASE}/?lib=diet-and-mortality")
    settle(pg)
    # Simulate page translation: wrap every text node in <font>, as browser
    # translators do, then keep using the page.
    pg.evaluate("""() => { const w = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
      const ns = []; while (w.nextNode()) ns.push(w.currentNode);
      for (const n of ns) { if (!n.nodeValue.trim() || n.parentElement.closest('script,style')) continue;
        const f = document.createElement('font'); n.parentNode.insertBefore(f, n); f.appendChild(n); } }""")
    type_q(pg, "alcohol")
    pg.locator(".about-card .lib-summary-toggle").first.click()
    pg.wait_for_timeout(300)
    rec(S, not ev["errors"] and pg.locator(".results-list > *").count() > 0,
        "page translation (text wrapped in <font>) → still works", str(ev["errors"][:1]))
    c.close()
    c = ctx(br)
    pg = c.new_page()
    ev = guard(pg)
    pg.goto(f"{BASE}/?lib=diet-and-mortality")
    settle(pg)
    c.set_offline(True)
    type_q(pg, "red meat")
    n = pg.locator(".results-list > *").count()
    c.set_offline(False)
    rec(S, n > 0 and not ev["errors"], "offline after first load → search still answers", f"results={n}")
    c.close()


def keyboard(br):
    S = "keyboard"
    c = ctx(br)
    pg = c.new_page()
    pg.goto(f"{BASE}/?lib=diet-and-mortality")
    settle(pg)
    pg.click("#ask-input")
    pg.keyboard.type("a/b")
    pg.keyboard.press("Control+k")
    pg.keyboard.press("Meta+k")
    pg.wait_for_timeout(300)
    rec(S, pg.input_value("#ask-input") == "a/b" and pg.locator(".cmdk").count() == 0,
        "'/' and Ctrl/⌘+K do nothing while typing in the search box", pg.input_value("#ask-input"))
    c.close()
    c = ctx(br)
    pg = c.new_page()
    pg.goto(f"{BASE}/gaps/?lib=llm-calibration")
    settle(pg)
    pg.focus(".filters select")
    pg.keyboard.press("/")
    pg.wait_for_timeout(200)
    rec(S, pg.locator(".cmdk").count() == 0, "'/' does nothing while a select has focus")
    pg.locator("main h1").first.click()
    pg.keyboard.press("/")
    pg.wait_for_timeout(300)
    opened = pg.locator(".cmdk").count() == 1
    pg.keyboard.press("Escape")
    pg.wait_for_timeout(300)
    rec(S, opened and pg.locator(".cmdk").count() == 0, "'/' opens the palette on a page without a search box; Escape closes it")
    c.close()
    c = ctx(br)
    pg = c.new_page()
    pg.goto(f"{BASE}/gap/opp-contra-diet-and-mortality-01-openalex-w2109401990-openalex-w2513212958/")
    settle(pg)
    pg.locator(".lib-switch-notice, .crumb").first.focus() if pg.locator(".crumb").count() else None
    pg.keyboard.press("Control+k")
    pg.wait_for_timeout(300)
    open1 = pg.locator(".cmdk").count() == 1
    seen = set()
    for _ in range(12):
        pg.keyboard.press("Tab")
        seen.add(pg.evaluate("document.activeElement && document.activeElement.className"))
    pg.keyboard.press("Escape")
    pg.wait_for_timeout(300)
    back = pg.evaluate("document.activeElement && document.activeElement.className")
    rec(S, open1 and pg.locator(".cmdk").count() == 0 and "crumb" in str(back),
        "Ctrl+K opens, Tab is not trapped, Escape closes and returns focus", f"back={back!r}")
    c.close()


def network(br):
    S = "network"
    hosts = set()
    c = ctx(br)
    pg = c.new_page()
    pg.on("request", lambda r: hosts.add(r.url.split("/")[2]))
    for path in ("/?lib=diet-and-mortality", "/gaps/?lib=ml-fairness", "/library/?lib=llm-calibration",
                 "/gap/opp-contra-diet-and-mortality-01-openalex-w2109401990-openalex-w2513212958/",
                 "/paper/W2109401990/", "/method/", "/about/"):
        pg.goto(BASE + path)
        settle(pg)
    pg.goto(f"{BASE}/?lib=llm-calibration")
    settle(pg)
    type_q(pg, "quantum computing", 2000)
    b = pg.get_by_role("button", name="Want a library on this subject?")
    if b.count():
        b.first.click()
        pg.wait_for_timeout(1500)
    rec(S, hosts == {BASE.split("/")[2]}, "every runtime request goes to the site itself (no paid or rate-limited API)",
        str(sorted(hosts)))
    c.close()


def main() -> int:
    secs = sys.argv[1:] or ["inject", "url", "dev", "medical", "distress", "offensive", "races", "env", "keyboard",
                            "network"]
    with sync_playwright() as p:
        engine = os.environ.get("HUNT_ENGINE", "chromium")
        try:
            br = getattr(p, engine).launch(headless=True)
        except Exception:
            if engine != "chromium":
                raise
            br = p.chromium.launch(channel="chrome", headless=True)   # installed Chrome
        for s in secs:
            env(p, br) if s == "env" else globals()[s](br)
        br.close()
    QA.mkdir(parents=True, exist_ok=True)
    (QA / "hunt.json").write_text(json.dumps([{"section": a, "ok": b, "label": c, "detail": d}
                                              for a, b, c, d in R], indent=2))
    for n in NOTES:
        print("NOTE", n)
    print(f"\nPASS={sum(ok for _, ok, _, _ in R)} FAIL={sum(not ok for _, ok, _, _ in R)}")
    return 0 if all(ok for _, ok, _, _ in R) else 1


if __name__ == "__main__":
    raise SystemExit(main())
