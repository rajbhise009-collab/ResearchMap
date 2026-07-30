"""Bounded citation snowball from the core on-domain seeds.

Expands the corpus toward ~200 in-domain papers by traversing the
OpenAlex citation graph from the 26 core seeds, both directions, to
depth 2, with the AI-subfield gate at each hop. Live OpenAlex (1 credit
per filter page); bounded by hard caps so the nine known snowball
failure modes (PROGRESS.md "Ingestion redesign assessment") don't blow
up the walk or the budget:

  1. Seed echo-chamber   -> seeds already span venues/years (hand-picked).
  2. Hop-2 explosion     -> GLOBAL_TARGET stop + frequency-ranked fetch +
                            HOP2_EXPAND_TOP_N cap on which nodes expand.
  3. Subfield gate drops -> SOFT gate: CS field (17) OR AI subfield (1702)
     Nature outliers        across ANY topic, PLUS an anchor-term rescue
                            so a Nature-published semantic-entropy paper
                            (Farquhar) survives even if its primary topic
                            is a life-science subfield.
  4. Hub-paper dominance -> PER_SEED_INBOUND_CAP limits how many citing
                            papers any one seed contributes; inbound is
                            sorted by cited_by so the cap keeps the most
                            substantive citers, not a random slice.
  5. Time-direction mix  -> direction is recorded per edge (outbound =
                            references/antecedents, inbound = citers/
                            successors); both are kept deliberately.
  6. Citation-graph gaps -> tolerated + reported (23/26 seeds have 0
                            referenced_works in OpenAlex; the walk leans
                            inbound and says so).
  7. Preprint/published  -> final normalizer dedup (DOI then title+year).
     duplication
  8. No stopping rule    -> frequency ranking (co-citation count) + a
                            heuristic on/off-domain label gate the walk;
                            off-domain candidates never enter the frontier.
  9. Seed poison         -> seeds are the hand-reviewed core set only.

Output: data/live_samples/snowball_candidates.json — kept candidates
with provenance, plus per-stage yield and failure-mode counters. No
Gemini spend; no extraction here.
"""

from __future__ import annotations

import csv
import json
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path("/Users/rajbhise/Downloads/claudecode/ResearchMap")
sys.path.insert(0, str(REPO_ROOT))

from backend.app.corpus.heuristic_label import ANCHOR_TERMS, classify  # noqa: E402
from backend.app.corpus.run_live_extraction import CORPUS_CSV  # noqa: E402
from backend.app.ingestion.normalizer import (  # noqa: E402
    _reconstruct_abstract,
    normalize_title,
)
from backend.app.ingestion.openalex import (  # noqa: E402
    OpenAlexClient,
    OpenAlexQuotaError,
)

OUT = REPO_ROOT / "data" / "live_samples" / "snowball_candidates.json"

# --- Caps (guard the failure modes) -----------------------------------
# Final corpus target is ~200 papers TOTAL. The existing domain corpus
# already holds 34 in-domain papers, so the snowball contributes the
# remainder. (Overshooting also costs extraction $ against a $6 gate.)
EXISTING_IN_DOMAIN = 34
GLOBAL_TARGET = 200 - EXISTING_IN_DOMAIN   # = 166 new papers
PER_SEED_CAP = 40              # max NEW keepers any ONE seed may contribute
                              # (both directions combined) — the hub-seed
                              # dominance guard. A single citation-heavy
                              # survey cannot become the whole corpus.
FETCH_PER_NODE = 120          # max records fetched per node to hit its cap
HOP2_CAP = 20                 # max new keepers per expanded hop-1 node
HOP2_EXPAND_TOP_N = 30        # only the top-N hop-1 core keepers expand
CREDIT_FLOOR = 500            # stop if daily remaining drops below this
CENTRALITY = {"on-domain": "core", "borderline": "peripheral"}


def _core_seed_ids() -> list[str]:
    rows = list(csv.DictReader(CORPUS_CSV.open(encoding="utf-8")))
    return [
        r["openalex_id"].rsplit("/", 1)[-1]
        for r in rows
        if r["on_domain"] == "on-domain" and r.get("excluded") != "1"
    ]


def _all_labelled_ids() -> set[str]:
    """Every openalex id already hand-labelled (the 60) — snowball must
    not re-surface them as 'new'."""
    rows = list(csv.DictReader(CORPUS_CSV.open(encoding="utf-8")))
    return {r["openalex_id"].rsplit("/", 1)[-1] for r in rows}


def _native(oid: str) -> str:
    return oid.rsplit("/", 1)[-1]


def _passes_gate(record: dict, abstract: str) -> bool:
    """Soft AI gate: any topic in CS field (17) or AI subfield (1702),
    OR an anchor term appears in title/abstract (rescues off-subfield
    outliers like a Nature semantic-entropy paper)."""
    for t in record.get("topics") or []:
        sub = ((t.get("subfield") or {}).get("id") or "")
        fld = ((t.get("field") or {}).get("id") or "")
        if sub.endswith("/1702") or fld.endswith("/17"):
            return True
    blob = f"{record.get('title') or ''} {abstract}".lower()
    return any(term in blob for term in ANCHOR_TERMS)


