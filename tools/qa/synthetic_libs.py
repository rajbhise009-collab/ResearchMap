"""Does the UI scale to many libraries? Build a copy of the frontend whose
data has the real libraries plus synthetic ones (8 in total), serve it, and
check every place libraries are listed or chosen.

  .venv/bin/python tools/qa/synthetic_libs.py [N_TOTAL=8]

Synthetic libraries are copies of real ones' search indexes with new slugs
and names and no cards or papers of their own (a build-only test; nothing
here is published). Checks, Chromium desktop + iPhone 13 width:
  - the library picker offers all N, and choosing the last one works
  - footer, /about and /method list all N
  - out-of-scope panel: 3 other libraries, then "All N-1 other libraries"
  - "this looks like it's about <library>": the strongest match is named
  - no horizontal scroll at 320 px; no console errors
"""
from __future__ import annotations

import functools
import http.server
import json
import os
import shutil
import socketserver
import subprocess
import sys
import threading
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
FE = ROOT / "frontend"
N_TOTAL = int(sys.argv[1]) if len(sys.argv) > 1 else 8
WORK = Path(os.environ.get("SYNTH_DIR") or "/private/tmp/researchmap-synthetic-libs")
PORT = 8796
R: list[tuple[bool, str, str]] = []


def rec(ok, label, detail=""):
    R.append((ok, label, detail))
    print(f"[{'PASS' if ok else 'FAIL'}] {label}" + (f" — {detail}" if detail and not ok else ""), flush=True)


def build_copy() -> Path:
    if WORK.exists():
        shutil.rmtree(WORK)
    shutil.copytree(FE, WORK, ignore=shutil.ignore_patterns("node_modules", ".next", "out"))
    (WORK / "node_modules").symlink_to(FE / "node_modules")
    data = WORK / "public" / "data"
    libs = json.loads((data / "libraries.json").read_text())
    facts = json.loads((data / "site-facts.json").read_text())
    lang = json.loads((data / "language.json").read_text())
    real = [l for l in libs["libraries"]]
    bases = [l for l in real if l["snapshot_path"] != "/data"] or real
    for i in range(N_TOTAL - len(real)):
        base = bases[i % len(bases)]
        slug, name = f"synthetic-{i + 1}", f"Synthetic library {i + 1} ({base['short_name']} copy)"
        src = data / base["snapshot_path"].removeprefix("/data/")
        dst = data / "library" / slug
        shutil.copytree(src, dst, ignore=shutil.ignore_patterns("paper", "opportunity"))
        (dst / "paper").mkdir()
        (dst / "opportunity").mkdir()
        o = json.loads((dst / "opportunities.json").read_text())
        o["items"] = []
        (dst / "opportunities.json").write_text(json.dumps(o))
        (dst / "papers.json").write_text(json.dumps({"total": 0, "items": []}))
        libs["libraries"].append({**base, "slug": slug, "name": name, "short_name": f"Synthetic {i + 1}",
                                  "n_papers": 0, "is_default": False, "snapshot_path": f"/data/library/{slug}"})
        bf = next(f for f in facts["libraries"] if f["slug"] == base["slug"])
        facts["libraries"].append({**bf, "slug": slug, "name": name, "short_name": f"Synthetic {i + 1}",
                                   "papers": 0, "results_total": 0, "set_aside_total": 0,
                                   "results": [{**r, "count": 0} for r in bf["results"]]})
        lang["libraries_note"]["items"].append({"slug": slug, "name": name, "n_papers": 0, "note": "Test only."})
    (data / "libraries.json").write_text(json.dumps(libs))
    (data / "site-facts.json").write_text(json.dumps(facts))
    (data / "language.json").write_text(json.dumps(lang))
    r = subprocess.run(["npx", "next", "build"], cwd=WORK, capture_output=True, text=True,
                       env={**os.environ, "NEXT_PUBLIC_SITE_URL": f"http://127.0.0.1:{PORT}"})
    if r.returncode != 0:
        raise SystemExit("synthetic build failed:\n" + (r.stdout + r.stderr)[-2000:])
    return WORK / "out"


