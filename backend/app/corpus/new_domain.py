"""Prepare a new library end to end, free (OpenAlex + open full text only).

  python -m backend.app.corpus.new_domain --domain social-media --stage all
  python -m backend.app.corpus.new_domain --domain social-media --stage audit-score

Stages (each resumable; outputs under data/domains/<slug>/):
  snowball      corpus.multi_domain.snowball (seed pool, two hops, per-seed
                and hop-2 caps, global target, off-domain rejects kept)
  prelabel      every snowball record classified by the library's rubric;
                off-domain dropped; then DEDUP before trimming: the full
                ingestion dedupe (normalizer.deduplicate: DOI, title+year+
                author, cross-year, arXiv<->published, title similarity) plus
                the title rule (same normalised title of >= 25 characters);
                every collapse logged to dedup_log.json; trimmed to 100
                (core by citations first, then borderline)
  fulltext      corpus.multi_domain.retrieve_fulltext_all (the real pipeline)
  slim          records.slim.json (what a fresh checkout needs)
  audit         15-paper stratified sample for a BLIND self-audit:
                audit_blind.json holds titles + abstracts only (no labels);
                the auditor's labels go in audit_blind_labels.json
  audit-score   agreement between the blind labels and the rubric; >= 80%
                required. Writes audit_result.json.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from collections import Counter
from pathlib import Path

from backend.app.corpus import multi_domain as M
from backend.app.corpus import records

TARGET = 100
AGREEMENT_REQUIRED = 0.80


def _dir(slug: str) -> Path:
    return M.DOMAINS_DIR / slug


def prelabel_dedup(cfg: M.DomainConfig) -> dict:
    from backend.app.ingestion.normalizer import deduplicate, from_openalex, normalize_title
    snow = json.loads(M._snowball_path(cfg).read_text())
    labelled = []
    counts = Counter()
    for rec in snow["records"]:
        wid = M._native_id(rec.get("id", ""))
        if not wid:
            continue
        abstract = M._abstract_of(rec)
        label, why = M.classify(rec, abstract=abstract, config=cfg)
        counts[label] += 1
        if label != "off-domain":
            labelled.append((rec, label, why, abstract))
    # 4-pass ingestion dedupe over everything kept
    papers = {}
    for rec, *_ in labelled:
        try:
            papers[rec["id"]] = from_openalex(rec)
        except Exception:  # noqa: BLE001
            continue
    survivors = {p.id for p in deduplicate(list(papers.values()))}
    log = []
    by_pid = {p.id: rid for rid, p in papers.items()}
    keep_ids = {by_pid[s] for s in survivors if s in by_pid}
    for rid, p in papers.items():
        if rid not in keep_ids:
            log.append({"dropped": M._native_id(rid), "title": p.title, "rule": "ingestion 4-pass dedupe"})
    # title rule among what is left (deterministic: most-cited wins)
    seen_t: dict[str, str] = {}
    kept = []
    for rec, label, why, abstract in sorted(labelled, key=lambda x: (-(x[0].get("cited_by_count") or 0),
                                                                     x[0]["id"])):
        if rec["id"] not in keep_ids:
            continue
        t = normalize_title(rec.get("title") or rec.get("display_name") or "")
        if len(t) >= 25 and t in seen_t:
            log.append({"dropped": M._native_id(rec["id"]), "title": rec.get("title"),
                        "rule": f"same normalised title as {seen_t[t]}"})
            continue
        if t:
            seen_t.setdefault(t, M._native_id(rec["id"]))
        kept.append({
            "wid": M._native_id(rec["id"]), "openalex_id": rec.get("id"),
            "title": rec.get("title") or rec.get("display_name"), "year": rec.get("publication_year"),
            "doi": rec.get("doi"), "venue": M._venue_of(rec), "field": M._field_of(rec),
            "cited_by_count": rec.get("cited_by_count"), "abstract": abstract,
            "label": label, "rationale": why,
            "domain_centrality": "core" if label == "on-domain" else "peripheral"})
    kept.sort(key=lambda r: (r["domain_centrality"] != "core", -(r["cited_by_count"] or 0), r["wid"]))
    trimmed = kept[:TARGET]
    out = {"slug": cfg.slug, "n_input": snow.get("n_candidates", len(snow["records"])),
           "n_pre_dedup": len(labelled), "n_after_dedup": len(kept), "n_kept": len(trimmed),
           "counts_by_label": dict(counts),
           "counts_by_centrality": dict(Counter(r["domain_centrality"] for r in trimmed)),
           "entries": trimmed}
    M._prelabel_path(cfg).write_text(json.dumps(out))
    (_dir(cfg.slug) / "dedup_log.json").write_text(json.dumps({"collapsed": log}, indent=1))
    return {k: v for k, v in out.items() if k != "entries"} | {"dedup_collapsed": len(log)}


def audit_blind(cfg: M.DomainConfig, n: int = 15, seed: int = 7) -> dict:
    """Stratified: 7 core, 5 borderline, 3 rejected (off-domain) — shown with
    title, venue and abstract only, in shuffled order, with no labels."""
    pre = json.loads(M._prelabel_path(cfg).read_text())["entries"]
    snow = json.loads(M._snowball_path(cfg).read_text())
    rng = random.Random(seed)
    core = [e for e in pre if e["domain_centrality"] == "core"]
    peri = [e for e in pre if e["domain_centrality"] == "peripheral"]
    rej = []
    for r in snow.get("rejected_records", []):
        rej.append({"wid": M._native_id(r.get("id", "")), "title": r.get("title") or r.get("display_name"),
                    "venue": M._venue_of(r), "abstract": M._abstract_of(r), "label": "off-domain"})
    rng.shuffle(core), rng.shuffle(peri), rng.shuffle(rej)
    pick = core[:7] + peri[:5] + rej[:max(0, n - min(7, len(core)) - min(5, len(peri)))]
    pick = pick[:n]
    rng.shuffle(pick)
    blind = [{"wid": e["wid"], "title": e["title"], "venue": e.get("venue"),
              "abstract": (e.get("abstract") or "")[:1500]} for e in pick]
    key = {e["wid"]: e["label"] for e in pick}
    (_dir(cfg.slug) / "audit_blind.json").write_text(json.dumps({"items": blind}, indent=1))
    (_dir(cfg.slug) / "audit_key.json").write_text(json.dumps(key, indent=1))
    return {"n": len(blind), "by_label": dict(Counter(key.values()))}


def audit_score(cfg: M.DomainConfig) -> dict:
    """Agreement = blind label == rubric label, where 'borderline' and
    'on-domain' both count as 'in the library' only if the auditor said so
    exactly; a three-way match is reported alongside the in/out match."""
    key = json.loads((_dir(cfg.slug) / "audit_key.json").read_text())
    mine = json.loads((_dir(cfg.slug) / "audit_blind_labels.json").read_text())["labels"]
    rows, exact, inout = [], 0, 0
    for wid, rubric in key.items():
        me = mine[wid]["label"]
        e = me == rubric
        io = (me != "off-domain") == (rubric != "off-domain")
        exact += e
        inout += io
        rows.append({"wid": wid, "rubric": rubric, "auditor": me, "exact": e, "in_out": io,
                     "why": mine[wid].get("why", "")})
    n = len(rows)
    res = {"n": n, "exact_agreement": round(exact / n, 3), "in_out_agreement": round(inout / n, 3),
           "required": AGREEMENT_REQUIRED, "passes": inout / n >= AGREEMENT_REQUIRED, "rows": rows}
    (_dir(cfg.slug) / "audit_result.json").write_text(json.dumps(res, indent=1))
    return {k: v for k, v in res.items() if k != "rows"}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--domain", choices=sorted(M.DOMAINS), required=True)
    ap.add_argument("--stage", choices=["snowball", "prelabel", "fulltext", "slim", "audit",
                                        "audit-score", "all"], default="all")
    a = ap.parse_args()
    cfg = M.DOMAINS[a.domain]
    _dir(cfg.slug).mkdir(parents=True, exist_ok=True)
    st = a.stage
    if st in ("snowball", "all"):
        print("snowball", json.dumps(M.snowball(cfg), default=str)[:400], flush=True)
    if st in ("prelabel", "all"):
        print("prelabel", json.dumps(prelabel_dedup(cfg)), flush=True)
    if st in ("fulltext", "all"):
        r = M.retrieve_fulltext_all(cfg)
        print("fulltext", json.dumps({k: v for k, v in r.items()}), flush=True)
    if st in ("slim", "all"):
        print("slim", records.write_slim(cfg.slug), flush=True)
    if st in ("audit", "all"):
        print("audit", audit_blind(cfg), flush=True)
    if st == "audit-score":
        print("audit-score", audit_score(cfg), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
