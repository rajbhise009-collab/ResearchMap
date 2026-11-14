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
Phase 2 (submit):   pick candidates from free OpenAlex filter queries in
                    widening tiers (search: recent citers, then the forward
                    and backward citation snowball, then the library's own
                    vocabulary by year), keep the ones the library's
                    labelling rubric AND core scope accept, dedupe
                    (candidate rule + the full ingestion dedupe + title
                    rule), fetch open full text, and submit ONE batch whose
                    projection x1.5 fits the run's budget and the lifetime
                    ledger ceiling (mode batch), or extract the papers in
                    this run (mode sync, about 2x the cost: extract_sync).

Libraries grown: every built, non-frozen library in data/library_registry.json.
LLM-calibration is frozen: its corpus is the validation baseline (tag
llm-cal-baseline-v1).

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
from backend.app.grow.plan import SYNC_COST_FACTOR

def grow_slugs() -> tuple[str, ...]:
    """Every built, non-frozen library (data/library_registry.json).
    LLM calibration is frozen: the validation baseline."""
    from backend.app.api import registry
    return tuple(registry.growable())
MAX_NEW_PER_LIBRARY = 15     # default need of one library when none is given
LOOKBACK_DAYS = 10
EXTRACTION_MULT = 1.5        # projection padding for extraction (brief: x1.5)
CLASSIFY_MULT = 2.0          # projection padding for classification calls
FOLLOWON_WAIT_S = 45 * 60    # longest wait on a follow-on batch per run
GATE_RESERVE_S = 80 * 60     # run time kept back for regenerating, every gate and the publish
REASON_RANK = {"cites-both": 0, "orphan-citer": 1, "snowball": 2, "snowball-forward": 3,
               "snowball-backward": 4, "vocabulary": 5}
SEARCH_TIERS = ("recent", "forward", "backward", "vocabulary")
LIST_PER_PAGE = 200          # OpenAlex's maximum for a filter list
FETCH_CHUNK = 50             # records fetched per openalex_id call


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
    body = with_retry(lambda: oa.get("/works", {"filter": flt, "per-page": str(n),
                                                "sort": "cited_by_count:desc", "select": _SELECT}))
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


class CallBudget:
    """Counts this run's OpenAlex calls (all libraries together) and stops
    the search at openalex_max_calls_per_run. Wraps any client with .get."""

    class Spent(RuntimeError):
        pass

    def __init__(self, oa, max_calls: int):
        self.oa, self.max_calls, self.calls = oa, max_calls, 0

    @property
    def left(self) -> int:
        return max(0, self.max_calls - self.calls)

    def get(self, path: str, params: dict) -> dict:
        if self.calls >= self.max_calls:
            raise CallBudget.Spent(f"OpenAlex call budget for this run used ({self.max_calls} calls)")
        self.calls += 1
        return self.oa.get(path, params)


def _list(oa, flt: str, *, sort: str = "cited_by_count:desc", pages: int = 1) -> list[dict]:
    out: list[dict] = []
    for page in range(1, pages + 1):
        body = with_retry(lambda: oa.get("/works", {"filter": flt, "per-page": str(LIST_PER_PAGE), "page": str(page),
                                                    "sort": sort, "select": _SELECT}))
        res = body.get("results") or []
        out += res
        if len(res) < LIST_PER_PAGE:
            break
    return out


def _cand(w: dict, reason: str, detail: str) -> dict | None:
    wid = _wid(w.get("id", ""))
    if not wid or w.get("is_retracted") or w.get("is_paratext"):
        return None
    return {"wid": wid, "reason": reason, "detail": detail, "cited_by_count": w.get("cited_by_count") or 0}


_YEAR_RX = None


def _without_year(flt: str) -> str:
    """The domain's seed filter with its own publication-year limit removed,
    so each vocabulary query can set its own year slice."""
    import re
    global _YEAR_RX
    _YEAR_RX = _YEAR_RX or re.compile(r",?publication_year:[^,]*")
    return _YEAR_RX.sub("", flt).strip(",")


