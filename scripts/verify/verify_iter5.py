"""Iteration-5 verification against the production static build.

  (cd frontend && npm run build)                       # no ENABLE_DEV
  python -m http.server 8765 --bind 127.0.0.1 -d frontend/out &
  .venv/bin/python scripts/verify/verify_iter5.py <build-sha>

Fresh browser context per check; library via ?lib=<slug>. Settled state:
1500 ms after the last keystroke. Expected text is read from the shipped
JSON and the denylist from backend/tests/api/test_public_claims.py, never
hard-coded here.
"""
from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

from playwright.sync_api import sync_playwright

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
from backend.tests.api.test_public_claims import DENYLIST  # noqa: E402

BASE = "http://127.0.0.1:8765"
DATA = REPO / "frontend" / "public" / "data"
SHOTS = REPO / "docs" / "review" / "screenshots"
REPORT = REPO / "docs" / "review" / "verification-iteration5.md"
LIBS = ["llm-calibration", "diet-and-mortality", "ml-fairness"]
SHOTS.mkdir(parents=True, exist_ok=True)
results: list[tuple[bool, str]] = []


def rec(ok: bool, label: str, detail: str = "") -> None:
    results.append((ok, f"[{'PASS' if ok else 'FAIL'}] {label}"
                    + (f" — {detail}" if detail and not ok else "")))
    print(results[-1][1])


def body(pg) -> str:
    return pg.inner_text("body").lower()


def refusal(pg) -> bool:
    return "that's not in this library" in body(pg)


def edge(pg) -> bool:
    return "at the edge of this library" in body(pg)


def open_lib(pg, slug: str, path: str = "/") -> None:
    pg.goto(f"{BASE}{path}?lib={slug}", wait_until="networkidle")
    pg.wait_for_timeout(700)


def type_settled(pg, sel: str, text: str) -> None:
    pg.wait_for_selector(sel)
    pg.fill(sel, "")
    pg.type(sel, text, delay=120)
    pg.wait_for_timeout(1500)


def main() -> int:
    sha = sys.argv[1] if len(sys.argv) > 1 else "unknown"
    findings = json.loads((DATA / "findings.json").read_text())["items"]
    lang = {s: json.loads(((DATA if s == "llm-calibration" else DATA / "library" / s)
                           / "language.json").read_text()) for s in LIBS}
    with sync_playwright() as p:
        br = p.chromium.launch(channel="chrome", headless=True)

        # ---- Findings pages render, on every library, with no denylisted claim
        for slug in LIBS:
            for f in findings:
                c = br.new_context()
                pg = c.new_page()
                open_lib(pg, slug, f"/findings/{f['slug']}/")
                b = body(pg)
                first_line = next((ln.strip().lstrip("#").strip() for ln in f["markdown"].splitlines()
                                   if ln.strip().startswith("# ")), f["title"]).lower()
                hits = [d for d in DENYLIST if d.lower() in b]
                ok = (first_line[:40] in b and len(b) > 500 and not hits
                      and "<!-- gen" not in b and "gen:" not in b)
                rec(ok, f"{slug}: /findings/{f['slug']} renders, no denylisted phrase",
                    f"hits={hits} title_found={first_line[:40] in b} len={len(b)}")
                if f["slug"] == "multi-domain":
                    rec("why zero? not established" in b and "(a)" in b and "(c)" in b,
                        f"{slug}: multi-domain shows 'Why zero? Not established' with hypotheses (a)-(c)")
                    if slug == "ml-fairness":
                        pg.screenshot(path=str(SHOTS / "iter5-findings-multi-domain.png"), full_page=True)
                c.close()

        # ---- Footer notes follow the library and carry the corrected copy
        for slug in LIBS:
            c = br.new_context()
            pg = c.new_page()
            open_lib(pg, slug)
            b = body(pg)
            notes = [i["note"].lower() for i in lang[slug]["libraries_note"]["items"]]
            rec(all(n[:60] in b for n in notes) and "saturated fat" not in b
                and "papers here disagree about which incompatibility" not in b,
                f"{slug}: footer shows corrected library notes")
            c.close()

        # ---- Regression: settled typing
        for slug, q, must in [("diet-and-mortality", "alc", "alcohol"),
                              ("ml-fairness", "fair", "fair"),
                              ("llm-calibration", "halluc", "halluc")]:
            c = br.new_context()
            pg = c.new_page()
            open_lib(pg, slug)
            type_settled(pg, "#ask-input", q)
            b = body(pg)
            n_results = pg.locator(".results-list > *").count()
            rec(n_results > 0 and must in b and not refusal(pg) and not edge(pg),
                f"settled: {slug} '{q}' → {n_results} results present, no banner", b[:200])
            if slug == "diet-and-mortality":
                pg.screenshot(path=str(SHOTS / "iter5-diet-alc.png"), full_page=True)
            c.close()

        for slug in LIBS:
            c = br.new_context()
            pg = c.new_page()
            open_lib(pg, slug)
            type_settled(pg, "#ask-input", "melanoma treatment")
            rec(refusal(pg) and not edge(pg),
                f"settled: {slug} 'melanoma treatment' refuses", body(pg)[:200])
            if slug == "ml-fairness":
                pg.screenshot(path=str(SHOTS / "iter5-mlf-melanoma.png"), full_page=True)
            c.close()

        # ---- Spend figures never shown to consumers
        for slug in LIBS:
            c = br.new_context()
            pg = c.new_page()
            open_lib(pg, slug, "/library/")
            b = body(pg)
            rec("spend_to_date" not in b and "spend ledger" not in b.replace("spending ledger", ""),
                f"{slug}: /library shows no spend figure")
            c.close()
        br.close()

    n_ok = sum(ok for ok, _ in results)
    lines = [f"# Iteration-5 verification — {n_ok}/{len(results)} pass", "",
             f"- Date: {date.today().isoformat()}",
             f"- Build sha (HEAD of the tree the static build was made from): `{sha}`",
             "- Production static build (`npm run build`, no ENABLE_DEV), served from frontend/out.",
             "- Playwright + system Chrome; fresh context per check; library via ?lib=<slug>.",
             "- Settled state: 1500 ms after the last keystroke.",
             "- Denylist imported from backend/tests/api/test_public_claims.py.",
             "- Screenshots: `docs/review/screenshots/iter5-*.png`.", ""]
    lines += [ln for _, ln in results]
    REPORT.write_text("\n".join(lines) + "\n")
    print(f"\nPASS={n_ok} FAIL={len(results) - n_ok}")
    return 0 if n_ok == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
