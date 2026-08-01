"""Build the domain-corpus manifest: select, retrieve full text, flag.

Free (arXiv only — no Gemini spend). For every domain paper (core +
peripheral) it attempts arXiv full-text retrieval (idempotent — cached
hits are reused), decides the per-paper `input_source`
(fulltext where available, else abstract), flags `abstract_only`, and
records every excluded label row with a reason.

Output: data/live_samples/domain_corpus_manifest.json — the single
source of truth the batch runner, dry-run, and CORPUS_REPORT consume.
A paper that has neither full text NOR a usable abstract is moved to
`exclusions` (nothing to extract from).
"""

from __future__ import annotations

import hashlib
import json
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]  # backend/app/corpus/x.py
sys.path.insert(0, str(REPO_ROOT))

import httpx  # noqa: E402

from backend.app.corpus.domain_corpus import domain_corpus  # noqa: E402
from backend.app.ingestion.fulltext import (  # noqa: E402
    estimate_tokens,
    retrieve_fulltext,
)

MANIFEST = REPO_ROOT / "data" / "live_samples" / "domain_corpus_manifest.json"


def manifest_hash(records: list[dict]) -> str:
    """Stable hash over the corpus composition (paper id + input_source +
    centrality), order-independent."""
    key = sorted(
        f"{r['paper_id']}|{r['input_source']}|{r['domain_centrality']}"
        for r in records
    )
    return hashlib.sha256("\n".join(key).encode()).hexdigest()[:16]


def build(*, retrieve: bool = True) -> dict:
    entries, exclusions = domain_corpus()

    records: list[dict] = []
    with httpx.Client(
        timeout=httpx.Timeout(60.0, connect=10.0),
        headers={"User-Agent": "ResearchMap/0.1 corpus"},
    ) as client:
        for e in entries:
            res = retrieve_fulltext(e.paper, client=client, use_cache=True)
            if res.abstract_only and retrieve is False:
                pass
            # Politeness pause only on an actual network fetch.
            if not res.from_cache and res.reason == "retrieved":
                time.sleep(1.0)

            has_ft = bool(res.fulltext)
            input_source = "fulltext" if has_ft else "abstract"
            abstract_only = not has_ft
            # A paper with no full text AND no abstract can't be extracted.
            if abstract_only and not (e.paper.abstract or "").strip():
                exclusions.append({
                    "openalex_id": e.openalex_id,
                    "reason": "no_fulltext_no_abstract",
                })
                continue

            ft_tokens = estimate_tokens(res.fulltext) if has_ft else None
            records.append({
                "openalex_id": e.openalex_id,
                "paper_id": e.paper.id,
                "title": e.paper.title,
                "venue": e.paper.venue,
                "year": e.paper.year,
                "domain_centrality": e.domain_centrality,
                "abstract_source": e.row.get("abstract_source"),
                "input_source": input_source,
                "abstract_only": abstract_only,
                "arxiv_id": res.arxiv_id,
                "fulltext_reason": res.reason,
                "fulltext_tokens": ft_tokens,
            })

    core = sum(1 for r in records if r["domain_centrality"] == "core")
    periph = sum(1 for r in records if r["domain_centrality"] == "peripheral")
    ft = sum(1 for r in records if r["input_source"] == "fulltext")
    ab = sum(1 for r in records if r["abstract_only"])
    src_contrib = Counter(r["abstract_source"] for r in records)

    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "corpus_size": len(records),
        "domain_centrality": {"core": core, "peripheral": periph},
        "input_source": {"fulltext": ft, "abstract_only": ab},
        "fulltext_coverage_pct": round(100 * ft / len(records), 1) if records else 0.0,
        "abstract_source_contribution": dict(src_contrib),
        "excluded_count": len(exclusions),
        "exclusions": exclusions,
        "manifest_hash": manifest_hash(records),
        "records": records,
    }
    return manifest


def main() -> int:
    manifest = build()
    MANIFEST.write_text(json.dumps(manifest, indent=2))
    print(f"corpus: {manifest['corpus_size']} papers "
          f"(core={manifest['domain_centrality']['core']}, "
          f"peripheral={manifest['domain_centrality']['peripheral']})")
    print(f"input source: fulltext={manifest['input_source']['fulltext']}, "
          f"abstract_only={manifest['input_source']['abstract_only']} "
          f"({manifest['fulltext_coverage_pct']}% full text)")
    print(f"excluded: {manifest['excluded_count']} {manifest['exclusions']}")
    print(f"per-source: {manifest['abstract_source_contribution']}")
    print(f"manifest_hash: {manifest['manifest_hash']}")
    print(f"written to {MANIFEST.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