def tier_candidates(tier: str, slug: str, oa, *, ref: dt.date, errors: list[str]) -> list[dict]:
    """Candidates of one widening search tier, before rubric and dedupe.
    Every call is an OpenAlex filter list (1 credit each), never search=.

      recent      find_candidates: citers of the library's disagreements,
                  open questions and papers, published in the last 10 days
      forward     papers citing the library's papers: the last two years
                  first (newest first), then all years (most cited first)
      backward    works the library's papers cite, most co-cited first (older
                  foundational papers the library is missing)
      vocabulary  the library's own seed query (its rubric's strong terms and
                  outcome terms) by year slice: the last two years, then 3-5
                  and 6-10 years back, most cited first
    """
    if tier == "recent":
        return find_candidates(slug, oa, ref=ref, errors=errors)
    _pre, entries, raw = _library(slug)
    lib = sorted({e["wid"] for e in entries})
    out: list[dict] = []
    if tier == "forward":
        since = (ref - dt.timedelta(days=730)).isoformat()
        for flt_extra, sort, why in ((f",from_publication_date:{since}", "publication_date:desc",
                                      "cites papers in this library (last two years)"),
                                     ("", "cited_by_count:desc", "cites papers in this library (any year)")):
            for k in range(0, len(lib), 50):
                chunk = lib[k:k + 50]
                try:
                    for w in _list(oa, f"cites:{'|'.join(chunk)}{flt_extra}", sort=sort):
                        c = _cand(w, "snowball-forward", why)
                        if c and c["wid"] not in chunk:
                            out.append(c)
                except CallBudget.Spent:
                    raise
                except Exception as e:  # noqa: BLE001
                    errors.append(f"{slug}: OpenAlex forward snowball: {type(e).__name__}")
        return out
    if tier == "backward":
        from collections import Counter
        have = set(lib)
        refs: Counter = Counter()
        for r in raw:
            if _wid(r.get("id", "")) in have:
                refs.update({_wid(x) for x in r.get("referenced_works") or []} - have - {""})
        ranked = [w for w, _n in refs.most_common()]
        recs = fetch_records(oa, ranked[:4 * FETCH_CHUNK])
        for w in ranked[:4 * FETCH_CHUNK]:
            if w in recs:
                c = _cand(recs[w], "snowball-backward", f"cited by {refs[w]} paper(s) in this library")
                if c:
                    c["record"] = recs[w]
                    out.append(c)
        return out
    if tier == "vocabulary":
        from backend.app.corpus.multi_domain_reason import DOMAINS
        base = _without_year(DOMAINS[slug].seed_filter)
        y = ref.year
        for y0, y1 in ((y - 1, y), (y - 5, y - 2), (y - 10, y - 6)):
            try:
                for w in _list(oa, f"{base},publication_year:{y0}-{y1}"):
                    c = _cand(w, "vocabulary", f"matches this library's own search terms ({y0}-{y1})")
                    if c:
                        out.append(c)
            except CallBudget.Spent:
                raise
            except Exception as e:  # noqa: BLE001
                errors.append(f"{slug}: OpenAlex vocabulary {y0}-{y1}: {type(e).__name__}")
        return out
    raise ValueError(f"unknown search tier {tier!r}")


def search(slug: str, oa, *, ref: dt.date, need: int, errors: list[str]) -> dict:
    """Widen the search tier by tier until the library has `need` in-scope,
    deduplicated candidates, or every tier has been tried (exhausted). The
    rubric, core scope and dedupe are exactly select()'s; nothing is loosened.
    Records are fetched best-first in chunks, and fetching stops once enough
    candidates are kept. Returns {chosen, records, funnel}; funnel reports,
    per tier and in total, the candidates seen, kept and dropped by reason."""
    seen: dict[str, dict] = {}
    records: dict[str, dict] = {}
    tried: set[str] = set()          # wids whose record was fetched (or asked for)
    tiers: list[dict] = []
    chosen: list[tuple[dict, dict]] = []
    drops: dict = {}
    stopped = None
    for tier in SEARCH_TIERS:
        if len(chosen) >= need:
            break
        kept_before = len(chosen)
        try:
            new = [c for c in tier_candidates(tier, slug, oa, ref=ref, errors=errors) if c["wid"] not in seen]
        except CallBudget.Spent as e:
            stopped = str(e)
            break
        best: dict[str, dict] = {}
        for c in new:
            if c["wid"] not in best or REASON_RANK[c["reason"]] < REASON_RANK[best[c["wid"]]["reason"]]:
                best[c["wid"]] = c
        new = sorted(best.values(), key=lambda c: (REASON_RANK[c["reason"]], -c["cited_by_count"], c["wid"]))
        for c in new:
            if "record" in c:
                records[c["wid"]] = c.pop("record")
                tried.add(c["wid"])
        seen.update({c["wid"]: c for c in new})
        todo = [c["wid"] for c in new if c["wid"] not in records]
        for k in range(0, max(1, len(todo)), FETCH_CHUNK):
            chunk = todo[k:k + FETCH_CHUNK]
            if chunk:
                try:
                    records.update(fetch_records(oa, chunk))
                except CallBudget.Spent as e:
                    stopped = str(e)
                    break
                tried.update(chunk)
            chosen, drops = select(slug, [c for c in seen.values() if c["wid"] in tried], records,
                                   ref=ref, cap=need)
            if len(chosen) >= need:
                break
        tiers.append({"tier": tier, "seen": len(new), "kept": len(chosen) - kept_before})
        if stopped:
            break
    if not seen:
        chosen, drops = [], {}
    drops = dict(drops)
    if len(seen) > len(tried):
        drops["not examined (enough found, or the search stopped)"] = len(seen) - len(tried)
    exhausted = len(chosen) < need and stopped is None
    funnel = {"need": need, "seen": len(seen), "kept": len(chosen), "dropped": drops, "tiers": tiers,
              "exhausted": exhausted, "stopped": stopped,
              "short": max(0, need - len(chosen))}
    return {"chosen": chosen, "records": records, "funnel": funnel}


