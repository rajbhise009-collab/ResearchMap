"""Weekly growth, one library at a time.

Phase 1 (collect):  fetch the extraction batch submitted last week; bill it
                    to the ledger once (batch rate); validate + cache each
                    result; add the papers that extracted cleanly to the
                    library. Then the paid follow-on checks for the new
                    material, each gated by the week's budget: disagreement
                    check on new claim pairs, future-work matcher, method-
                    transfer confirmation. Anything a check has not reached
                    stays hidden (new disagreements show as "Flagged by the
                    system, not yet checked" and never count).
Phase 2 (submit):   pick candidates from free OpenAlex queries, keep the
                    ones the library's labelling rubric accepts, dedupe
                    (candidate rule + the full ingestion dedupe + title
                    rule), fetch open full text, and submit ONE batch whose
                    projection x1.5 fits the week's remaining budget and the
                    lifetime ledger ceiling.

LLM-calibration is not grown: its corpus is the frozen validation baseline
(tag llm-cal-baseline-v1).

Clients come in through `Clients` (real or mocked), never imported here
directly, so the whole flow runs offline in tests.
"""

from __future__ import annotations

import datetime as dt
import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from backend.app.config import REPO_ROOT

GROW_SLUGS = ("diet-and-mortality", "ml-fairness")
MAX_NEW_PER_LIBRARY = 15
LOOKBACK_DAYS = 10
EXTRACTION_MULT = 1.5        # projection padding for extraction (brief: x1.5)
CLASSIFY_MULT = 2.0          # projection padding for classification calls
FOLLOWON_WAIT_S = 45 * 60    # longest wait on a follow-on batch per run
REASON_RANK = {"cites-both": 0, "orphan-citer": 1, "snowball": 2}


class GrowStop(RuntimeError):
    """Stop cleanly: publish nothing, open an Issue with `action`."""

    def __init__(self, what: str, action: str):
        super().__init__(what)
        self.what = what
        self.action = action


@dataclass
class Clients:
    openalex: Any                       # .get(path, params) -> dict
    batch: Any                          # submit / poll / wait / results_with_usage
    embed: Any                          # .embed(list[str]) -> list[list[float]]
    llm: Any                            # .generate(prompt) -> str
    fulltext: Callable[[dict, dict], str | None]   # (entry, raw record) -> source tag
    mock: bool = False


@dataclass
class Budget:
    """This run's new commitments, in INR. Last week's batch (already
    approved last week) is recorded but does not count against this week."""
    weekly_inr: float
    committed: float = 0.0
    lines: list[dict] = field(default_factory=list)

    @property
    def remaining(self) -> float:
        return max(0.0, self.weekly_inr - self.committed)

    def fits(self, padded_inr: float) -> bool:
        return padded_inr <= self.remaining + 1e-9

    def commit(self, stage: str, projected_inr: float, mult: float) -> None:
        self.committed += projected_inr * mult
        self.lines.append({"stage": stage, "projected_inr": round(projected_inr, 4),
                           "padded_inr": round(projected_inr * mult, 4)})


def domains_dir() -> Path:
    return REPO_ROOT / "data" / "domains"


def grow_dir(slug: str) -> Path:
    return domains_dir() / slug / "grow"


def pending_path(slug: str) -> Path:
    return grow_dir(slug) / "pending.json"


def _wid(x: str) -> str:
    return (x or "").rsplit("/", 1)[-1].split(":")[-1]


def _read(p: Path) -> dict:
    return json.loads(p.read_text())


def _write(p: Path, obj: Any) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, indent=1) + "\n")


# ---------------------------------------------------------------------------
# Candidates (free OpenAlex)
# ---------------------------------------------------------------------------

_SELECT = ("id,doi,display_name,publication_year,primary_location,cited_by_count,"
           "is_retracted,is_paratext,type")


def _window(ref: dt.date, days: int) -> str:
    return (f"from_publication_date:{(ref - dt.timedelta(days=days)).isoformat()},"
            f"to_publication_date:{ref.isoformat()}")


def _query(oa, flt: str, n: int) -> list[dict]:
    body = oa.get("/works", {"filter": flt, "per-page": str(n),
                             "sort": "cited_by_count:desc", "select": _SELECT})
    return body.get("results") or []


def _library(slug: str) -> tuple[dict, list[dict], list[dict]]:
    from backend.app.corpus import records
    pre = _read(domains_dir() / slug / "prelabelled.json")
    snow = records.load(slug)
    return pre, pre["entries"], snow["records"] + snow["rejected_records"]


