"""Phase-2 corpus-quality diagnostic.

One live OpenAlex call for ~200 papers under the current v3 query
strategy. Heuristic auto-labels each paper (on-domain / off-domain /
borderline). Samples 60 for a hand-review CSV with a blank on_domain
column. Attributes each paper to the topic + anchor terms it matched
so we can measure per-clause leak.

Deliberately a one-shot script, not a service — this is a research
task per the phase brief.

Outputs (all relative to repo root):
  data/live_samples/phase2_diagnostic_raw.json      # raw response
  data/labelled/corpus_relevance_review.csv         # 60-row hand-review
  data/labelled/heuristic_full_labels.csv           # full 200-row auto-labels
  data/labelled/per_clause_leak.md                  # leak breakdown report
"""

from __future__ import annotations

import csv
import hashlib
import json
import random
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path("/Users/rajbhise/Downloads/claudecode/ResearchMap")
sys.path.insert(0, str(REPO_ROOT))

import httpx  # noqa: E402

from backend.app.config import get_settings  # noqa: E402
from backend.app.corpus.heuristic_label import (  # noqa: E402
    ANCHOR_TERMS,
    CO_OCCURRENCE_WINDOW,
    TOPIC_TERMS,
    classify,
)
from backend.app.ingestion.normalizer import _reconstruct_abstract  # noqa: E402
from backend.app.ingestion.openalex import OpenAlexClient  # noqa: E402


# --- Query (frozen from v3) --------------------------------------------

ANCHOR = (
    '"language model" OR "LLM" OR "large language model" '
    'OR "neural text generation"'
)
TOPIC = (
    'calibration OR "uncertainty quantification" OR abstention '
    'OR "selective prediction" OR "hallucination detection" '
    'OR "confidence estimation" OR "epistemic uncertainty"'
)
SEARCH_VALUE = f"({ANCHOR}) AND ({TOPIC})"
FILTER = ",".join([
    f"title_and_abstract.search:{SEARCH_VALUE}",
    "primary_topic.subfield.id:1702",
    "type:article|preprint",
    "publication_year:>2018",
])
TARGET_COUNT = 200
REVIEW_SAMPLE_SIZE = 60
RANDOM_SEED = 20260723

RAW_PATH        = REPO_ROOT / "data" / "live_samples" / "phase2_diagnostic_raw.json"
FULL_LABEL_PATH = REPO_ROOT / "data" / "labelled" / "heuristic_full_labels.csv"
REVIEW_PATH     = REPO_ROOT / "data" / "labelled" / "corpus_relevance_review.csv"
LEAK_REPORT     = REPO_ROOT / "data" / "labelled" / "per_clause_leak.md"


def _abstract(record: dict) -> str | None:
    return _reconstruct_abstract(record.get("abstract_inverted_index"))


def _venue(record: dict) -> str | None:
    hv = record.get("host_venue") or record.get("primary_location") or {}
    if isinstance(hv, dict):
        src = hv.get("source") if isinstance(hv.get("source"), dict) else {}
        return (src.get("display_name") if isinstance(src, dict) else None) \
                or hv.get("display_name")
    return None


def _primary_topic_display(record: dict) -> str | None:
    pt = record.get("primary_topic") or {}
    return (pt.get("display_name") if isinstance(pt, dict) else None)


def _matched_terms(text: str, terms: tuple[str, ...]) -> list[str]:
    """Return terms whose lower-case appearance is present in `text`."""
    lower = text.lower()
    hits: list[str] = []
    for t in terms:
        if re.search(rf"\b{re.escape(t.lower())}\b", lower):
            hits.append(t)
    return hits