def fetch_records(oa, wids: list[str]) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for k in range(0, len(wids), 50):
        body = with_retry(lambda: oa.get("/works", {"filter": "openalex_id:" + "|".join(wids[k:k + 50]),
                                                    "per-page": "50"}))
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
           ref: dt.date, cap: int = MAX_NEW_PER_LIBRARY) -> tuple[list[tuple[dict, dict]], dict]:
    """Rubric, then dedupe; ranked; at most `cap` (this run's need for the
    library). Returns ([(entry, raw)], drop counts)."""
    from collections import Counter

    from backend.app.corpus.multi_domain import _abstract_of, classify
    from backend.app.corpus.multi_domain_reason import DOMAINS   # short and full slugs
    from backend.app.grow.scope import core_scope
    from backend.app.ingestion.normalizer import deduplicate, from_openalex, normalize_title
    from backend.app.refresh.weekly_candidates import Candidate, _dedupe_candidates
    cfg = DOMAINS[slug]
    pre, entries, raw = _library(slug)
    drops: Counter = Counter()
    known_wids = {e["wid"] for e in entries} | {_wid(m) for e in entries for m in e.get("merged_from", [])}
    # papers the owner removed from the library never re-enter
    removed_wids = {r["wid"] for r in pre.get("removed", [])}
    pend = pending_path(slug)
    if pend.exists():
        known_wids |= {e["wid"] for e in _read(pend)["entries"]}
    known_dois = {(e.get("doi") or "").lower().removeprefix("https://doi.org/") for e in entries} - {""}
    known_titles = {normalize_title(e.get("title") or "") for e in entries} - {""}

    kept: list[tuple[dict, dict]] = []
    for c in sorted(cands, key=lambda c: (REASON_RANK[c["reason"]], -c["cited_by_count"], c["wid"])):
        if c["wid"] in removed_wids:
            drops["removed from the library by the owner"] += 1
            continue
        rec = records.get(c["wid"])
        if rec is None:
            drops["record not returned"] += 1
            continue
        label, why = classify(rec, abstract=_abstract_of(rec), config=cfg)
        if label != "on-domain":                 # borderline is excluded from weekly growth
            drops[f"rubric: {label}"] += 1
            continue
        ok, scope_why = core_scope(slug, rec.get("title") or rec.get("display_name") or "", _abstract_of(rec))
        if not ok:                               # the domain's core population and outcome
            drops["outside the core scope"] += 1
            continue
        kept.append((_entry(rec, c, label, f"{why}; core scope: {scope_why}", ref), rec))

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
    drops["beyond this run's need for the library"] += max(0, len(accepted) - cap)
    return accepted[:cap], {k: v for k, v in drops.items() if v}


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