def find_candidates(slug: str, oa, *, ref: dt.date, lookback: int = LOOKBACK_DAYS,
                    errors: list[str]) -> list[dict]:
    """[{wid, reason, detail}] — before rubric and dedupe."""
    pre, entries, _raw = _library(slug)
    lib_wids = [e["wid"] for e in entries]
    win = _window(ref, lookback)
    found: list[dict] = []

    def add(works, reason, detail, exclude=()):
        for w in works:
            wid = _wid(w.get("id", ""))
            if wid and wid not in exclude and not w.get("is_retracted") and not w.get("is_paratext"):
                found.append({"wid": wid, "reason": reason, "detail": detail,
                              "cited_by_count": w.get("cited_by_count") or 0})

    audit = domains_dir() / slug / "reasoning" / "contradiction_audit.json"
    for v in (_read(audit).get("verdicts", []) if audit.exists() else []):
        if v.get("verdict") != "genuine":
            continue
        a, b = _wid(v["a_paper_id"]), _wid(v["b_paper_id"])
        try:
            add(_query(oa, f"cites:{a},cites:{b},{win}", 10), "cites-both",
                f"cites both sides of '{v.get('topic') or 'a disagreement'}'", (a, b))
        except Exception as e:  # noqa: BLE001
            errors.append(f"{slug}: OpenAlex cites-both {a}+{b}: {type(e).__name__}")

    opps = REPO_ROOT / "frontend" / "public" / "data" / "library" / slug / "opportunities.json"
    sources = []
    for c in (_read(opps).get("items", []) if opps.exists() else []):
        if (c.get("consumer") or {}).get("kind_id") == "unfollowed_future_work":
            sp = c.get("supporting_papers") or []
            if sp:
                pid = sp[0].get("paper_id") if isinstance(sp[0], dict) else sp[0]
                if pid and _wid(pid) not in sources:
                    sources.append(_wid(pid))
    for k in range(0, len(sources), 50):
        chunk = sources[k:k + 50]
        try:
            add(_query(oa, f"cites:{'|'.join(chunk)},{win}", 25), "orphan-citer",
                "cites a paper whose open question is not yet followed up", chunk)
        except Exception as e:  # noqa: BLE001
            errors.append(f"{slug}: OpenAlex orphan-citer: {type(e).__name__}")

    for k in range(0, len(lib_wids), 50):
        chunk = lib_wids[k:k + 50]
        try:
            add(_query(oa, f"cites:{'|'.join(chunk)},{win}", 25), "snowball",
                "cites papers in this library", chunk)
        except Exception as e:  # noqa: BLE001
            errors.append(f"{slug}: OpenAlex snowball: {type(e).__name__}")
    # keep each wid once, under its strongest reason
    best: dict[str, dict] = {}
    for c in found:
        if c["wid"] not in best or REASON_RANK[c["reason"]] < REASON_RANK[best[c["wid"]]["reason"]]:
            best[c["wid"]] = c
    return list(best.values())


def fetch_records(oa, wids: list[str]) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for k in range(0, len(wids), 50):
        body = oa.get("/works", {"filter": "openalex_id:" + "|".join(wids[k:k + 50]),
                                 "per-page": "50"})
        for r in body.get("results") or []:
            out[_wid(r.get("id", ""))] = r
    return out


def _entry(rec: dict, cand: dict, label: str, rationale: str, ref: dt.date) -> dict:
    from backend.app.corpus.multi_domain import _abstract_of, _field_of, _venue_of
    return {
        "wid": _wid(rec.get("id", "")), "openalex_id": rec.get("id"),
        "title": rec.get("title") or rec.get("display_name"),
        "year": rec.get("publication_year"), "doi": rec.get("doi"),
        "venue": _venue_of(rec), "field": _field_of(rec),
        "cited_by_count": rec.get("cited_by_count"), "abstract": _abstract_of(rec),
        "label": label, "rationale": rationale, "domain_centrality": "core",
        "added_by": "weekly-grow", "added_on": ref.isoformat(),
        "found_via": cand["reason"], "found_via_detail": cand["detail"],
    }


