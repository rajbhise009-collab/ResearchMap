"""Export a static JSON snapshot of the API for the self-contained
frontend build (no running server, no hosting). Free — file-backed.

  python -m backend.app.api.export [outdir]   # default frontend/public/data
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

# Locate the repo root from this file's own path — never a hardcoded
# absolute path. Layout: backend/app/api/export.py, so parents[3] is the
# repo root. Anyone cloning this repo (or moving it after clone) needs
# this to keep working without editing the file.
REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))

from backend.app.api import data, language, search_index  # noqa: E402
from backend.app.ranking.schema import SCHEMA_VERSION  # noqa: E402

DEFAULT_OUT = REPO_ROOT / "frontend" / "public" / "data"


def slug(s: str) -> str:
    return re.sub(r"[^a-zA-Z0-9]+", "-", s).strip("-").lower()


def _wid(paper_id: str) -> str:
    return paper_id.split(":")[-1]


def _write(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj))


def export(outdir: Path = DEFAULT_OUT) -> int:
    _write(outdir / "meta.json", {"schema_version": SCHEMA_VERSION})

    # Every card carries its plain-English face alongside the raw values.
    # Developer mode shows the raw side; the consumer view never touches it.
    cards = []
    for c in data.cards():
        card = {**c.model_dump(), "slug": slug(c.id)}
        card["consumer"] = language.consumer_card(card)
        if card["consumer"].get("verdict"):
            card["verdict"] = card["consumer"]["verdict"]
        cards.append(card)
    _write(outdir / "opportunities.json", {"schema_version": SCHEMA_VERSION,
                                           "total": len(cards), "items": cards})
    for c in cards:
        _write(outdir / "opportunity" / f"{c['slug']}.json", c)

    papers = [{**p, "wid": _wid(p["paper_id"])} for p in data.paper_summaries()]
    _write(outdir / "papers.json", {"total": len(papers), "items": papers})
    details = []
    for p in papers:
        detail = data.paper_detail(p["paper_id"])
        detail["wid"] = p["wid"]
        detail["consumer"] = language.consumer_paper(detail)
        _write(outdir / "paper" / f"{p['wid']}.json", detail)
        details.append(detail)

    _write(outdir / "language.json", language.language_pack())
    _write(outdir / "search-index.json", search_index.build_index(cards, details))

    _write(outdir / "relationships.json",
           {"items": [r.model_dump() for r in data.relationships()]})
    _write(outdir / "stats.json", data.stats())
    _write(outdir / "findings.json", {"items": data.findings()})

    print(f"exported snapshot -> {outdir.relative_to(REPO_ROOT)} "
          f"({len(cards)} opportunities, {len(papers)} papers)")
    return 0


def main() -> int:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_OUT
    return export(out)


if __name__ == "__main__":
    raise SystemExit(main())
