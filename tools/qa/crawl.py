"""Crawl every page in the built sitemap (rendered, so client-side links
count), check every internal link, and sample external DOI/OpenAlex links.

  .venv/bin/python tools/qa/crawl.py      # server: tools/qa/serve.py on :8765

Internal links fail the run if broken. External links are only reported
(40 sampled, one request per second, plain GET with a descriptive UA).
"""
import json
import random
import re
import time
import urllib.parse
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "frontend" / "out"
BASE = "http://127.0.0.1:8765"
QA = Path.home() / "ResearchMap-private" / "launch-qa"
LIBS = {l["slug"] for l in json.loads((ROOT / "frontend/public/data/libraries.json").read_text())["libraries"]}


def status(url: str) -> int:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "ResearchMap-linkcheck/1.0 (launch QA)"})
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code
    except Exception:
        return -1


def main() -> int:
    locs = re.findall(r"<loc>([^<]+)</loc>", (OUT / "sitemap.xml").read_text())
    paths = [urllib.parse.urlparse(u).path for u in locs]
    internal: dict[str, set[str]] = {}
    external: set[str] = set()
    with sync_playwright() as p:
        br = p.chromium.launch(channel="chrome", headless=True)
        ctx = br.new_context()
        ctx.route("**/_vercel/insights/**", lambda r: r.fulfill(status=200, body=""))
        pg = ctx.new_page()
        for i, path in enumerate(paths):
            pg.goto(BASE + path)
            pg.wait_for_load_state("networkidle")
            pg.wait_for_timeout(250)
            for href in pg.eval_on_selector_all("a[href]", "els => els.map(e => e.href)"):
                u = urllib.parse.urlparse(href)
                if u.scheme in ("http", "https") and u.netloc == "127.0.0.1:8765":
                    internal.setdefault(href.split("#")[0], set()).add(path)
                elif u.scheme in ("http", "https"):
                    external.add(href)
            if i % 50 == 0:
                print(f"rendered {i + 1}/{len(paths)}", flush=True)
        br.close()
    broken = []
    for href, sources in sorted(internal.items()):
        u = urllib.parse.urlparse(href)
        code = status(href)
        lib = urllib.parse.parse_qs(u.query).get("lib", [None])[0]
        if code != 200 or (lib is not None and lib not in LIBS):
            broken.append({"href": href, "status": code, "lib_ok": lib is None or lib in LIBS,
                           "from": sorted(sources)[:3]})
    ext = sorted(u for u in external if "doi.org" in u or "openalex.org" in u)
    random.Random(42).shuffle(ext)
    ext_results = []
    for u in ext[:40]:
        ext_results.append({"url": u, "status": status(u)})
        time.sleep(1.0)
    report = {"pages_rendered": len(paths), "internal_links": len(internal), "internal_broken": broken,
              "external_total": len(external), "external_doi_openalex": len(ext),
              "external_sampled": ext_results,
              "external_not_ok": [r for r in ext_results if not (200 <= r["status"] < 400)]}
    (QA / "crawl.json").write_text(json.dumps(report, indent=2))
    print(f"pages {len(paths)} · internal links {len(internal)} · broken {len(broken)} · "
          f"external {len(external)} (doi/openalex {len(ext)}) · sampled 40 · not OK "
          f"{len(report['external_not_ok'])}")
    for b in broken[:10]:
        print("BROKEN", b)
    for r in report["external_not_ok"]:
        print("EXTERNAL", r["status"], r["url"])
    return 1 if broken else 0


if __name__ == "__main__":
    raise SystemExit(main())
