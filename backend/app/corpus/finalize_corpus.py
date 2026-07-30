"""Finalize the corpus: relabel (corrected rubric) + full 4-pass dedup,
then filter every downstream store to the surviving/in-domain paper set so
no orphaned references remain. Operates on the EXISTING expanded manifest
(preserving OA-recovery metadata); the same corrections are wired into
build_expanded_manifest.py for future rebuilds.

Free — no LLM, no paid calls. Writes:
  data/live_samples/expanded_corpus_manifest.json  (corrected; .bak kept)
and filters data/relationships/{claim_embeddings,future_work_addressals,
citation_edges,claim_relationships,future_work_*}.
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

REPO_ROOT = Path("/Users/rajbhise/Downloads/claudecode/ResearchMap")
sys.path.insert(0, str(REPO_ROOT))

import numpy as np  # noqa: E402

from backend.app.corpus.heuristic_label import classify  # noqa: E402
from backend.app.models import Paper, Source  # noqa: E402
from backend.app.ingestion.normalizer import deduplicate  # noqa: E402

MAN = REPO_ROOT / "data" / "live_samples" / "expanded_corpus_manifest.json"
SNOW = REPO_ROOT / "data" / "live_samples" / "snowball_candidates.json"
AUTHORS = REPO_ROOT / "data" / "reasoning" / "authors_full.json"
REL = REPO_ROOT / "data" / "relationships"

VERIFY_KEEP = {"openalex:W2514278201"}  # #14, hand-verified in-domain (selective prediction)


def _relabel(rec: dict, snow_reason: dict[str, str]) -> bool:
    """True = keep (in-domain). Original hand-labelled papers are trusted;
    snowball papers are re-judged under the corrected rubric."""
    if rec["paper_id"] in VERIFY_KEEP:
        return True
    if rec.get("provenance") == "original":
        return True  # hand-labelled — trusted
    reason = (snow_reason.get(rec["paper_id"].split(":")[-1], "") or "").lower()
    if "allowlist" in reason and "arxiv" not in reason:
        return True  # real venue (not arXiv) — unaffected by the fix
    label, _ = classify({"title": rec.get("title")}, abstract_text=rec.get("abstract"))
    return label == "on-domain"


def main() -> int:
    man = json.loads(MAN.read_text())
    records = man["records"]
    snow_reason = {r["native_id"]: r.get("label_reason", "")
                   for r in json.loads(SNOW.read_text())["records"]}
    authors = json.loads(AUTHORS.read_text()) if AUTHORS.exists() else {}

    n0 = len(records)
    kept = [r for r in records if _relabel(r, snow_reason)]
    excluded_relabel = [r["paper_id"] for r in records if r not in kept]

    # Full 4-pass dedup on the kept set (authors populated for pass #4).
    papers = [Paper(id=r["paper_id"], source=Source.OPENALEX,
                    source_id=r["paper_id"].split(":")[-1], doi=r.get("doi"),
                    title=r.get("title") or "Untitled", year=r.get("year"),
                    authors=authors.get(r["paper_id"].split(":")[-1], []))
              for r in kept]
    survivors = deduplicate(papers)
    survivor_ids = {p.id for p in survivors}
    merged = {p.id: list(p.merged_from) for p in survivors if p.merged_from}
    dropped_dup = {lost for losers in merged.values() for lost in losers}

    final = [r for r in kept if r["paper_id"] in survivor_ids]
    final_ids = {r["paper_id"] for r in final}

    # --- rewrite manifest (preserve every field) ---
    shutil.copy2(MAN, MAN.with_suffix(".json.bak"))
    from collections import Counter
    man["records"] = final
    man["corpus_size"] = len(final)
    man["domain_centrality"] = dict(Counter(r["domain_centrality"] for r in final))
    man["provenance"] = dict(Counter(r["provenance"] for r in final))
    man["input_source"] = {
        "fulltext": sum(1 for r in final if r["input_source"] == "fulltext"),
        "abstract_only": sum(1 for r in final if r["abstract_only"]),
    }
    man["finalize"] = {
        "before": n0, "after_relabel": len(kept), "after_dedup": len(final),
        "excluded_by_relabel": excluded_relabel,
        "dedup_merged": merged,
    }
    MAN.write_text(json.dumps(man, indent=2))

    # --- filter downstream stores to final_ids (drop orphaned refs) ---
    def _paper_of_claim(cid, claim_paper):
        return claim_paper.get(cid)

    stats = {}
    # claim embeddings (jsonl meta + npy vectors, same order)
    emeta = REL / "claim_embeddings.jsonl"
    evec = REL / "claim_embeddings.npy"
    if emeta.exists():
        rows = [json.loads(l) for l in emeta.read_text().splitlines() if l.strip()]
        vecs = np.load(evec)
        keep_idx = [i for i, r in enumerate(rows) if r["paper_id"] in final_ids]
        emeta.write_text("\n".join(json.dumps(rows[i]) for i in keep_idx) + "\n")
        np.save(evec, vecs[keep_idx])
        stats["claim_embeddings"] = f"{len(rows)}->{len(keep_idx)}"

    # future-work vectors + ids (drop items whose source paper is gone)
    fwi = REL / "future_work_ids.json"
    fwv = REL / "future_work.npy"
    if fwi.exists():
        fw_ids = json.loads(fwi.read_text())
        # fw id encodes source paper: 'openalex:Wxxxx:...'; source paper = first two segs
        def _src(fwid):
            parts = fwid.split(":")
            return ":".join(parts[:2]) if len(parts) >= 2 else fwid
        vecs = np.load(fwv)
        keep = [i for i, fid in enumerate(fw_ids) if _src(fid) in final_ids]
        fwi.write_text(json.dumps([fw_ids[i] for i in keep]))
        np.save(fwv, vecs[keep])
        stats["future_work_vectors"] = f"{len(fw_ids)}->{len(keep)}"

    # addressals (drop refs to dropped papers)
    for name in ("future_work_addressals.jsonl", "claim_relationships.jsonl"):
        f = REL / name
        if not f.exists():
            continue
        rows = [json.loads(l) for l in f.read_text().splitlines() if l.strip()]
        kept_rows = [r for r in rows
                     if r.get("from_paper_id", "x") in final_ids
                     and r.get("to_paper_id", "x") in final_ids]
        f.write_text("\n".join(json.dumps(r) for r in kept_rows) + ("\n" if kept_rows else ""))
        stats[name] = f"{len(rows)}->{len(kept_rows)}"

    # citation edges
    ce = REL / "citation_edges.jsonl"
    if ce.exists():
        rows = [json.loads(l) for l in ce.read_text().splitlines() if l.strip()]
        kept_rows = [r for r in rows if r["from_paper_id"] in final_ids and r["to_paper_id"] in final_ids]
        ce.write_text("\n".join(json.dumps(r) for r in kept_rows) + "\n")
        stats["citation_edges"] = f"{len(rows)}->{len(kept_rows)}"

    print(f"corpus: {n0} -> relabel {len(kept)} -> dedup {len(final)} unique papers")
    print(f"excluded by relabel: {len(excluded_relabel)}")
    print(f"dedup merged (survivor <- losers): {merged}")
    print(f"#14 (W2514278201) in final: {'openalex:W2514278201' in final_ids}")
    print(f"centrality: {man['domain_centrality']} | provenance: {man['provenance']}")
    print(f"input_source: {man['input_source']}")
    print(f"downstream filtered: {stats}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