def prepare(slug: str, cl: Clients, *, ref: dt.date, errors: list[str], need: int = MAX_NEW_PER_LIBRARY,
            oa=None) -> dict:
    """Free: widening search (search) -> rubric -> core scope -> dedupe ->
    full text -> rendered prompts with per-paper projections (batch and
    sync), best first. Nothing is submitted here. `oa`: the run's
    CallBudget-wrapped client (default: the clients' own)."""
    if pending_path(slug).exists():
        return {"slug": slug, "items": [], "candidates": 0, "dropped": {},
                "note": "last batch not collected yet",
                "funnel": {"need": need, "seen": 0, "kept": 0, "dropped": {}, "tiers": [], "exhausted": False,
                           "stopped": "its last batch is not collected yet (no new search)", "short": 0}}
    if need <= 0:
        return {"slug": slug, "items": [], "candidates": 0, "dropped": {}, "note": "no share this run",
                "funnel": {"need": 0, "seen": 0, "kept": 0, "dropped": {}, "tiers": [], "exhausted": False,
                           "stopped": None, "short": 0}}
    found = search(slug, oa or cl.openalex, ref=ref, need=need, errors=errors)
    chosen, drops, funnel = found["chosen"], found["funnel"]["dropped"], found["funnel"]
    items = []
    for e, r in chosen:
        try:
            src = cl.fulltext(e, r)
        except Exception as ex:  # noqa: BLE001
            errors.append(f"{slug}: full text {e['wid']}: {type(ex).__name__}")
            src = None
        e["input_source"] = "fulltext" if src else "abstract_only"
        e["fulltext_source"] = src
        e["abstract_only"] = not src
        prompt, src2, inr = _prompt_for(e)
        items.append({"entry": e, "record": r, "prompt": prompt, "src": src2, "inr": inr,
                      "inr_sync": inr * SYNC_COST_FACTOR})
    return {"slug": slug, "items": items, "candidates": funnel["seen"], "dropped": drops, "funnel": funnel}


# ---------------------------------------------------------------------------
# Fairness: no library is starved by a fixed order.
#   data/grow/fairness.json  {slug: {"extraction_served": date, "followon_served": date,
#                                    "followon_owed": [step, ...]}}
# Each week the library served longest ago goes first (never served = first);
# a library whose follow-on checks were skipped (budget) is owed them and goes
# first in next week's follow-on phase. Skipped work is recomputed next run
# (unchecked pairs, unembedded items), so nothing is lost, only delayed.

def fairness_path() -> Path:
    return domains_dir().parent / "grow" / "fairness.json"


def load_fairness() -> dict:
    p = fairness_path()
    return json.loads(p.read_text()) if p.exists() else {}


def fair_order(slugs, kind: str, *, papers: dict[str, int] | None = None,
               candidates: dict[str, int] | None = None) -> list[str]:
    """kind: "extraction" or "followon"."""
    f = load_fairness()
    papers, candidates = papers or {}, candidates or {}

    def key(s):
        st = f.get(s, {})
        owed = 0 if (kind == "followon" and st.get("followon_owed")) else 1
        return (owed, st.get(f"{kind}_served") or "0000-00-00", -candidates.get(s, 0), papers.get(s, 0), s)
    return sorted(slugs, key=key)


def record_fairness(slug: str, kind: str, *, served: bool, ref: dt.date, owed: list[str] | None = None) -> None:
    f = load_fairness()
    st = f.setdefault(slug, {})
    if served:
        st[f"{kind}_served"] = ref.isoformat()
    if kind == "followon":
        st["followon_owed"] = list(owed or [])
    p = fairness_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(f, indent=1, sort_keys=True) + "\n")


def followon_owed(r: dict) -> list[str]:
    """Follow-on steps skipped for money this run (carried over)."""
    owed = [k for k, v in r.items() if isinstance(v, str) and v.startswith("skipped")]
    if r.get("disagreement_unchecked_pairs"):
        owed.append("disagreement")
    if r.get("money_refused"):
        owed.append("all (money rule)")
    return owed


