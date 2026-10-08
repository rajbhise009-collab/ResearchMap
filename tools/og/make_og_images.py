"""Share images (1200x630) and app icons, rendered from the design tokens
and each library's real stats. Free; offline; uses system Chrome via
Playwright (outside frontend/).

  .venv/bin/python tools/og/make_og_images.py

Writes frontend/public/og/<slug>.png and og/default.png (each must be
< 150 KB), plus apple-touch-icon.png (180), icon-192.png, icon-512.png
rendered from frontend/public/favicon.svg. Colours are read from
frontend/app/globals.css (:root tokens); numbers from
frontend/public/data/site-facts.json; the name from site.config.json.
"""
from __future__ import annotations

import html
import json
import re
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
FE = ROOT / "frontend"
OUT = FE / "public" / "og"
MAX_BYTES = 150_000


def tokens() -> dict:
    css = (FE / "app" / "globals.css").read_text()
    root = css[css.index(":root"):]
    root = root[:root.index("}")]
    return dict(re.findall(r"--([a-z-]+):\s*(#[0-9a-fA-F]{3,8})", root))


def card(t: dict, site: str, eyebrow: str, title: str, lines: list[str], note: str | None) -> str:
    e = html.escape
    body = "".join(f"<div class='line'>{e(x)}</div>" for x in lines)
    foot = f"<div class='note'>{e(note)}</div>" if note else ""
    return f"""<!doctype html><html><head><meta charset="utf-8"><style>
  html,body{{margin:0;width:1200px;height:630px;background:{t['paper']};}}
  .c{{box-sizing:border-box;width:1200px;height:630px;padding:64px 72px;display:flex;
      flex-direction:column;border-left:18px solid {t['accent']};}}
  .site{{font:600 30px -apple-system,'Helvetica Neue',Arial,sans-serif;color:{t['accent']};
         letter-spacing:.01em}}
  .eyebrow{{margin-top:56px;font:500 24px -apple-system,'Helvetica Neue',Arial,sans-serif;
            color:{t['ink-soft']};text-transform:uppercase;letter-spacing:.08em}}
  .title{{margin-top:14px;font:600 66px/1.08 Charter,'Iowan Old Style',Georgia,serif;
          color:{t['ink-strong']};max-width:1000px}}
  .lines{{margin-top:30px}}
  .line{{font:400 28px/1.45 -apple-system,'Helvetica Neue',Arial,sans-serif;color:{t['ink']}}}
  .grow{{flex:1}}
  .note{{font:400 22px -apple-system,'Helvetica Neue',Arial,sans-serif;color:{t['ink-soft']};
         border-top:2px solid {t['accent-soft']};padding-top:16px}}
</style></head><body><div class="c"><div class="site">{e(site)}</div>
<div class="eyebrow">{e(eyebrow)}</div><div class="title">{e(title)}</div>
<div class="lines">{body}</div><div class="grow"></div>{foot}</div></body></html>"""


def main() -> int:
    t = tokens()
    site = json.loads((FE / "site.config.json").read_text())["siteName"]
    facts = json.loads((FE / "public" / "data" / "site-facts.json").read_text())["libraries"]
    OUT.mkdir(parents=True, exist_ok=True)
    jobs = []
    for lib in facts:
        read = (f"claims read from {lib['claims_read']} of {lib['papers']}"
                if lib["claims_read"] is not None else "claims read: not measured")
        lines = [f"{lib['papers']} papers · {read}",
                 f"Library built {lib['built']}" if lib["built"] else "Build date: not measured"]
        note = ("Research-literature analysis. Not dietary or medical advice."
                if lib["not_advice"] else
                "Results come only from the papers in this library. A starting point, not a verdict.")
        jobs.append((OUT / f"{lib['slug']}.png",
                     card(t, site, "Library", lib["name"], lines, note)))
    total = sum(l["papers"] for l in facts)
    jobs.append((OUT / "default.png", card(
        t, site, f"{len(facts)} libraries · {total} papers",
        "Find research questions nobody has answered yet.",
        [", ".join(l["name"] for l in facts)],
        "Results come only from the papers in the selected library. A starting point, not a verdict.")))
    svg = (FE / "public" / "favicon.svg").read_text()
    icons = [(FE / "public" / "apple-touch-icon.png", 180),
             (FE / "public" / "icon-192.png", 192), (FE / "public" / "icon-512.png", 512)]
    with sync_playwright() as p:
        br = p.chromium.launch(channel="chrome", headless=True)
        pg = br.new_page(viewport={"width": 1200, "height": 630}, device_scale_factor=1)
        for path, doc in jobs:
            pg.set_content(doc)
            pg.wait_for_timeout(150)
            pg.screenshot(path=str(path), type="png")
        for path, size in icons:
            ip = br.new_page(viewport={"width": size, "height": size}, device_scale_factor=1)
            ip.set_content(f"<html><body style='margin:0;background:{t['paper']}'>"
                           f"<div style='width:{size}px;height:{size}px'>{svg}</div></body></html>")
            ip.evaluate("""s => { const v = document.querySelector('svg');
                v.setAttribute('width', s); v.setAttribute('height', s); }""", size)
            ip.screenshot(path=str(path), type="png", clip={"x": 0, "y": 0, "width": size, "height": size})
            ip.close()
        br.close()
    # What each image says, so the consistency check can compare it with the
    # current data (frontend/scripts/consistency.mjs).
    (OUT / "manifest.json").write_text(json.dumps({
        "site_name": site,
        "libraries": {l["slug"]: {"papers": l["papers"], "claims_read": l["claims_read"],
                                  "built": l["built"]} for l in facts},
        "total_papers": total, "n_libraries": len(facts),
    }, indent=2) + "\n")
    bad = []
    for path, _ in jobs:
        n = path.stat().st_size
        print(f"{path.relative_to(ROOT)}  {n/1000:.0f} KB")
        if n >= MAX_BYTES:
            bad.append(path.name)
    for path, size in icons:
        print(f"{path.relative_to(ROOT)}  {path.stat().st_size/1000:.0f} KB ({size}px)")
    if bad:
        print("over 150 KB:", bad)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