def select(slug: str, cands: list[dict], records: dict[str, dict], *,
           ref: dt.date) -> tuple[list[tuple[dict, dict]], dict]:
    """Rubric, then dedupe; ranked. Returns ([(entry, raw)], drop counts)."""
    from collections import Counter

    from backend.app.corpus.multi_domain import DOMAINS, _abstract_of, classify
    from backend.app.ingestion.normalizer import deduplicate, from_openalex, normalize_title
    from backend.app.refresh.weekly_candidates import Candidate, _dedupe_candidates
    cfg = DOMAINS[slug]
    pre, entries, raw = _library(slug)
    drops: Counter = Counter()
    known_wids = {e["wid"] for e in entries} | {_wid(m) for e in entries for m in e.get("merged_from", [])}
    pend = pending_path(slug)
    if pend.exists():
        known_wids |= {e["wid"] for e in _read(pend)["entries"]}
    known_dois = {(e.get("doi") or "").lower().removeprefix("https://doi.org/") for e in entries} - {""}
    known_titles = {normalize_title(e.get("title") or "") for e in entries} - {""}

    kept: list[tuple[dict, dict]] = []
    for c in sorted(cands, key=lambda c: (REASON_RANK[c["reason"]], -c["cited_by_count"], c["wid"])):
        rec = records.get(c["wid"])
        if rec is None:
            drops["record not returned"] += 1
            continue
        label, why = classify(rec, abstract=_abstract_of(rec), config=cfg)
        if label != "on-domain":
            drops[f"rubric: {label}"] += 1
            continue
        kept.append((_entry(rec, c, label, why, ref), rec))

    # 1. candidate rule (wid, DOI, title+year, title>=25 chars)
    cobjs = [Candidate(wid=e["wid"], title=e["title"] or "", year=e["year"],
                       doi=(e.get("doi") or "").lower().removeprefix("https://doi.org/") or None,
                       oa_url=None, reason=e["found_via"], library=slug) for e, _r in kept]
    keep_w = {c.wid for c in _dedupe_candidates(cobjs)}
    drops["duplicate among candidates"] += len(kept) - len(keep_w)
    kept = [(e, r) for e, r in kept if e["wid"] in keep_w]
    # 2. against the library: id, merged-loser id, DOI, title rule
    out = []
    for e, r in kept:
        doi = (e.get("doi") or "").lower().removeprefix("https://doi.org/")
        if e["wid"] in known_wids or (doi and doi in known_dois) \
                or normalize_title(e["title"] or "") in known_titles:
            drops["already in library (id/DOI/title)"] += 1
            continue
        out.append((e, r))
    # 3. the full ingestion dedupe (DOI, title+year+author, cross-year,
    #    arXiv<->published, title similarity) against library + accepted
    lib_papers = [from_openalex(r) for r in raw if _wid(r.get("id", "")) in known_wids]
    base = len(deduplicate(lib_papers))
    accepted: list[tuple[dict, dict]] = []
    for e, r in out:
        trial = lib_papers + [from_openalex(x) for _e, x in accepted] + [from_openalex(r)]
        if len(deduplicate(trial)) != base + len(accepted) + 1:
            drops["duplicate by ingestion dedupe"] += 1
            continue
        accepted.append((e, r))
    drops["over weekly per-library cap"] += max(0, len(accepted) - MAX_NEW_PER_LIBRARY)
    return accepted[:MAX_NEW_PER_LIBRARY], dict(drops)


# ---------------------------------------------------------------------------
# Phase 2: submit
# ---------------------------------------------------------------------------

def _prompt_for(entry: dict) -> tuple[str, str, float]:
    from backend.app.corpus.multi_domain_extract import (
        OUT_TOKENS_ABSTRACT, OUT_TOKENS_FULLTEXT, _paper_from_entry, cost,
    )
    from backend.app.corpus.run_batch_corpus import _make_renderer
    from backend.app.extraction.rate_limiter import estimate_tokens
    paper = _paper_from_entry(entry)
    src = "fulltext" if entry.get("input_source") == "fulltext" and paper.fulltext else "abstract"
    prompt = _make_renderer(src)._render(paper)
    out_t = OUT_TOKENS_FULLTEXT if src == "fulltext" else OUT_TOKENS_ABSTRACT
    return prompt, src, cost(estimate_tokens(prompt), out_t, batch=True) * 84.0