def main() -> int:
    settings = get_settings()
    if not settings.can_use_openalex_live:
        print("OPENALEX_API_KEY unset — refusing live call.", file=sys.stderr)
        return 2

    RAW_PATH.parent.mkdir(parents=True, exist_ok=True)
    REVIEW_PATH.parent.mkdir(parents=True, exist_ok=True)

    with OpenAlexClient(page_size=TARGET_COUNT) as client:
        try:
            payload = client._request(
                path="/works",
                params={
                    "filter": FILTER,
                    "per-page": str(TARGET_COUNT),
                    # sort omitted — default relevance ordering
                },
                endpoint_label="works.search",
            )
        except httpx.HTTPStatusError as e:
            print(f"HTTP {e.response.status_code}: {e.response.text[:600]}",
                  file=sys.stderr)
            return 1

        body = payload["body"]
        results = body.get("results") or []
        ledger = client.credits.as_dict()

    # --- Raw dump ------------------------------------------------------
    RAW_PATH.write_text(json.dumps({
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "filter": FILTER,
        "sort": "default (relevance)",
        "per_page": TARGET_COUNT,
        "credit_ledger": ledger,
        "meta": body.get("meta"),
        "results": results,
    }, indent=2, ensure_ascii=False))
    raw_hash = hashlib.sha256(RAW_PATH.read_bytes()).hexdigest()[:12]
    print(f"[fetch] {len(results)} papers, credit ledger: {ledger}")

    # --- Heuristic classification -------------------------------------
    labelled_rows: list[dict] = []
    for w in results:
        abstract = _abstract(w)
        text = " ".join(filter(None, [w.get("title") or "", abstract or ""]))
        label, rationale = classify(w, abstract_text=abstract)
        matched_anchors = _matched_terms(text, ANCHOR_TERMS)
        matched_topics = _matched_terms(text, TOPIC_TERMS)
        labelled_rows.append({
            "openalex_id": w.get("id"),
            "title": (w.get("title") or "").strip(),
            "year": w.get("publication_year"),
            "venue": _venue(w) or "",
            "primary_topic": _primary_topic_display(w) or "",
            "cited_by_count": w.get("cited_by_count", 0),
            "heuristic_on_domain": label,
            "heuristic_rationale": rationale,
            "matched_anchor_terms": "|".join(matched_anchors),
            "matched_topic_terms": "|".join(matched_topics),
            "abstract_snippet": (abstract or "")[:400].replace("\n", " "),
        })

    # --- Write full-labelled CSV --------------------------------------
    fieldnames = list(labelled_rows[0].keys())
    with FULL_LABEL_PATH.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(labelled_rows)

    # --- Sample 60 for hand-review CSV --------------------------------
    rng = random.Random(RANDOM_SEED)
    idx = list(range(len(labelled_rows)))
    rng.shuffle(idx)
    sample = [labelled_rows[i] for i in idx[:REVIEW_SAMPLE_SIZE]]

    review_fields = [
        "openalex_id", "title", "year", "venue", "primary_topic",
        "cited_by_count", "abstract_snippet", "matched_anchor_terms",
        "matched_topic_terms", "heuristic_on_domain", "heuristic_rationale",
        # blank column for hand-labelling. Values: on-domain / off-domain /
        # borderline (matches the heuristic vocabulary).
        "on_domain",
        "reviewer_notes",
    ]
    with REVIEW_PATH.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=review_fields)
        w.writeheader()
        for row in sample:
            out = {k: row.get(k, "") for k in review_fields}
            out["on_domain"] = ""
            out["reviewer_notes"] = ""
            w.writerow(out)

    # --- Per-clause leak breakdown (over heuristic labels) ------------
    #
    # Two views:
    # (1) off-domain rate per clause — the strict view. The AI-subfield
    #     filter already killed cross-domain contamination, so almost
    #     every remaining paper survives with the heuristic's default
    #     "on-domain". This view will mostly be zeros; it's still
    #     reported for completeness.
    # (2) non-on-domain rate per clause (borderline + off-domain) — the
    #     more informative view. Borderline is where the within-AI
    #     noise (application papers mentioning LLMs; adjacent surveys)
    #     accumulates. The hand-labelled CSV is the definitive answer
    #     to which of those borderline papers is truly off-domain.
    label_counts = {"on-domain": 0, "off-domain": 0, "borderline": 0}
    per_topic_total: dict[str, int] = {t: 0 for t in TOPIC_TERMS}
    per_topic_offdomain: dict[str, int] = {t: 0 for t in TOPIC_TERMS}
    per_topic_nonon: dict[str, int] = {t: 0 for t in TOPIC_TERMS}
    per_anchor_total: dict[str, int] = {t: 0 for t in ANCHOR_TERMS}
    per_anchor_offdomain: dict[str, int] = {t: 0 for t in ANCHOR_TERMS}
    per_anchor_nonon: dict[str, int] = {t: 0 for t in ANCHOR_TERMS}
    for row in labelled_rows:
        label_counts[row["heuristic_on_domain"]] += 1
        is_off = row["heuristic_on_domain"] == "off-domain"
        is_nonon = row["heuristic_on_domain"] != "on-domain"
        for t in row["matched_topic_terms"].split("|"):
            if t:
                per_topic_total[t] = per_topic_total.get(t, 0) + 1
                if is_off:
                    per_topic_offdomain[t] = per_topic_offdomain.get(t, 0) + 1
                if is_nonon:
                    per_topic_nonon[t] = per_topic_nonon.get(t, 0) + 1
        for t in row["matched_anchor_terms"].split("|"):
            if t:
                per_anchor_total[t] = per_anchor_total.get(t, 0) + 1
                if is_off:
                    per_anchor_offdomain[t] = per_anchor_offdomain.get(t, 0) + 1
                if is_nonon:
                    per_anchor_nonon[t] = per_anchor_nonon.get(t, 0) + 1

    total = len(labelled_rows)
    def _pct(n: int, d: int) -> str:
        return f"{100.0 * n / d:.1f}%" if d else "-"

    lines: list[str] = []
    lines.append("# Per-clause leak breakdown — Phase 2 diagnostic")
    lines.append("")
    lines.append(f"- Sample size: **{total}** papers")
    lines.append(f"- Raw dump: `data/live_samples/phase2_diagnostic_raw.json` (sha256[:12] = `{raw_hash}`)")
    lines.append(f"- Credit ledger: `{json.dumps(ledger)}`")
    lines.append(f"- Query filter (frozen): `{FILTER}`")
    lines.append(f"- Anchor+topic co-occurrence window: {CO_OCCURRENCE_WINDOW} tokens")
    lines.append("")
    lines.append("## Heuristic label distribution")
    lines.append("")
    lines.append("| Label | Count | Share |")
    lines.append("|:------|------:|------:|")
    for k in ("on-domain", "borderline", "off-domain"):
        c = label_counts[k]
        lines.append(f"| {k} | {c} | {_pct(c, total)} |")
    lines.append("")
    lines.append(
        "**Heuristic-measured on-domain rate** (on-domain / total) = "
        f"**{_pct(label_counts['on-domain'], total)}**.\n\n"
        "**IMPORTANT: do not read this as precision.** The heuristic "
        "is designed to catch CROSS-DOMAIN contamination (chemistry, "
        "materials science, medicine venues), which the "
        "`primary_topic.subfield.id:1702` filter already removed at "
        "query time — so `off-domain` will be near-zero regardless of "
        "true within-AI noise. The `borderline` bucket is where "
        "within-AI application papers accumulate; the 60-row hand-"
        "review CSV is the definitive precision measurement, not this "
        "table."
    )
    lines.append("")
    lines.append("## Per-topic-term leak (strict off-domain rate)")
    lines.append("")
    lines.append("Rate = fraction of papers matching this topic term "
                 "that the heuristic labelled off-domain. Ranked "
                 "most-leaky first. Sparse by design — see note above.")
    lines.append("")
    lines.append("| Topic term | Matches | Off-domain hits | Leak rate |")
    lines.append("|:-----------|--------:|----------------:|----------:|")
    for term, cnt in sorted(per_topic_total.items(), key=lambda x: -per_topic_offdomain.get(x[0], 0)):
        off = per_topic_offdomain.get(term, 0)
        lines.append(f"| {term!r} | {cnt} | {off} | {_pct(off, cnt)} |")
    lines.append("")
    lines.append("## Per-topic-term leak (non-on-domain rate — borderline + off-domain)")
    lines.append("")
    lines.append(
        "The heuristic-informative view. Rate = fraction of papers "
        "matching this topic term that the heuristic did NOT confidently "
        "label on-domain. Ranked highest-rate first. Not conclusive "
        "(borderline includes some real on-domain papers whose "
        "co-occurrence didn't tighten enough), but it's the best cheap "
        "signal for which clause is pulling the most within-AI grey area."
    )
    lines.append("")
    lines.append("| Topic term | Matches | Non-on-domain hits | Rate |")
    lines.append("|:-----------|--------:|-------------------:|-----:|")
    for term, cnt in sorted(per_topic_total.items(),
                             key=lambda x: -(per_topic_nonon.get(x[0], 0) / max(1, x[1]))):
        n = per_topic_nonon.get(term, 0)
        lines.append(f"| {term!r} | {cnt} | {n} | {_pct(n, cnt)} |")
    lines.append("")
    lines.append("## Per-anchor-term leak (strict off-domain rate)")
    lines.append("")
    lines.append("| Anchor term | Matches | Off-domain hits | Leak rate |")
    lines.append("|:------------|--------:|----------------:|----------:|")
    for term, cnt in sorted(per_anchor_total.items(), key=lambda x: -per_anchor_offdomain.get(x[0], 0)):
        off = per_anchor_offdomain.get(term, 0)
        lines.append(f"| {term!r} | {cnt} | {off} | {_pct(off, cnt)} |")
    lines.append("")
    lines.append("## Per-anchor-term leak (non-on-domain rate)")
    lines.append("")
    lines.append("| Anchor term | Matches | Non-on-domain hits | Rate |")
    lines.append("|:------------|--------:|-------------------:|-----:|")
    for term, cnt in sorted(per_anchor_total.items(),
                             key=lambda x: -(per_anchor_nonon.get(x[0], 0) / max(1, x[1]))):
        n = per_anchor_nonon.get(term, 0)
        lines.append(f"| {term!r} | {cnt} | {n} | {_pct(n, cnt)} |")
    lines.append("")
    lines.append("## Files for review")
    lines.append("")
    lines.append(
        "- `data/labelled/heuristic_full_labels.csv` — all "
        f"{total} papers with heuristic label and matched terms."
    )
    lines.append(
        f"- `data/labelled/corpus_relevance_review.csv` — {REVIEW_SAMPLE_SIZE}-paper "
        "sample with an empty `on_domain` column for hand-labelling."
    )
    lines.append(
        "- `data/live_samples/phase2_diagnostic_raw.json` — full "
        "OpenAlex response body + credit-ledger headers."
    )
    lines.append("")
    lines.append("## Agreement between heuristic and hand labels")
    lines.append("")
    lines.append(
        "Not yet measurable — the `on_domain` column in the review CSV "
        "is empty until Raj fills it in. Once filled, compute agreement "
        "with a follow-up pass over the CSV. Fields to expect: rows "
        "where heuristic said `on-domain` but human said `off-domain` "
        "(false positives), and vice versa (false negatives)."
    )

    LEAK_REPORT.write_text("\n".join(lines))
    print(f"[write] {FULL_LABEL_PATH.relative_to(REPO_ROOT)}")
    print(f"[write] {REVIEW_PATH.relative_to(REPO_ROOT)}")
    print(f"[write] {LEAK_REPORT.relative_to(REPO_ROOT)}")
    print(f"[write] {RAW_PATH.relative_to(REPO_ROOT)}  (sha256[:12] {raw_hash})")

    # Stdout summary — enough for the assistant's turn-end message.
    print(f"\n=== SUMMARY ===")
    print(f"Fetched: {total} papers, credits used: {ledger.get('credits_used_this_run')}")
    print(f"Heuristic labels:")
    for k, c in label_counts.items():
        print(f"  {k:12s}: {c:3d} ({_pct(c, total)})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
