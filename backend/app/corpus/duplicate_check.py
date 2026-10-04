"""Duplicate-paper check across the three libraries — free, reads files only.

  python -m backend.app.corpus.duplicate_check     # writes data/duplicate_check.json

For each library:
  1. Replays the project's 4-pass `normalizer.deduplicate()` on the published
     corpus (diet / fairness: Papers rebuilt from the raw OpenAlex records in
     snowball.json, which carry authors; llm-calibration: manifest records +
     data/reasoning/authors_full.json). Any collapse here is a pair the
     4-pass dedup WOULD have merged if it had been run.
  2. Flags author-independent candidates for hand review: same normalized
     DOI; same normalized title; title similarity >= TITLE_SIM; or one arXiv
     DOI and one non-arXiv DOI with title similarity >= ARXIV_SIM.
Also classifies every "duplicate" verdict in the diet hand audit: same two
papers counted twice (different claims), or two copies of one work.
Does not change any corpus.
"""

from __future__ import annotations

import json
import sys
from difflib import SequenceMatcher
from itertools import combinations
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))

from backend.app.ingestion.normalizer import (  # noqa: E402
    _is_arxiv_doi, deduplicate, from_openalex, normalize_doi, normalize_title,
)
from backend.app.models import Paper  # noqa: E402

DATA = REPO_ROOT / "data"
OUT = DATA / "duplicate_check.json"
TITLE_SIM = 0.85
ARXIV_SIM = 0.75


def _wid(x: str) -> str:
    return x.rsplit("/", 1)[-1].split(":")[-1]


def _new_library_papers(slug: str) -> list[Paper]:
    pre = json.loads((DATA / "domains" / slug / "prelabelled.json").read_text())
    keep = {e["wid"] for e in pre["entries"]}
    snow = json.loads((DATA / "domains" / slug / "snowball.json").read_text())
    return [from_openalex(r) for r in snow["records"] if _wid(r.get("id", "")) in keep]


def _llm_cal_papers() -> list[Paper]:
    m = json.loads((DATA / "live_samples" / "expanded_corpus_manifest.json").read_text())
    authors = json.loads((DATA / "reasoning" / "authors_full.json").read_text())
    out = []
    for r in m["records"]:
        w = _wid(r["paper_id"])
        out.append(Paper.model_construct(
            id=f"openalex:{w}", source="openalex", source_id=w,
            doi=normalize_doi(r.get("doi")), title=r.get("title") or "",
            abstract=None, year=r.get("year"), authors=authors.get(w, []),
            venue=None, citations_out=[], citations_in_count=0,
            oa_fulltext_available=False, fulltext=None, merged_from=[]))
    return out


def _sim(a: str, b: str) -> float:
    return SequenceMatcher(None, normalize_title(a), normalize_title(b)).ratio()


def _candidates(papers: list[Paper]) -> list[dict]:
    out = []
    for a, b in combinations(papers, 2):
        reasons = []
        if a.doi and a.doi == b.doi:
            reasons.append("same DOI")
        s = _sim(a.title, b.title)
        if normalize_title(a.title) and normalize_title(a.title) == normalize_title(b.title):
            reasons.append("same normalized title")
        elif s >= TITLE_SIM:
            reasons.append(f"title similarity {s:.2f}")
        if (a.doi and b.doi and _is_arxiv_doi(a.doi) != _is_arxiv_doi(b.doi)
                and s >= ARXIV_SIM and "same normalized title" not in reasons):
            reasons.append(f"arXiv/non-arXiv DOI pair, title similarity {s:.2f}")
        if reasons:
            la = {x.split()[-1].lower() for x in (a.authors or []) if x.split()}
            lb = {x.split()[-1].lower() for x in (b.authors or []) if x.split()}
            out.append({"a": _wid(a.id), "b": _wid(b.id),
                        "a_title": a.title, "b_title": b.title,
                        "a_year": a.year, "b_year": b.year,
                        "a_doi": a.doi, "b_doi": b.doi,
                        "shared_last_names": sorted(la & lb),
                        "reasons": reasons})
    return out


def check_library(slug: str) -> dict:
    papers = _llm_cal_papers() if slug == "llm-calibration" else _new_library_papers(slug)
    survivors = deduplicate(papers)
    merges = [{"survivor": _wid(p.id), "merged_from": [_wid(x) for x in p.merged_from]}
              for p in survivors if getattr(p, "merged_from", None)]
    return {"slug": slug, "n_papers": len(papers),
            "n_without_authors": sum(1 for p in papers if not p.authors),
            "four_pass_replay": {"n_after": len(survivors), "merges": merges},
            "candidates_for_hand_review": _candidates(papers)}


def diet_audit_duplicates() -> list[dict]:
    a = json.loads((DATA / "domains" / "diet-and-mortality" / "reasoning"
                    / "contradiction_audit.json").read_text())["verdicts"]
    out = []
    for i, v in enumerate(a, 1):
        if v["verdict"] != "duplicate":
            continue
        same_pair = [j for j, w in enumerate(a, 1) if j != i and w["verdict"] != "duplicate"
                     and {w["a_paper_id"], w["b_paper_id"]} == {v["a_paper_id"], v["b_paper_id"]}]
        out.append({"pair": i, "a_paper_id": v["a_paper_id"], "b_paper_id": v["b_paper_id"],
                    "a_text_starts": v["a_text_starts"], "b_text_starts": v["b_text_starts"],
                    "same_two_papers_as_pair": same_pair,
                    "kind": ("same two papers, different claim (one paper pair counted "
                             "more than once)") if same_pair else "needs review"})
    return out


def main() -> int:
    libs = [check_library(s) for s in ("llm-calibration", "diet-and-mortality", "ml-fairness")]
    out = {"title_sim_threshold": TITLE_SIM, "arxiv_sim_threshold": ARXIV_SIM,
           "libraries": libs, "diet_audit_duplicates": diet_audit_duplicates()}
    OUT.write_text(json.dumps(out, indent=2) + "\n")
    for lib in libs:
        print(f"{lib['slug']}: {lib['n_papers']} papers, 4-pass replay "
              f"{lib['n_papers']} -> {lib['four_pass_replay']['n_after']}, "
              f"{len(lib['candidates_for_hand_review'])} candidates, "
              f"{lib['n_without_authors']} without authors")
    for d in out["diet_audit_duplicates"]:
        print(f"diet audit pair {d['pair']}: {d['kind']} (same papers as {d['same_two_papers_as_pair']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