def allocate(prepared: dict[str, dict], budget: Budget, papers: dict[str, int],
             order: list[str] | None = None, *, target: int | None = None,
             mode: str = "batch") -> dict[str, list[dict]]:
    """Round-robin across libraries, one paper per library per round, until
    the run's target is reached or its budget (padded x1.5) is spent. A
    library that ran out of candidates simply drops out of later rounds, so
    the others fill its share. Library order each round: the fair order
    (served longest ago first; see fair_order), else most open candidates
    first, then fewest papers (lowest coverage). mode sync prices each paper
    at the interactive rate (about 2x)."""
    key = "inr_sync" if mode == "sync" else "inr"
    order = [s for s in (order or []) if s in prepared] or \
        sorted(prepared, key=lambda s: (-len(prepared[s]["items"]), papers.get(s, 0), s))
    picked: dict[str, list[dict]] = {s: [] for s in prepared}
    total, n = 0.0, 0
    for rnd in range(max((len(p["items"]) for p in prepared.values()), default=0)):
        for s in order:
            items = prepared[s]["items"]
            if rnd >= len(items):
                continue
            it = items[rnd]
            cost = it.get(key, it["inr"] * (SYNC_COST_FACTOR if mode == "sync" else 1.0))
            d = prepared[s]["dropped"]
            if target is not None and n >= target:
                d["beyond the run's target"] = d.get("beyond the run's target", 0) + 1
            elif budget.fits((total + cost) * EXTRACTION_MULT):
                picked[s].append(it)
                total += cost
                n += 1
            else:
                d["over this run's budget"] = d.get("over this run's budget", 0) + 1
    return picked


def submit(slug: str, cl: Clients, budget: Budget, items: list[dict], *, ref: dt.date) -> dict:
    """Submit ONE extraction batch for the allocated papers (paid)."""
    proj = sum(it["inr"] for it in items)
    res = {"slug": slug, "submitted": len(items), "projected_inr": round(proj, 4)}
    if not items:
        return res
    from backend.app.extraction.spend_gate import preflight
    preflight(stage=f"grow_extract_{slug}", projected_inr=proj, n_calls=len(items),
              multiplier=EXTRACTION_MULT)               # money rule, recorded
    prompts = {f"openalex:{it['entry']['wid']}": it["prompt"] for it in items}
    bid = with_retry(lambda: cl.batch.submit(prompts, display_name=f"researchmap-grow-{slug}"))
    budget.commit(f"extract_{slug}", proj, EXTRACTION_MULT)
    _write(pending_path(slug), {
        "batch_id": bid, "slug": slug, "submitted_on": ref.isoformat(),
        "submitted_at": time.time(), "projected_inr": proj, "ledger_recorded": False,
        "input_source": {f"openalex:{it['entry']['wid']}": it["src"] for it in items},
        "entries": [it["entry"] for it in items], "records": [it["record"] for it in items]})
    res["batch_id"] = bid
    res["titles"] = [it["entry"]["title"] for it in items]
    return res


def with_retry(fn, *, tries: int = 4, base_s: float | None = None):
    """Self-heal transient API errors (timeouts, 429, 5xx) with backoff."""
    import os
    base = float(os.environ.get("GROW_RETRY_BASE_S", "20")) if base_s is None else base_s
    for k in range(tries):
        try:
            return fn()
        except Exception as e:  # noqa: BLE001
            transient = any(t in f"{type(e).__name__} {e}" for t in
                            ("Timeout", "ConnectError", "429", " 50", "503", "502", "500", "Unavailable",
                             "RemoteProtocolError", "ReadError"))
            if not transient or k == tries - 1:
                raise
            time.sleep(base * (2 ** k))


# ---------------------------------------------------------------------------
# Phase 1: collect
# ---------------------------------------------------------------------------

def add_to_library(slug: str, pairs: list[tuple[dict, dict]], *, ref: dt.date | None = None,
                   excluded: list[dict] | None = None) -> list[str]:
    """Append collected (entry, record) pairs to the library. A paper already
    in it, or removed from it by the owner, is never (re-)added. A paper that
    was paid for but fails the core scope at collection (it was submitted
    before the rule, or the rule changed) is kept on file under
    "scope_excluded" — never deleted, never published — and reported in
    `excluded` for the weekly Issue. Returns the wids added."""
    from backend.app.grow.scope import core_scope
    pre_p = domains_dir() / slug / "prelabelled.json"
    pre = _read(pre_p)
    have = ({e["wid"] for e in pre["entries"]} | {r["wid"] for r in pre.get("removed", [])}
            | {r["wid"] for r in pre.get("scope_excluded", [])})
    new_recs, wids = [], []
    for e, r in pairs:
        if e["wid"] in have:
            continue
        try:
            ok, why = core_scope(slug, e.get("title") or "", e.get("abstract"))
        except Exception as ex:  # noqa: BLE001  (a scope check must never block a run)
            ok, why = True, f"scope check failed ({type(ex).__name__}); kept"
        new_recs.append(r)              # the record is kept either way
        if not ok:
            x = {"wid": e["wid"], "title": e.get("title"), "reason": why,
                 "collected_on": (ref or dt.date.today()).isoformat(), "entry": e}
            pre.setdefault("scope_excluded", []).append(x)
            if excluded is not None:
                excluded.append({k: v for k, v in x.items() if k != "entry"})
            continue
        pre["entries"].append(e)
        wids.append(e["wid"])
    pre["n_kept"] = len(pre["entries"])
    pre_p.write_text(json.dumps(pre))
    from backend.app.corpus import records
    records.append(slug, new_recs)
    return wids


