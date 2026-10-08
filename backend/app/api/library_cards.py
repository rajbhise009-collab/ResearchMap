"""Phase-4 scorer cards for a multi-domain library — the same scorers,
thresholds, card assembly and plain-language translation as LLM
calibration (ranking.assemble + api.language). Deterministic; reads files;
never calls an LLM.

Which scorers run is decided by what data exists, never assumed:
  - persistent limitations: always (free, code only)
  - structural holes: always; k = max(2, round(sqrt N)) (the scaling study's
    correction), top 15, each lead labelled by its saved LLM confirmation
  - orphaned future work: only if the two-stage matcher's verdicts exist
    (reasoning/fw_addressals.jsonl). Without them "unfollowed" would be
    unchecked, so the scorer is skipped and the reason is published.
  - unresolved contradictions: not here — the library's audited
    disagreement cards are produced by multi_library_export and unchanged.
  - disjoint bridging: off (as everywhere).
"""
from __future__ import annotations

import re
from pathlib import Path

from backend.app.api import language
from backend.app.api.contradiction_titles import VERDICT_WORDS
from backend.app.config import REPO_ROOT

DOMAINS = REPO_ROOT / "data" / "domains"


def _slugify(s: str) -> str:
    return re.sub(r"[^a-zA-Z0-9]+", "-", s).strip("-").lower()


def scorer_plan(slug: str) -> tuple[list[str], dict[str, str]]:
    """(scorers to run, {skipped scorer: plain reason})."""
    run = ["persistent_limitations", "structural_holes"]
    skipped: dict[str, str] = {}
    addr = DOMAINS / slug / "reasoning" / "fw_addressals.jsonl"
    if addr.exists() and addr.read_text().strip():
        run.append("orphaned_future_work")
    else:
        skipped["orphaned_future_work"] = (
            "seeing whether later papers took up each paper's suggested next "
            "steps needs a paid language-model pass that did not fit this "
            "run's budget, so open questions are not listed for this library yet")
    return run, skipped


def _dedupe(cards: list[dict]) -> None:
    """Headlines unique within the library: a repeated headline gets the
    title of the paper the card is about (its first supporting paper)."""
    seen: dict[str, int] = {}
    for c in cards:
        h = c["consumer"]["headline"]
        seen[h] = seen.get(h, 0) + 1
    for c in cards:
        h = c["consumer"]["headline"]
        if seen[h] > 1:
            sp = (c.get("supporting_papers") or [{}])[0]
            c["consumer"]["headline"] = f"{h} ({(sp.get('title') or c['id'])[:80]})"


def scorer_cards(slug: str) -> tuple[list[dict], dict, dict[str, str]]:
    """(cards ready for the snapshot, yields per scorer, skipped scorers)."""
    from backend.app.ranking.assemble import build_evidence_cards
    from backend.app.reasoning.library_corpus import load_library_corpus
    from backend.app.reasoning.run_library_scorers import confirmations_path, n_clusters_for

    run, skipped = scorer_plan(slug)
    rc = load_library_corpus(slug)
    cards = build_evidence_cards(
        rc, scorers=run, confirmations_path=confirmations_path(slug),
        scorer_kwargs={"structural_holes": {"n_clusters": n_clusters_for(len(rc.papers)),
                                            "top": 15}})
    out = []
    for c in cards:
        d = c.model_dump(mode="json")
        d["slug"] = f"opp-{slug}-{_slugify(c.id.removeprefix('opp:'))}"
        d["consumer"] = language.consumer_card(d)
        if d["consumer"].get("verdict"):
            d["verdict"] = d["consumer"]["verdict"]
        out.append(d)
    _dedupe(out)
    for d in out:
        low = d["consumer"]["headline"].lower()
        bad = [w for w in VERDICT_WORDS if re.search(rf"\b{w}\b", low)]
        if bad:
            raise ValueError(f"verdict word {bad} in headline {d['consumer']['headline']!r}")
    yields = {
        "persistent_limitations": sum(1 for d in out if d["scorer"] == "persistent_limitations"),
        "orphaned_future_work": sum(1 for d in out if d["scorer"] == "orphaned_future_work"),
        "structural_holes": sum(1 for d in out if d["scorer"] == "structural_holes"),
        "structural_holes_substantive": sum(1 for d in out if d["scorer"] == "structural_holes"
                                            and d.get("confirm_status") == "substantive"),
    }
    return out, yields, skipped


__all__ = ["scorer_cards", "scorer_plan"]