def submit(slug: str, cl: Clients, budget: Budget, *, ref: dt.date,
           errors: list[str]) -> dict:
    if pending_path(slug).exists():
        return {"slug": slug, "submitted": 0, "note": "last batch not collected yet"}
    cands = find_candidates(slug, cl.openalex, ref=ref, errors=errors)
    records = fetch_records(cl.openalex, [c["wid"] for c in cands]) if cands else {}
    chosen, drops = select(slug, cands, records, ref=ref)
    for e, r in chosen:
        try:
            src = cl.fulltext(e, r)
        except Exception as ex:  # noqa: BLE001
            errors.append(f"{slug}: full text {e['wid']}: {type(ex).__name__}")
            src = None
        e["input_source"] = "fulltext" if src else "abstract_only"
        e["fulltext_source"] = src
        e["abstract_only"] = not src
    prompts, sources, entries, raws, proj = {}, {}, [], [], 0.0
    for e, r in chosen:
        p, src, inr = _prompt_for(e)
        if not budget.fits((proj + inr) * EXTRACTION_MULT):
            drops["over weekly budget"] = drops.get("over weekly budget", 0) + 1
            continue
        pid = f"openalex:{e['wid']}"
        prompts[pid], sources[pid] = p, src
        entries.append(e)
        raws.append(r)
        proj += inr
    res = {"slug": slug, "candidates": len(cands), "dropped": drops, "submitted": len(prompts),
           "projected_inr": round(proj, 4)}
    if not prompts:
        return res
    from backend.app.extraction.spend_gate import preflight
    from backend.app.extraction.spend_ledger import SpendLedger
    preflight(stage=f"grow_extract_{slug}", projected_inr=proj, n_calls=len(prompts),
              multiplier=EXTRACTION_MULT)               # lifetime ceiling, recorded
    SpendLedger.load()                                  # ledger readable before paying
    bid = cl.batch.submit(prompts, display_name=f"researchmap-grow-{slug}")
    budget.commit(f"extract_{slug}", proj, EXTRACTION_MULT)
    _write(pending_path(slug), {
        "batch_id": bid, "slug": slug, "submitted_on": ref.isoformat(),
        "submitted_at": time.time(), "projected_inr": proj, "ledger_recorded": False,
        "input_source": sources, "entries": entries, "records": raws})
    res["batch_id"] = bid
    res["titles"] = [e["title"] for e in entries]
    return res


# ---------------------------------------------------------------------------
# Phase 1: collect
# ---------------------------------------------------------------------------

def collect(slug: str, cl: Clients, *, ref: dt.date) -> dict:
    from backend.app.corpus.multi_domain_extract import MODEL_ID, _paper_from_entry
    from backend.app.corpus.run_batch_corpus import _validate_and_cache
    from backend.app.extraction.batch_client import record_batch_usage
    from backend.app.extraction.cache import ExtractionCache
    sp = pending_path(slug)
    if not sp.exists():
        return {"slug": slug, "status": "nothing pending", "added": []}
    st = _read(sp)
    job = cl.batch.poll(st["batch_id"])
    if not job.done:
        return {"slug": slug, "status": "pending", "state": job.state, "added": []}
    hist = grow_dir(slug) / "history" / f"{st['submitted_on']}-{st['batch_id'].rsplit('/', 1)[-1]}.json"
    if not job.succeeded:
        st["outcome"] = {"state": job.state, "collected_on": ref.isoformat()}
        _write(hist, st)
        sp.unlink()
        return {"slug": slug, "status": "failed", "state": job.state, "added": []}
    with_usage = cl.batch.results_with_usage(job)
    if not st.get("ledger_recorded"):
        st["recorded_inr"] = record_batch_usage(
            with_usage, stage=f"grow_extract_{slug}_batch", model=MODEL_ID.split(":", 1)[1])
        st["ledger_recorded"] = True
        _write(sp, st)                       # billed once, even if the rest fails
    cache = ExtractionCache()
    by_pid = {f"openalex:{e['wid']}": (e, r) for e, r in zip(st["entries"], st["records"])}
    added, fails = [], []
    for pid, (text, _u) in sorted(with_usage.items()):
        if pid not in by_pid:
            fails.append((pid, "unknown-paper"))
            continue
        e, _r = by_pid[pid]
        out = _validate_and_cache(_paper_from_entry(e), text,
                                  src=st["input_source"].get(pid, "abstract"),
                                  model=MODEL_ID, cache=cache)
        (added if out == "ok" else fails).append(pid if out == "ok" else (pid, out))
    for pid in sorted(set(st["input_source"]) - set(with_usage)):
        fails.append((pid, "no-result-returned"))
    if added:
        pre_p = domains_dir() / slug / "prelabelled.json"
        pre = _read(pre_p)
        have = {e["wid"] for e in pre["entries"]}
        new_recs = []
        for pid in added:
            e, r = by_pid[pid]
            if e["wid"] in have:
                continue
            pre["entries"].append(e)
            new_recs.append(r)
        pre["n_kept"] = len(pre["entries"])
        pre_p.write_text(json.dumps(pre))
        from backend.app.corpus import records
        records.append(slug, new_recs)
    st["outcome"] = {"state": job.state, "collected_on": ref.isoformat(),
                     "added": added, "failed": fails}
    _write(hist, st)
    sp.unlink()
    return {"slug": slug, "status": "collected", "recorded_inr": round(st["recorded_inr"], 4),
            "added": added, "added_titles": [by_pid[p][0]["title"] for p in added],
            "failed": fails}