def collect(slug: str, cl: Clients, *, ref: dt.date) -> dict:
    from backend.app.corpus.multi_domain_extract import MODEL_ID, _paper_from_entry
    from backend.app.corpus.run_batch_corpus import _validate_and_cache
    from backend.app.extraction.batch_client import record_batch_usage
    from backend.app.extraction.cache import ExtractionCache
    sp = pending_path(slug)
    if not sp.exists():
        return {"slug": slug, "status": "nothing pending", "added": []}
    st = _read(sp)
    job = with_retry(lambda: cl.batch.poll(st["batch_id"]))
    if not job.done:
        return {"slug": slug, "status": "pending", "state": job.state, "added": []}
    hist = grow_dir(slug) / "history" / f"{st['submitted_on']}-{st['batch_id'].rsplit('/', 1)[-1]}.json"
    if not job.succeeded:
        st["outcome"] = {"state": job.state, "collected_on": ref.isoformat()}
        _write(hist, st)
        sp.unlink()
        return {"slug": slug, "status": "failed", "state": job.state, "added": []}
    with_usage = with_retry(lambda: cl.batch.results_with_usage(job))
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
    scope_excluded: list[dict] = []
    if added:
        in_lib = set(add_to_library(slug, [by_pid[pid] for pid in added], ref=ref, excluded=scope_excluded))
        added = [pid for pid in added if pid.split(":")[-1] in in_lib]
    st["outcome"] = {"state": job.state, "collected_on": ref.isoformat(),
                     "added": added, "failed": fails, "scope_excluded": scope_excluded}
    _write(hist, st)
    sp.unlink()
    return {"slug": slug, "status": "collected", "recorded_inr": round(st["recorded_inr"], 4),
            "added": added, "added_titles": [by_pid[p][0]["title"] for p in added],
            "failed": fails, "scope_excluded": scope_excluded}


# ---------------------------------------------------------------------------
# mode sync: extract in this run (interactive API, about 2x the batch price)
# ---------------------------------------------------------------------------

SYNC_CHECKPOINT_EVERY = 10   # papers between checkpoint pushes in a sync extraction


def inflight_path(slug: str) -> Path:
    return grow_dir(slug) / "sync_inflight.json"


def _sync_one(it: dict, cl: Clients, *, slug: str, cache) -> str:
    """Extract one paper (paid) unless its result is already cached (free).
    Returns "ok", "cached" or the validation failure."""
    from backend.app.corpus.multi_domain_extract import (
        MODEL_ID, OUT_TOKENS_ABSTRACT, OUT_TOKENS_FULLTEXT, _paper_from_entry,
    )
    from backend.app.corpus.run_batch_corpus import V11, _validate_and_cache
    e = it["entry"]
    pid = f"openalex:{e['wid']}"
    if cache.get(pid, MODEL_ID, it["src"], V11.hash) is not None:
        return "cached"                       # paid once already: never again
    if hasattr(cl.llm, "set_run_context"):
        cl.llm.set_run_context(stage=f"grow_extract_sync_{slug}",
                               est_output_tokens=OUT_TOKENS_FULLTEXT if it["src"] == "fulltext"
                               else OUT_TOKENS_ABSTRACT)
    text = with_retry(lambda: cl.llm.generate(it["prompt"]))
    return _validate_and_cache(_paper_from_entry(e), text, src=it["src"], model=MODEL_ID, cache=cache)


