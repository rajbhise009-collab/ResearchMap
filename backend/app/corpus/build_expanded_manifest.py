"""Build the EXPANDED domain-corpus manifest (original 34 + snowball).

Merges the existing hand-labelled domain corpus (34) with the snowball
candidates (166) into one self-contained manifest: each record carries
everything extraction needs (title, abstract, doi, centrality,
provenance) so the batch runner does not depend on the raw OpenAlex
dump for the new papers. Retrieves arXiv full text for every paper
(idempotent), flags abstract_only, and cross-dedups the two sets by DOI
then normalized (title, year) — failure mode #7, preprint-vs-published
duplication across sources.

Free (arXiv only). Output: data/live_samples/expanded_corpus_manifest.json.
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
from backend.app.ingestion.normalizer import deduplicate, normalize_title  # noqa: E402
from backend.app.models import Paper, Source  # noqa: E402

SNOWBALL = REPO_ROOT / "data" / "live_samples" / "snowball_candidates.json"
OUT = REPO_ROOT / "data" / "live_samples" / "expanded_corpus_manifest.json"


def _paper_from_snowball(rec: dict) -> Paper:
    native = rec["native_id"]
    return Paper(
        id=f"openalex:{native}",
        source=Source.OPENALEX,
        source_id=native,
        doi=(rec.get("doi") or "").lower().removeprefix("https://doi.org/") or None,
        title=rec.get("title") or "Untitled",
        abstract=rec.get("abstract"),
        year=rec.get("year"),
    )


AUTHORS_FULL = REPO_ROOT / "data" / "reasoning" / "authors_full.json"


def _authors_for(native: str) -> list[str]:
    if AUTHORS_FULL.exists():
        return json.loads(AUTHORS_FULL.read_text()).get(native, [])
    return []


def _collect_papers() -> list[dict]:
    """Return unified list of {paper, centrality, provenance} for all
    corpus papers (original + snowball). Author lists are populated so the
    full dedup (pass #4, arXiv-DOI-aware, shared-author-guarded) can fire."""
    out: list[dict] = []
    entries, _excl = domain_corpus()
    for e in entries:
        p = e.paper
        if not p.authors:
            p = p.model_copy(update={"authors": _authors_for(p.source_id)})
        out.append({"paper": p, "centrality": e.domain_centrality,
                    "provenance": "original"})
    snow = json.loads(SNOWBALL.read_text())
    for rec in snow["records"]:
        p = _paper_from_snowball(rec)
        p = p.model_copy(update={"authors": _authors_for(p.source_id)})
        out.append({"paper": p, "centrality": rec["domain_centrality"],
                    "provenance": "snowball"})
    return out


def _manifest_hash(records: list[dict]) -> str:
    key = sorted(
        f"{r['paper_id']}|{r['input_source']}|{r['domain_centrality']}|{r['provenance']}"
        for r in records
    )
    return hashlib.sha256("\n".join(key).encode()).hexdigest()[:16]


def build() -> dict:
    papers = _collect_papers()
    records: list[dict] = []
    exclusions: list[dict] = []

    # FULL 4-pass ingestion dedup (DOI, title+year+author, cross-year,
    # arXiv-DOI-aware) — replaces the old 2-pass (DOI, title+YEAR) that
    # missed cross-year preprint/published pairs (failure mode #7). Author
    # lists were populated in _collect_papers so pass #4 can fire.
    by_id = {item["paper"].id: item for item in papers}
    survivors = deduplicate([item["paper"] for item in papers])
    survivor_ids = {p.id for p in survivors}
    merged = {p.id: list(p.merged_from) for p in survivors if p.merged_from}
    collapses = [{"paper_id": lost, "dup_of": sid, "by": "full_4pass_dedup"}
                 for sid, losers in merged.items() for lost in losers]
    papers = [by_id[p.id] for p in survivors]

    with httpx.Client(
        timeout=httpx.Timeout(60.0, connect=10.0),
        headers={"User-Agent": "ResearchMap/0.1 corpus"},
    ) as client:
        for item in papers:
            paper = item["paper"]
            res = retrieve_fulltext(paper, client=client, use_cache=True)
            if not res.from_cache and res.reason == "retrieved":
                time.sleep(0.5)
            has_ft = bool(res.fulltext)
            abstract_only = not has_ft
            if abstract_only and not (paper.abstract or "").strip():
                exclusions.append({"paper_id": paper.id,
                                   "reason": "no_fulltext_no_abstract",
                                   "provenance": item["provenance"]})
                continue

            records.append({
                "openalex_id": f"https://openalex.org/{paper.source_id}",
                "paper_id": paper.id,
                "title": paper.title,
                "year": paper.year,
                "doi": paper.doi,
                "abstract": paper.abstract,
                "domain_centrality": item["centrality"],
                "provenance": item["provenance"],
                "input_source": "fulltext" if has_ft else "abstract",
                "abstract_only": abstract_only,
                "arxiv_id": res.arxiv_id,
                "fulltext_reason": res.reason,
                "fulltext_tokens": estimate_tokens(res.fulltext) if has_ft else None,
            })

    def _c(pred):
        return sum(1 for r in records if pred(r))

    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "corpus_size": len(records),
        "domain_centrality": {
            "core": _c(lambda r: r["domain_centrality"] == "core"),
            "peripheral": _c(lambda r: r["domain_centrality"] == "peripheral"),
        },
        "provenance": {
            "original": _c(lambda r: r["provenance"] == "original"),
            "snowball": _c(lambda r: r["provenance"] == "snowball"),
        },
        "input_source": {
            "fulltext": _c(lambda r: r["input_source"] == "fulltext"),
            "abstract_only": _c(lambda r: r["abstract_only"]),
        },
        "fulltext_coverage_pct": round(
            100 * _c(lambda r: r["input_source"] == "fulltext") / len(records), 1
        ) if records else 0.0,
        "dedup_collapses": len(collapses),
        "collapse_detail": collapses,
        "excluded_count": len(exclusions),
        "exclusions": exclusions,
        "manifest_hash": _manifest_hash(records),
        "records": records,
    }
    return manifest


def main() -> int:
    m = build()
    OUT.write_text(json.dumps(m, indent=2))
    print(f"corpus: {m['corpus_size']} "
          f"(core={m['domain_centrality']['core']}, "
          f"peripheral={m['domain_centrality']['peripheral']})")
    print(f"provenance: original={m['provenance']['original']}, "
          f"snowball={m['provenance']['snowball']}")
    print(f"input source: fulltext={m['input_source']['fulltext']}, "
          f"abstract_only={m['input_source']['abstract_only']} "
          f"({m['fulltext_coverage_pct']}% full text)")
    print(f"dedup collapses: {m['dedup_collapses']} | excluded: {m['excluded_count']}")
    print(f"manifest_hash: {m['manifest_hash']}")
    print(f"wrote {OUT.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