# ---------------------------------------------------------------------------
# Phase 1b: paid follow-on checks for new material (each budget-gated)
# ---------------------------------------------------------------------------

def followon(slug: str, cl: Clients, budget: Budget) -> dict:
    from backend.app.corpus import multi_domain_reason as R
    from backend.app.corpus.multi_domain_reason_incremental import write_coverage
    from backend.app.reasoning import run_library_scorers as S
    from backend.app.reasoning.library_corpus import embed_future_work
    out: dict[str, Any] = {"slug": slug}

    # a. disagreement check on new claim pairs (new claims embedded first;
    #    embeddings are fractions of a paisa and ledgered by the client)
    exts = R.load_extractions(slug)
    pairs = R.compute_shortlist(exts, use_real_embeddings=True, slug=slug, embed_client=cl.embed)
    done = R.load_classified_keys(slug)
    unseen = [p for p in pairs if (p.from_claim_id, p.to_claim_id) not in done]
    per = R.projected_inr_per_pair()
    n_fit = min(len(unseen), int(budget.remaining / (per * CLASSIFY_MULT))) if per > 0 else len(unseen)
    todo = unseen[:n_fit]
    if todo:
        if hasattr(cl.llm, "set_run_context"):
            from backend.app.extraction.pricing import OUT_TOKENS_PAIR
            cl.llm.set_run_context(stage=f"grow_contradiction_{slug}",
                                   est_output_tokens=OUT_TOKENS_PAIR)
        r = R.classify_pairs(slug, exts, todo, llm=cl.llm)
        budget.commit(f"disagreement_{slug}", per * len(todo), CLASSIFY_MULT)
        out["disagreement"] = {"classified": r["stats"].get("calls", 0),
                               "new_flagged": r["stats"].get("contradicts", 0),
                               "halted": r["halted"]}
    out["disagreement_unchecked_pairs"] = len(unseen) - len(todo)
    write_coverage(slug, exts, pairs, threshold=R.LIBRARY_THRESHOLD,
                   max_per_claim=R.LIBRARY_MAX_PER_CLAIM,
                   note="updated by the weekly growth run")

    # b. future-work matcher (embed new items, then classify new pairs)
    dry = embed_future_work(slug, dry_run=True)
    if dry["to_embed"]:
        if budget.fits(dry["projected_inr"] * EXTRACTION_MULT):
            embed_future_work(slug, dry_run=False, client=cl.embed)
            budget.commit(f"embed_fw_{slug}", dry["projected_inr"], EXTRACTION_MULT)
        else:
            out["fw_embed"] = "skipped: over weekly budget"
    fwd = S.fwmatch(slug, dry_run=True)
    if fwd["to_classify"] or S._state(slug, "fw_match").exists():
        if S._state(slug, "fw_match").exists() or budget.fits(fwd["projected_inr"] * CLASSIFY_MULT):
            if not S._state(slug, "fw_match").exists():
                budget.commit(f"fw_match_{slug}", fwd["projected_inr"], CLASSIFY_MULT)
            try:
                out["fw_match"] = S.fwmatch(slug, dry_run=False, client=cl.batch,
                                            wait_timeout_s=FOLLOWON_WAIT_S)
            except S.BatchPending as e:
                out["fw_match"] = f"pending: {e}"
        else:
            out["fw_match"] = "skipped: over weekly budget"
    else:
        # nothing to classify: every embedded item has been looked at
        from backend.app.reasoning.library_corpus import load_library_corpus, mark_fw_checked
        mark_fw_checked(slug, load_library_corpus(slug).fw_ids)

    # c. confirmation of method-transfer leads (unconfirmed leads stay hidden)
    cd = S.confirm(slug, dry_run=True)
    if cd["to_confirm"] or S._state(slug, "hole_confirm").exists():
        if S._state(slug, "hole_confirm").exists() or budget.fits(cd["projected_inr"] * CLASSIFY_MULT):
            if not S._state(slug, "hole_confirm").exists():
                budget.commit(f"hole_confirm_{slug}", cd["projected_inr"], CLASSIFY_MULT)
            try:
                out["confirm"] = S.confirm(slug, dry_run=False, client=cl.batch,
                                           wait_timeout_s=FOLLOWON_WAIT_S)
            except S.BatchPending as e:
                out["confirm"] = f"pending: {e}"
        else:
            out["confirm"] = "skipped: over weekly budget"
    return out