def extract_sync(slug: str, cl: Clients, budget: Budget, items: list[dict], *, ref: dt.date,
                 checkpoint: Callable[[str], None] | None = None) -> dict:
    """mode sync: extract the allocated papers NOW (paid, interactive rate)
    and add the ones that validate to the library in this run. Each result
    is validated and cached as it arrives (the spend is ledgered per call by
    the client); a cached result is never paid for again. The in-flight file
    (written before the first call and pushed by `checkpoint`) lets the next
    run finish a killed run's papers from the cache for free (finish_inflight)."""
    from backend.app.extraction.cache import ExtractionCache
    from backend.app.extraction.spend_gate import preflight
    proj = sum(it.get("inr_sync", it["inr"] * SYNC_COST_FACTOR) for it in items)
    res = {"slug": slug, "submitted": len(items), "projected_inr": round(proj, 4), "mode": "sync", "added": []}
    if not items:
        return res
    preflight(stage=f"grow_extract_sync_{slug}", projected_inr=proj, n_calls=len(items),
              multiplier=EXTRACTION_MULT)
    budget.commit(f"extract_sync_{slug}", proj, EXTRACTION_MULT)
    _write(inflight_path(slug), {"slug": slug, "started_on": ref.isoformat(), "projected_inr": proj,
                                 "src": {it["entry"]["wid"]: it["src"] for it in items},
                                 "entries": [it["entry"] for it in items], "records": [it["record"] for it in items]})
    if checkpoint:
        checkpoint(f"sync extraction of {slug} started")
    cache = ExtractionCache()
    ok, fails = [], []
    for n, it in enumerate(items, 1):
        out = _sync_one(it, cl, slug=slug, cache=cache)
        (ok if out in ("ok", "cached") else fails).append(it if out in ("ok", "cached") else
                                                          (f"openalex:{it['entry']['wid']}", out))
        if checkpoint and n % SYNC_CHECKPOINT_EVERY == 0 and n < len(items):
            checkpoint(f"sync extraction of {slug}: {n}/{len(items)}")
    res.update(_finish_sync(slug, ok, fails, ref=ref))
    return res


def _finish_sync(slug: str, ok: list[dict], fails: list, *, ref: dt.date) -> dict:
    excluded: list[dict] = []
    in_lib = set(add_to_library(slug, [(it["entry"], it["record"]) for it in ok], ref=ref, excluded=excluded))
    added = [f"openalex:{it['entry']['wid']}" for it in ok if it["entry"]["wid"] in in_lib]
    st = _read(inflight_path(slug)) if inflight_path(slug).exists() else {"slug": slug}
    st["outcome"] = {"mode": "sync", "collected_on": ref.isoformat(), "added": added, "failed": fails,
                     "scope_excluded": excluded}
    _write(grow_dir(slug) / "history" / f"{ref.isoformat()}-sync-{int(time.time())}.json", st)
    inflight_path(slug).unlink(missing_ok=True)
    return {"status": "extracted in this run", "added": added,
            "added_titles": [it["entry"]["title"] for it in ok if it["entry"]["wid"] in in_lib],
            "failed": fails, "scope_excluded": excluded}


def finish_inflight(slug: str, *, ref: dt.date) -> dict | None:
    """A sync extraction a killed run left behind: its cached results are
    added now (free); the rest are dropped from the in-flight list (they may
    have been paid for; they stay eligible as candidates, and a cached result
    is reused if they are picked again). Never calls an API."""
    p = inflight_path(slug)
    if not p.exists():
        return None
    from backend.app.corpus.multi_domain_extract import MODEL_ID
    from backend.app.corpus.run_batch_corpus import V11
    from backend.app.extraction.cache import ExtractionCache
    st, cache = _read(p), ExtractionCache()
    ok, fails = [], []
    for e, r in zip(st["entries"], st["records"]):
        src = st["src"].get(e["wid"], "abstract")
        if cache.get(f"openalex:{e['wid']}", MODEL_ID, src, V11.hash) is not None:
            ok.append({"entry": e, "record": r})
        else:
            fails.append((f"openalex:{e['wid']}", "no cached result (the earlier run stopped first)"))
    out = _finish_sync(slug, ok, fails, ref=ref)
    return {"slug": slug, **out, "status": "finished a stopped sync extraction from the cache (free)"}


# ---------------------------------------------------------------------------
# Phase 1b: paid follow-on checks for new material (each budget-gated)
# ---------------------------------------------------------------------------

