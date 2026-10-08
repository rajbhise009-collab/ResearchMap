"""Regenerate every number-bearing block in the findings docs from data.

  python -m backend.app.corpus.doc_numbers          # rewrite the blocks in place
  python -m backend.app.corpus.doc_numbers --check  # exit 1 if any block is stale

A generated block sits between `<!-- gen:NAME -->` and `<!-- /gen:NAME -->`
in a doc. Only the text between the markers is replaced; prose around it is
hand-written. Free: reads files only. The impossibility-paper table rebuilds
the ML-fairness shortlist from the cached claim embeddings and REFUSES to
embed anything (it raises if a claim is missing from the cache), so this
script can never make a paid call.

Sources:
  data/spend_ledger.json                                   spend, corrections, cap
  data/ledger_audit.json                                   mock-entry audit
  data/relationships/relationship_summary.json             llm-calibration pairs
  data/domains/<slug>/reasoning/{coverage,contradictions,contradiction_audit}.json
  frontend/public/data/library/<slug>/stats.json           papers, full text, limitations
  data/coherence/features.json                             predictor scores
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))

DATA = REPO_ROOT / "data"
LIB = REPO_ROOT / "frontend" / "public" / "data" / "library"
DOCS = REPO_ROOT / "docs" / "findings"
def _registry_built() -> list[dict]:
    return [l for l in json.loads((REPO_ROOT / "data" / "library_registry.json").read_text())["libraries"]
            if l["status"] == "built"]


# Every built library except the frozen LLM-calibration baseline, in registry order.
NEW_LIBS = tuple(l["slug"] for l in _registry_built() if l["slug"] != "llm-calibration")
LIB_NAMES = {l["slug"]: l["short_name"] for l in _registry_built()}

# Impossibility-result papers re-examined in iteration 4 (OpenAlex work ids,
# read from the ML-fairness corpus). Labels come from the paper files.
IMPOSSIBILITY_PAPERS = ["W4386564359", "W2543774860", "W2524301210", "W2599025709",
                        "W2584805976", "W2790025105", "W2808105152"]


def _j(p: Path):
    return json.loads(p.read_text())


def _stats(slug: str) -> dict:
    return _j(LIB / slug / "stats.json")


def _table(head: list[str], align: list[str], rows: list[list]) -> str:
    out = ["| " + " | ".join(head) + " |",
           "|" + "|".join(":--" if a == "l" else "--:" for a in align) + "|"]
    out += ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]
    return "\n".join(out)


def _inr(x: float) -> str:
    return f"₹{x:,.2f}"


# ---- blocks -------------------------------------------------------------

def corpus() -> str:
    rows = []
    for slug in ("llm-calibration", *NEW_LIBS):
        s = _stats(slug)
        n = s["papers"]
        rows.append([LIB_NAMES[slug], f"`{slug}`", n, s.get("core", "—"),
                     s.get("peripheral", "—"),
                     f"{s['full_text']} ({round(100 * s['full_text'] / n)}%)",
                     f"{s['n_extractions']} of {n}"])
    return _table(["library", "slug", "papers", "core", "peripheral", "full text", "claims extracted"],
                  ["l", "l", "r", "r", "r", "r", "r"], rows)


def yield_table() -> str:
    rel = _j(DATA / "relationships" / "relationship_summary.json")["contradiction_stats"]
    rows = [["LLM calibration (frozen 2026-07; threshold 0.78, cap 10)",
             rel["candidates"], rel["classified"], rel["contradicts"],
             _stats("llm-calibration")["n_confirmed_contradictions"], "—", "—"]]
    for slug in NEW_LIBS:
        cov = _j(DATA / "domains" / slug / "reasoning" / "coverage.json")
        flagged = _j(DATA / "domains" / slug / "reasoning" / "contradictions.json")["n"]
        ap = DATA / "domains" / slug / "reasoning" / "contradiction_audit.json"
        v = [x["verdict"] for x in _j(ap)["verdicts"]] if ap.exists() else []
        st = cov["shortlist_settings"]
        rows.append([f"{LIB_NAMES[slug]} (threshold {st['threshold']:.2f}, cap {st['max_per_claim']})",
                     cov["shortlist_pairs"], cov["classified_pairs"], flagged,
                     v.count("genuine"), v.count("artifact") if v else "—",
                     v.count("duplicate") if v else "—"])
    return _table(["library (shortlist settings)", "shortlisted pairs", "classified",
                   "flagged by classifier", "hand-audited genuine", "artifact", "duplicate"],
                  ["l", "r", "r", "r", "r", "r", "r"], rows)


def diet_audit() -> str:
    a = _j(DATA / "domains" / "diet-and-mortality" / "reasoning" / "contradiction_audit.json")
    rows = [[i, v["verdict"], v["topic"], f"`{v['a_paper_id'].split(':')[-1]}` vs `{v['b_paper_id'].split(':')[-1]}`",
             v["reason"].replace("|", "/")]
            for i, v in enumerate(a["verdicts"], 1)]
    return _table(["pair", "verdict", "topic", "papers", "reason"], ["r", "l", "l", "l", "l"], rows)


def _fairness_shortlist():
    from backend.app.corpus import multi_domain_reason as R

    class _Refuse:
        def embed(self, texts):
            raise RuntimeError(f"doc_numbers would need to embed {len(texts)} claims; "
                               "refusing (free script, cache only)")

    exts = R.load_extractions("ml-fairness")
    cov = _j(DATA / "domains" / "ml-fairness" / "reasoning" / "coverage.json")["shortlist_settings"]
    pairs = R.compute_shortlist(exts, threshold=cov["threshold"],
                                max_per_claim=cov["max_per_claim"],
                                slug="ml-fairness", embed_client=_Refuse())
    paper_of = {c.id: e.paper_id.split(":")[-1] for e in exts for c in (e.claims or [])}
    return pairs, paper_of, R.load_classified_keys("ml-fairness"), {e.paper_id.split(":")[-1] for e in exts}


def impossibility() -> str:
    pairs, paper_of, done, extracted = _fairness_shortlist()
    flagged = {(x["from_claim_id"], x["to_claim_id"]) for x in
               _j(DATA / "domains" / "ml-fairness" / "reasoning" / "contradictions.json")["items"]}
    rows = []
    for wid in IMPOSSIBILITY_PAPERS:
        d = _j(LIB / "ml-fairness" / "paper" / f"{wid}.json")
        label = f"{d['title']} ({d['year']})"
        if wid not in extracted:
            rows.append([label, "not in corpus", "—", "—"])
            continue
        mine = [p for p in pairs if wid in (paper_of[p.from_claim_id], paper_of[p.to_claim_id])]
        keys = [(p.from_claim_id, p.to_claim_id) for p in mine]
        rows.append([f"{label} (`{wid}`)", len(mine), sum(k in done for k in keys),
                     sum(k in flagged for k in keys)])
    return _table(["paper", "shortlisted pairs", "classified", "flagged"], ["l", "r", "r", "r"], rows)


def _predictor_verdict(slug: str) -> dict:
    """From the 2026-08 study (features.json), else computed from the
    domain-selection fetch cached under data/coherence/<slug>/."""
    feats = {f["slug"]: f["verdict"] for f in _j(DATA / "coherence" / "features.json")}
    if slug in feats:
        return feats[slug]
    from backend.app.coherence import features as F
    return F.verdict(F.features(_j(DATA / "coherence" / slug / "openalex.json")["results"]))


def predictor() -> str:
    rows = []
    for slug in ("llm-calibration", *NEW_LIBS):
        v = _predictor_verdict(slug)
        rows.append([LIB_NAMES[slug], f"{v['contested_score']} ({v['contested_band']})",
                     _stats(slug)["n_confirmed_contradictions"]])
    return _table(["library", "predictor contested score", "hand-audited confirmed contradictions"],
                  ["l", "r", "r"], rows)


def fulltext() -> str:
    rows = []
    for slug in ("llm-calibration", *NEW_LIBS):
        s = _stats(slug)
        rows.append([LIB_NAMES[slug], s["full_text"], s["abstract_only"],
                     f"{round(100 * s['full_text'] / s['papers'])}%"])
    return _table(["library", "full text", "abstract only", "full-text share"],
                  ["l", "r", "r", "r"], rows)


def _future_work_items(slug: str) -> int:
    from backend.app.corpus import multi_domain_reason as R
    return sum(len(e.future_work or []) for e in R.load_extractions(slug))


def gap_types() -> str:
    rows = []
    for slug in NEW_LIBS:
        s = _stats(slug)
        g = s["gap_type_counts"]
        rows.append([LIB_NAMES[slug], f"{g['n_papers']} ({s['full_text']} full text)",
                     g["n_limitations"], _future_work_items(slug)])
    return _table(["library", "papers extracted", "limitations", "future-work items"],
                  ["l", "r", "r", "r"], rows)


def spend() -> str:
    L = _j(DATA / "spend_ledger.json")
    by = defaultdict(lambda: [0, 0.0, 0.0])
    for e in L["entries"]:
        b = by[e.get("stage", "unknown")]
        b[0] += 1
        b[1] += e["cost_usd"]
        b[2] += e["cost_inr"]
    rows = [[f"`{s}`", n, f"${u:.4f}", _inr(i)] for s, (n, u, i) in sorted(by.items())]
    tot_u = sum(v[1] for v in by.values())
    tot_i = sum(v[2] for v in by.values())
    rows.append(["**total (ledger, after corrections)**", sum(v[0] for v in by.values()),
                 f"**${tot_u:.4f}**", f"**{_inr(tot_i)}**"])
    from backend.app.extraction import money
    cfg = money.load()
    rem = money.remaining_inr(cfg, L["cumulative_inr"], L["entries"])
    rows.append(["ceiling (config/money.json: account total − safety buffer)", "", "",
                 _inr(money.ceiling_inr(cfg))])
    rows.append(["remaining (money rule)", "", "", _inr(rem)])
    return _table(["stage", "entries", "USD", "INR"], ["l", "r", "r", "r"], rows)


def unknown_entries() -> str:
    a = _j(DATA / "ledger_audit.json")
    u = a["unknown_stage"]
    lines = [
        f"- `unknown`-stage entries: **{u['n']}**, {_inr(u['inr'])} in total.",
        f"- All {u['n_with_mock_signature']} carry the mock-test signature "
        "(5 prompt tokens, 3 output tokens, 0 thinking tokens).",
        f"- Proven mock (signature + burst of exactly 10 inside one second): "
        f"**{u['n_proven_mock']}** entries, {_inr(u['proven_mock_inr'])}, in "
        f"{sum(b['proven_mock'] for b in u['bursts'])} bursts.",
        f"- Not proven, so still counted: **{u['n_unknown_not_proven']}** entries "
        f"({_inr(u['inr'] - u['proven_mock_inr'])}).",
        f"- Ledger before correction: {_inr(a['raw_cumulative_inr'])}; after the "
        f"appended correction: **{_inr(a['corrected_cumulative_inr'])}**.",
    ]
    return "\n".join(lines)


def duplicates() -> str:
    d = _j(DATA / "duplicate_check.json")
    rows = [[LIB_NAMES[l["slug"]], l["n_papers"], l["four_pass_replay"]["n_after"],
             len(l["candidates_for_hand_review"])] for l in d["libraries"]]
    return _table(["library", "papers", "after replaying the 4-pass dedup",
                   "candidates for hand review"], ["l", "r", "r", "r"], rows)


def _check(slug: str) -> tuple[int, int, int, int]:
    """(papers, extracted, shortlisted, classified) for any library."""
    s = _stats(slug)
    if slug == "llm-calibration":
        rel = _j(DATA / "relationships" / "relationship_summary.json")["contradiction_stats"]
        return s["papers"], s["n_extractions"], rel["candidates"], rel["classified"]
    cov = _j(DATA / "domains" / slug / "reasoning" / "coverage.json")
    return s["papers"], s["n_extractions"], cov["shortlist_pairs"], cov["classified_pairs"]


def _flagged(slug: str) -> int:
    if slug == "llm-calibration":
        return _j(DATA / "relationships" / "relationship_summary.json")["contradiction_stats"]["contradicts"]
    return _j(DATA / "domains" / slug / "reasoning" / "contradictions.json")["n"]


CONFOUNDS = {
    "llm-calibration": "own shortlist settings (0.78, cap 10); both flags set aside as regime conflation",
    "diet-and-mortality": "hand audit is the builder's, not expert review",
    "ml-fairness": "zero not explained (see multi-domain.md §2, hypotheses untested)",
    "social-media-teen-mental-health": ("22% full text; the rubric does not enforce the adolescent population "
                                        "(blind audit 87% in/out, 67% exact); builder's audit, not experts"),
}


def measured() -> str:
    rows = []
    for slug in ("llm-calibration", *NEW_LIBS):
        n, ext, sl, cl = _check(slug)
        v = _predictor_verdict(slug)
        rows.append([slug, v["contested_score"], v["contested_band"], _flagged(slug),
                     _stats(slug)["n_confirmed_contradictions"],
                     f"{ext} / {n} ({round(100 * ext / n)}%)", f"{cl} / {sl}",
                     CONFOUNDS.get(slug, "built 2026-10 or later; one hand audit by the builder, not experts")])
    return _table(["library", "predictor score", "predictor label", "raw flagged",
                   "audited genuine", "claims-read coverage", "pairs checked", "confounds"],
                  ["l", "r", "l", "r", "r", "l", "l", "l"], rows)


def mlf_facts() -> str:
    n, ext, sl, cl = _check("ml-fairness")
    return "\n".join([f"- Claims extracted from {ext} of {n} papers.",
                      f"- {cl} of {sl} shortlisted pairs classified; "
                      f"{_flagged('ml-fairness')} flagged as contradictions."])


def scorer_status() -> str:
    rows = []
    for slug in ("llm-calibration", *NEW_LIBS):
        n, ext, sl, cl = _check(slug)
        s = _stats(slug)
        y = s["scorer_yields"]
        conf = s["n_confirmed_contradictions"]
        fl = _flagged(slug)
        rows.append([slug, n, f"{ext} ({round(100 * ext / n)}%)", f"{cl} / {sl} pairs",
                     f"{conf} (of {fl} flagged)" if fl else conf,
                     y.get("persistent_limitations", 0),
                     "skipped (budget)" if "orphaned_future_work" in (s.get("scorers_skipped") or {})
                     else y.get("orphaned_future_work", 0),
                     f"{y.get('structural_holes', 0)} ({y.get('structural_holes_substantive', 0)} substantive)"])
    return _table(["library", "papers", "claims read", "disagreement check",
                   "confirmed contradictions", "persistent limitations",
                   "orphaned future work", "structural holes"],
                  ["l", "r", "r", "l", "r", "r", "l", "l"], rows)


def _v2_rows(section: str) -> str:
    d = _j(DATA / "duplicate_check_v2.json")
    rows = []
    for name, v in d[section].items():
        if not v["candidates"]:
            rows.append([name, f"`{v.get('n_papers', v.get('n_records'))}`", "—", "—", "—", "—", "—", "no candidates"])
        for c in v["candidates"]:
            rows.append([name, f"`{c['a'].split(':')[-1]}` / `{c['b'].split(':')[-1]}`",
                         f"{c['year_a']} / {c['year_b']}", c["title_jaccard"],
                         " ".join(c["numeric_a"]) or "—", " ".join(c["numeric_b"]) or "—",
                         "—" if c["abstract_jaccard"] is None else c["abstract_jaccard"],
                         "**merge**" if c["merge"] else f"blocked: {c['blocked_by']}"])
    head = "papers" if section == "corpora" else "records"
    return _table(["set", f"pair (or {head} scanned)", "years", "title Jaccard",
                   "numbers A", "numbers B", "abstract Jaccard", "rule outcome"],
                  ["l", "l", "l", "r", "l", "l", "r", "l"], rows)


def v2_corpora() -> str:
    return _v2_rows("corpora")


def v2_sweep() -> str:
    return _v2_rows("sweep")


def v2_counts() -> str:
    rows = []
    for slug in ("llm-calibration", *NEW_LIBS):
        log_p = DATA / "domains" / slug / "merge_log.json"
        if log_p.exists():
            lg = _j(log_p)
            b, a = lg["before"], lg["after"]
            rows.append([LIB_NAMES[slug], b["papers"], a["papers"], b["shortlist_pairs"],
                         a["shortlist_pairs"], b["supports_verdicts"], a["supports_verdicts"],
                         b["flagged_contradictions"], a["flagged_contradictions"]])
        else:
            n, _ext, sl, _cl = _check(slug)
            rows.append([LIB_NAMES[slug], n, n, sl, sl, "unchanged", "unchanged",
                         _flagged(slug), _flagged(slug)])
    return _table(["library", "papers before", "papers after", "shortlisted pairs before",
                   "after", "supports verdicts before", "after", "flagged before", "after"],
                  ["l", "r", "r", "r", "r", "r", "r", "r", "r"], rows)


def audit_doubts() -> str:
    lines = []
    for slug in NEW_LIBS:
        p = DATA / "domains" / slug / "reasoning" / "audit_doubts.json"
        for it in (_j(p)["items"] if p.exists() else []):
            lines.append(f"- **{LIB_NAMES[slug]}.** {it['text']}")
    return "\n".join(lines)


def scorer_yields() -> str:
    """Visible results per type, from site-facts.json (what the site shows),
    plus items set aside after checking."""
    facts = {l["slug"]: l for l in _j(REPO_ROOT / "frontend" / "public" / "data"
                                      / "site-facts.json")["libraries"]}
    order = [("unresolved_contradictions", "disagreements kept after checking"),
             ("persistent_limitations", "recurring limitations"),
             ("structural_holes", "method-transfer leads"),
             ("orphaned_future_work", "unfollowed questions")]
    rows = []
    for slug in ("llm-calibration", *NEW_LIBS):
        f = facts[slug]
        by = {r["type"]: r for r in f["results"]}
        row = [LIB_NAMES[slug]]
        for k, _l in order:
            r = by[k]
            row.append("skipped (budget)" if r["count"] is None else r["count"])
        row += [f.get("set_aside_total", 0), f["results_total"]]
        rows.append(row)
    return _table(["library"] + [l for _k, l in order] + ["set aside after checking", "total results"],
                  ["l", "r", "r", "r", "r", "r", "r"], rows)


BLOCKS = {
    "multi-domain.md": {"corpus": corpus, "yield": yield_table, "diet-audit": diet_audit,
                        "impossibility": impossibility, "predictor": predictor,
                        "mlf-facts": mlf_facts, "audit-doubts": audit_doubts,
                        "scorer-yields": scorer_yields,
                        "fulltext": fulltext, "gap-types": gap_types, "spend": spend},
    "ledger-unknown-entries.md": {"unknown": unknown_entries, "spend": spend},
    "domain-coherence-predictor.md": {"impossibility": impossibility, "measured": measured},
    "new-library-scorer-status.md": {"scorer-status": scorer_status},
    "duplicate-check-v2.md": {"v2-corpora": v2_corpora, "v2-sweep": v2_sweep,
                              "v2-counts": v2_counts},
    # duplicate-check.md is a dated record (pre-merge); its table is frozen.
}


def render(text: str, blocks: dict) -> str:
    cache: dict[str, str] = {}
    for name, fn in blocks.items():
        pat = re.compile(rf"(<!-- gen:{re.escape(name)} -->\n)(.*?)(<!-- /gen:{re.escape(name)} -->)", re.S)
        if pat.search(text):
            body = cache.setdefault(name, fn())
            text = pat.sub(lambda m: m.group(1) + body + "\n" + m.group(3), text)
    return text


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--check", action="store_true")
    a = p.parse_args()
    stale = []
    for doc, blocks in BLOCKS.items():
        path = DOCS / doc
        if not path.exists():
            continue
        old = path.read_text()
        new = render(old, blocks)
        if new != old:
            stale.append(doc)
            if not a.check:
                path.write_text(new)
    if a.check:
        print("stale: " + ", ".join(stale) if stale else "all generated blocks current")
        return 1 if stale else 0
    print("rewrote: " + (", ".join(stale) if stale else "nothing (already current)"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