def serve(out: Path):
    h = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(out))
    h.log_message = lambda *a, **k: None
    socketserver.TCPServer.allow_reuse_address = True
    srv = socketserver.TCPServer(("127.0.0.1", PORT), h)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def main() -> int:
    out = build_copy()
    srv = serve(out)
    base = f"http://127.0.0.1:{PORT}"
    names = [l["name"] for l in json.loads((out / "data" / "libraries.json").read_text())["libraries"]]
    rec(len(names) == N_TOTAL, f"synthetic build has {N_TOTAL} libraries", str(len(names)))
    with sync_playwright() as p:
        try:
            br = p.chromium.launch(headless=True)
        except Exception:
            br = p.chromium.launch(headless=True, channel="chrome")
        for label, vp in (("desktop", {"width": 1280, "height": 900}), ("320px", {"width": 320, "height": 800})):
            c = br.new_context(viewport=vp)
            c.route("**/_vercel/insights/**", lambda r: r.fulfill(status=200, body=""))
            pg = c.new_page()
            errs = []
            pg.on("pageerror", lambda e: errs.append(str(e)[:120]))
            pg.on("console", lambda m: errs.append(m.text[:120]) if m.type == "error" else None)
            pg.goto(base + "/")
            pg.wait_for_timeout(1500)
            opts = pg.locator(".lib-switcher select option").all_inner_texts()
            rec(len(opts) == N_TOTAL, f"{label}: picker offers {N_TOTAL} libraries", str(len(opts)))
            pg.select_option(".lib-switcher select", "synthetic-1")
            pg.wait_for_timeout(1200)
            card = pg.locator(".about-card").first.inner_text() if pg.locator(".about-card").count() else ""
            rec("lib=synthetic-1" in pg.url and "Synthetic library 1" in card,
                f"{label}: choosing a synthetic library switches the library card", f"{pg.url} | {card[:80]!r}")
            foot = pg.locator("footer").inner_text()
            rec(all(n in foot for n in names), f"{label}: footer lists all {N_TOTAL}")
            over = pg.evaluate("document.documentElement.scrollWidth - window.innerWidth")
            rec(over <= 1, f"{label}: no horizontal scroll", f"{over}px")
            for path in ("/about/", "/method/"):
                pg.goto(base + path)
                pg.wait_for_timeout(600)
                b = pg.inner_text("body")
                rec(all(n in b for n in names), f"{label}: {path} lists all {N_TOTAL}")
                over = pg.evaluate("document.documentElement.scrollWidth - window.innerWidth")
                rec(over <= 1, f"{label}: {path} no horizontal scroll", f"{over}px")
            pg.goto(base + "/?lib=llm-calibration")
            pg.wait_for_timeout(1200)
            pg.fill("#ask-input", "melanoma treatment")
            pg.press("#ask-input", "Enter")
            pg.wait_for_timeout(2500)
            shown = pg.locator("section:has(h2:text-is('Other libraries you can try')) > ul li").count()
            more = pg.locator("details.more-libs summary").inner_text() if pg.locator("details.more-libs").count() else ""
            rec(shown == 3 and more == f"All {N_TOTAL - 1} other libraries",
                f"{label}: out-of-scope panel shows 3 then 'All {N_TOTAL - 1} other libraries'", f"{shown} | {more!r}")
            pg.fill("#ask-input", "red meat and stroke")
            pg.press("#ask-input", "Enter")
            pg.wait_for_timeout(3000)
            nudge = pg.locator(".caveat:has(.cav-label:text-is('Maybe wrong library?')) strong")
            named = nudge.first.inner_text() if nudge.count() else ""
            rec(named == "Diet and all-cause mortality",
                f"{label}: suggestion names the strongest match (Diet, not a synthetic copy)", repr(named))
            rec(not errs, f"{label}: no console errors", "; ".join(errs[:3]))
            c.close()
        br.close()
    srv.shutdown()
    n_fail = sum(not ok for ok, _, _ in R)
    print(f"\nsynthetic {N_TOTAL}-library UI: PASS={len(R) - n_fail} FAIL={n_fail}")
    return 1 if n_fail else 0


if __name__ == "__main__":
    raise SystemExit(main())