def followon_wait_s() -> float:
    """How long a follow-on batch may be waited for now: FOLLOWON_WAIT_S,
    cut so the run keeps GATE_RESERVE_S before its deadline (GROW_DEADLINE_TS,
    set by the weekly run from its job timeout). A batch not finished in time
    stays pending (its state file is pushed) and the next run collects it,
    paying nothing twice."""
    import os
    dl = os.environ.get("GROW_DEADLINE_TS")
    if not dl:
        return FOLLOWON_WAIT_S
    return max(0.0, min(FOLLOWON_WAIT_S, float(dl) - time.time() - GATE_RESERVE_S))


def followon(slug: str, cl: Clients, budget: Budget) -> dict:
    """Each paid step is gated by the run's budget; if the money rule itself
    refuses (the money ran out mid-run), the step is skipped and reported as
    `money_refused` — never an error."""
    from backend.app.extraction.spend_gate import SpendGateRefused
    from backend.app.extraction.spend_ledger import SpendCapExceededError
    try:
        return _followon(slug, cl, budget)
    except (SpendGateRefused, SpendCapExceededError) as e:
        return {"slug": slug, "money_refused": str(e)[:200]}


def _followon(slug: str, cl: Clients, budget: Budget) -> dict:
    from backend.app.corpus import multi_domain_reason as R
    from backend.app.corpus.multi_domain_reason_incremental import write_coverage
    from backend.app.reasoning import run_library_scorers as S
    from backend.app.reasoning.library_corpus import embed_future_work
    from backend.app.grow import plan
    st = plan.load()
    out: dict[str, Any] = {"slug": slug}

    # a. disagreement check on new claim pairs (new claims embedded first;
    #    embeddings cost about half a paisa per claim and are ledgered by the client)
    exts = R.load_extractions(slug)
    pairs = R.compute_shortlist(exts, use_real_embeddings=True, slug=slug, embed_client=cl.embed)
    done = R.load_classified_keys(slug)
    unseen = [p for p in pairs if (p.from_claim_id, p.to_claim_id) not in done]
    per = R.projected_inr_per_pair()
    n_fit = min(len(unseen), int(budget.remaining / (per * CLASSIFY_MULT))) if per > 0 else len(unseen)
    # bounded per run as libraries grow: the rest stay unchecked (hidden,
    # never counted) and are carried over to the next run
    n_fit = min(n_fit, st.max_disagreement_pairs_per_run)
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
            out["fw_embed"] = "skipped: over this run's budget"
    fwd = S.fwmatch(slug, dry_run=True, max_items=st.max_fw_pairs_per_run)
    if fwd["to_classify"] or S._state(slug, "fw_match").exists():
        if S._state(slug, "fw_match").exists() or budget.fits(fwd["projected_inr"] * CLASSIFY_MULT):
            if not S._state(slug, "fw_match").exists():
                budget.commit(f"fw_match_{slug}", fwd["projected_inr"], CLASSIFY_MULT)
            try:
                out["fw_match"] = S.fwmatch(slug, dry_run=False, client=cl.batch,
                                            wait_timeout_s=followon_wait_s(), max_items=st.max_fw_pairs_per_run)
            except S.BatchPending as e:
                out["fw_match"] = f"pending: {e}"
        else:
            out["fw_match"] = "skipped: over this run's budget"
    else:
        # nothing to classify: every embedded item has been looked at
        from backend.app.reasoning.library_corpus import load_library_corpus, mark_fw_checked
        mark_fw_checked(slug, load_library_corpus(slug).fw_ids)

    # c. confirmation of method-transfer leads (unconfirmed leads stay hidden)
    cd = S.confirm(slug, dry_run=True, max_items=st.max_confirm_leads_per_run)
    if cd["to_confirm"] or S._state(slug, "hole_confirm").exists():
        if S._state(slug, "hole_confirm").exists() or budget.fits(cd["projected_inr"] * CLASSIFY_MULT):
            if not S._state(slug, "hole_confirm").exists():
                budget.commit(f"hole_confirm_{slug}", cd["projected_inr"], CLASSIFY_MULT)
            try:
                out["confirm"] = S.confirm(slug, dry_run=False, client=cl.batch,
                                           wait_timeout_s=followon_wait_s(), max_items=st.max_confirm_leads_per_run)
            except S.BatchPending as e:
                out["confirm"] = f"pending: {e}"
        else:
            out["confirm"] = "skipped: over this run's budget"
    return out