def _abstract_of(record: dict) -> str:
    return _reconstruct_abstract(record.get("abstract_inverted_index")) or ""


class Snowball:
    def __init__(self, client: OpenAlexClient) -> None:
        self.client = client
        self.seeds = _core_seed_ids()
        self.exclude = _all_labelled_ids() | set(self.seeds)
        self.kept: dict[str, dict] = {}        # id -> candidate
        self.seen: set[str] = set(self.exclude)
        self.freq: Counter = Counter()         # co-citation frequency
        self.counters = Counter()              # failure-mode tallies
        self.off_domain_samples: list[dict] = []  # for the audit sample

    def _budget_ok(self) -> bool:
        rem = self.client.credits.last_remaining
        if rem is not None and rem < CREDIT_FLOOR:
            self.counters["stopped_credit_floor"] += 1
            return False
        return True

    def _consider(self, record: dict, *, hop: int, direction: str,
                  parent: str) -> bool:
        """Returns True iff this record became a NEW keeper."""
        oid = _native(record.get("id") or "")
        if not oid:
            return False
        self.freq[oid] += 1
        if oid in self.seen:
            # Already kept/excluded — just accumulate provenance frequency.
            if oid in self.kept:
                self.kept[oid]["parents"].add(parent)
                self.kept[oid]["directions"].add(direction)
            return False
        self.seen.add(oid)
        abstract = _abstract_of(record)
        if not abstract.strip():
            self.counters["dropped_no_abstract"] += 1
            return False
        if not _passes_gate(record, abstract):
            self.counters["dropped_gate"] += 1
            return False
        label, reason = classify(record, abstract_text=abstract)
        if label == "off-domain":
            self.counters["dropped_off_domain"] += 1
            if len(self.off_domain_samples) < 40:
                self.off_domain_samples.append({
                    "openalex_id": record.get("id"),
                    "title": record.get("title"),
                    "year": record.get("publication_year"),
                    "abstract": abstract,
                    "label": "off-domain",
                    "label_reason": reason,
                })
            return False
        self.counters[f"kept_{label}"] += 1
        self.kept[oid] = {
            "openalex_id": record.get("id"),
            "native_id": oid,
            "title": record.get("title"),
            "year": record.get("publication_year"),
            "doi": record.get("doi"),
            "cited_by_count": record.get("cited_by_count"),
            "abstract": abstract,
            "label": label,
            "domain_centrality": CENTRALITY[label],
            "label_reason": reason,
            "hop": hop,
            "directions": {direction},
            "parents": {parent},
        }
        return True

    def _expand(self, node_id: str, *, cap: int, hop: int,
                seed_records: dict[str, dict] | None) -> None:
        """Expand ONE node: inbound citers first (most-cited), then
        outbound references (hop-1 only). Stops after `cap` NEW keepers
        are attributed to this node — the per-seed dominance guard — or
        after FETCH_PER_NODE records are examined."""
        added = 0
        examined = 0
        if not self._budget_ok():
            return
        # Inbound: papers citing node_id (successors), substantive first.
        try:
            for rec in self.client.raw_works(
                filter=f"cites:{node_id}",
                sort="cited_by_count:desc",
                limit=FETCH_PER_NODE,
                per_page=50,
            ):
                examined += 1
                if self._consider(rec, hop=hop, direction="inbound",
                                  parent=node_id):
                    added += 1
                if added >= cap or examined >= FETCH_PER_NODE:
                    break
        except OpenAlexQuotaError:
            self.counters["openalex_quota_hit"] += 1
            return

        # Outbound: references (antecedents), hop-1 seeds only.
        if seed_records is not None and added < cap:
            rec = seed_records.get(node_id)
            ref_ids = [_native(r) for r in (rec or {}).get("referenced_works", [])]
            ref_ids = [r for r in ref_ids if r not in self.seen]
            for i in range(0, len(ref_ids), 50):
                if added >= cap or not self._budget_ok():
                    return
                chunk = ref_ids[i:i + 50]
                filt = "ids.openalex:" + "|".join(chunk)
                try:
                    for rec2 in self.client.raw_works(filter=filt,
                                                      limit=len(chunk), per_page=50):
                        if self._consider(rec2, hop=hop, direction="outbound",
                                          parent=node_id):
                            added += 1
                        if added >= cap:
                            return
                except OpenAlexQuotaError:
                    self.counters["openalex_quota_hit"] += 1
                    return

    def run(self) -> dict:
        # Fetch seed raw records (for referenced_works + freshness).
        seed_records: dict[str, dict] = {}
        for i in range(0, len(self.seeds), 50):
            chunk = self.seeds[i:i + 50]
            filt = "ids.openalex:" + "|".join(chunk)
            for rec in self.client.raw_works(filter=filt, limit=len(chunk),
                                             per_page=50):
                seed_records[_native(rec.get("id") or "")] = rec

        # --- Hop 1: expand EVERY seed, each capped at PER_SEED_CAP. ----
        for sid in self.seeds:
            self._expand(sid, cap=PER_SEED_CAP, hop=1, seed_records=seed_records)
        hop1_kept = len(self.kept)

        # --- Hop 2: expand top-N hop-1 CORE keepers by co-citation. ----
        hop1_core = sorted(
            (c for c in self.kept.values()
             if c["hop"] == 1 and c["label"] == "on-domain"),
            key=lambda c: (self.freq[c["native_id"]], c.get("cited_by_count") or 0),
            reverse=True,
        )[:HOP2_EXPAND_TOP_N]
        for c in hop1_core:
            if len(self.kept) >= GLOBAL_TARGET * 1.5:
                break  # gathered plenty to rank/trim from
            self._expand(c["native_id"], cap=HOP2_CAP, hop=2, seed_records=None)

        return self._finalize(hop1_kept)

    def _finalize(self, hop1_kept: int) -> dict:
        # In-corpus dedup by DOI then normalized (title, year).
        by_doi: dict[str, str] = {}
        by_ty: dict[tuple, str] = {}
        collapses = 0
        survivors: dict[str, dict] = {}
        # Prefer higher cited_by as survivor on collision.
        for oid, c in sorted(self.kept.items(),
                             key=lambda kv: kv[1].get("cited_by_count") or 0,
                             reverse=True):
            doi = (c.get("doi") or "").lower() or None
            ty = (normalize_title(c.get("title") or ""), c.get("year"))
            if doi and doi in by_doi:
                collapses += 1
                continue
            if ty in by_ty:
                collapses += 1
                continue
            survivors[oid] = c
            if doi:
                by_doi[doi] = oid
            by_ty[ty] = oid

        recs = []
        for c in survivors.values():
            c = dict(c)
            c["directions"] = sorted(c["directions"])
            c["parents"] = sorted(c["parents"])
            c["co_citation_freq"] = self.freq[c["native_id"]]
            recs.append(c)
        # Rank: core before peripheral, then co-citation frequency, then
        # citations. Truncate to the global target (the walk may gather
        # more; we keep the most topically-central).
        recs.sort(key=lambda c: (c["domain_centrality"] != "core",
                                 -c["co_citation_freq"],
                                 -(c.get("cited_by_count") or 0)))
        kept_before_trim = len(recs)
        recs = recs[:GLOBAL_TARGET]

        # Per-seed contribution (balance / hub-dominance check).
        seed_contrib: Counter = Counter()
        for c in recs:
            for p in c["parents"]:
                seed_contrib[p] += 1
        max_seed_share = (round(100 * max(seed_contrib.values()) / len(recs), 1)
                          if recs else 0.0)

        core = sum(1 for c in recs if c["domain_centrality"] == "core")
        periph = sum(1 for c in recs if c["domain_centrality"] == "peripheral")
        traversed = len(self.seen) - len(self.exclude)
        summary = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "seeds": len(self.seeds),
            "candidates_traversed": traversed,
            "kept_before_trim": kept_before_trim,
            "kept_total": len(recs),
            "kept_core": core,
            "kept_peripheral": periph,
            "hop1_kept": hop1_kept,
            "hop2_kept": len(self.kept) - hop1_kept,
            "dedup_collapses": collapses,
            "seeds_contributing": len(seed_contrib),
            "max_single_seed_share_pct": max_seed_share,
            "top_seed_contributions": seed_contrib.most_common(6),
            "yield_rate_pct": round(100 * kept_before_trim / traversed, 1) if traversed else 0.0,
            "failure_mode_counters": dict(self.counters),
            "openalex_credits": self.client.credits.as_dict(),
            "off_domain_samples": self.off_domain_samples,
            "records": recs,
        }
        return summary


def main() -> int:
    with OpenAlexClient() as client:
        sb = Snowball(client)
        t0 = time.time()
        summary = sb.run()
        summary["wall_seconds"] = round(time.time() - t0, 1)
    OUT.write_text(json.dumps(summary, indent=2))
    print(f"seeds={summary['seeds']} traversed={summary['candidates_traversed']} "
          f"kept_before_trim={summary['kept_before_trim']} "
          f"kept={summary['kept_total']} (core={summary['kept_core']}, "
          f"peripheral={summary['kept_peripheral']})")
    print(f"hop1={summary['hop1_kept']} hop2={summary['hop2_kept']} "
          f"dedup_collapses={summary['dedup_collapses']} "
          f"yield={summary['yield_rate_pct']}%")
    print(f"seed balance: {summary['seeds_contributing']}/{summary['seeds']} seeds "
          f"contributed; max single-seed share={summary['max_single_seed_share_pct']}%")
    print(f"top seeds: {summary['top_seed_contributions']}")
    print(f"failure-mode counters: {summary['failure_mode_counters']}")
    print(f"OpenAlex credits: {summary['openalex_credits']}")
    print(f"wrote {OUT.relative_to(REPO_ROOT)} in {summary['wall_seconds']}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
