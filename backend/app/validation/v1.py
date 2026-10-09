"""Validation protocol v1 (docs/findings/validation-protocol-v1.md, pre-registered
in commit 1bcdb4b). Runs exactly as written; parameters live in PROTOCOL and
must not change after results (a change is a v2).

  python -m backend.app.validation.v1 --pool        # free: pool only
  python -m backend.app.validation.v1 --run         # fetch (free), embed (≤ ₹20), compute

OpenAlex fetches and embeddings are cached under data/validation/v1/, so a
re-run reproduces for free. No language model judges any match.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import time
from pathlib import Path
from statistics import NormalDist

import httpx
import numpy as np

from backend.app.config import REPO_ROOT

PROTOCOL = {
    "commit": "1bcdb4b",
    "min_papers": 30, "last_window_year": 2025, "window_years": 2,
    "abstract_chars": 600, "cap_options": (20, 15, 10, 8, 5), "budget_inr": 20.0, "pad": 1.5,
    "tau_draws": 20, "tau_percentile": 95, "seed": 20261009,
    "perm_draws": 10_000, "boot": 2_000, "ks": (5, 10, 20), "caliper": 0.5,
    "power_auc": 0.65, "alpha": 0.05, "power": 0.80, "min_class": 10, "min_pairs": 10,
}
LIBS = ("llm-calibration", "diet-and-mortality", "ml-fairness", "social-media-teen-mental-health")
DIR = REPO_ROOT / "data" / "validation" / "v1"
OA = "https://api.openalex.org/works"
PUB = REPO_ROOT / "frontend" / "public" / "data"


# ---- pool ------------------------------------------------------------------

def _corpus(slug):
    if slug == "llm-calibration":
        from backend.app.reasoning.corpus_view import load_reasoning_corpus
        return load_reasoning_corpus()
    from backend.app.reasoning.library_corpus import load_library_corpus
    return load_library_corpus(slug)


def pool() -> tuple[list[dict], dict]:
    """Open questions, each once at its earliest freeze point (engine output only)."""
    from backend.app.reasoning.scorers import score_orphaned_future_work
    from backend.app.validation.time_split import _frozen
    items, corpora = [], {}
    for slug in LIBS:
        rc = _corpus(slug)
        corpora[slug] = rc
        fw_text = {fw.id: fw.text for fw, _m in rc._loaded.future_work()}
        years = sorted({p.year for p in rc.papers.values() if p.year})
        seen = set()
        for Y in years:
            n = sum(1 for p in rc.papers.values() if p.year and p.year <= Y)
            if n < PROTOCOL["min_papers"] or Y + PROTOCOL["window_years"] > PROTOCOL["last_window_year"]:
                continue
            for o in sorted(score_orphaned_future_work(_frozen(rc, Y)), key=lambda o: (-o.score, o.id)):
                fid = o.evidence_trail[0]
                if fid in seen:
                    continue
                seen.add(fid)
                src = o.supporting_paper_ids[0]
                items.append({"library": slug, "fw_id": fid, "fw_text": fw_text[fid], "freeze_year": Y,
                              "score": float(o.score), "source": src, "source_wid": src.rsplit(":", 1)[-1],
                              "source_year": rc.papers[src].year})
    return items, corpora


# ---- OpenAlex (free, cached) -----------------------------------------------

def _key() -> str:
    from backend.app.config import get_settings
    k = get_settings().openalex_api_key
    return k.get_secret_value() if hasattr(k, "get_secret_value") else k


def _get(params: dict) -> dict:
    for attempt in range(5):
        r = httpx.get(OA, params={**params, "api_key": _key()}, timeout=60)
        if r.status_code == 429 or r.status_code >= 500:
            time.sleep(3 * 2 ** attempt)
            continue
        if r.status_code >= 400:     # never raise_for_status(): its message carries the key
            raise RuntimeError(f"OpenAlex HTTP {r.status_code}")
        return r.json()
    raise RuntimeError("OpenAlex: retries exhausted")


def _abstract(inv: dict | None) -> str:
    if not inv:
        return ""
    pos = sorted((p, w) for w, ps in inv.items() for p in ps)
    return " ".join(w for _p, w in pos)


def citing(wid: str, Y: int) -> list[dict]:
    p = DIR / "openalex" / f"citing_{wid}_{Y}.json"
    if p.exists():
        return json.loads(p.read_text())
    body = _get({"filter": f"cites:{wid},from_publication_date:{Y + 1}-01-01,"
                           f"to_publication_date:{Y + PROTOCOL['window_years']}-12-31",
                 "sort": "publication_date:asc", "per-page": "200",
                 "select": "id,publication_date,publication_year,abstract_inverted_index"})
    out = [{"id": w["id"].rsplit("/", 1)[-1], "date": w.get("publication_date"),
            "year": w.get("publication_year"), "abstract": _abstract(w.get("abstract_inverted_index"))}
           for w in body.get("results", [])]
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(out))
    return out


def citations_up_to(wid: str, Y: int) -> int:
    p = DIR / "openalex" / f"counts_{wid}.json"
    if not p.exists():
        body = _get({"filter": f"openalex_id:{wid}", "select": "id,counts_by_year"})
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps((body.get("results") or [{}])[0].get("counts_by_year", [])))
    return sum(c["cited_by_count"] for c in json.loads(p.read_text()) if c["year"] <= Y)


def usable_citing(wid: str, Y: int, cap: int) -> list[dict]:
    rows = [c for c in citing(wid, Y) if c["abstract"].strip()]
    for c in rows:     # protocol: no paper dated at or before Y
        if not c["date"] or int(c["date"][:4]) <= Y:
            raise AssertionError(f"citing paper {c['id']} dated {c['date']} is not after {Y}")
    rows.sort(key=lambda c: (c["date"], c["id"]))
    return rows[:cap]


# ---- embeddings (paid, ≤ ₹20, cached) -----------------------------------------

def _trunc(t: str) -> str:
    return " ".join(t.split())[:PROTOCOL["abstract_chars"]]


def _h(t: str) -> str:
    return hashlib.sha1(t.encode()).hexdigest()


def _emb_cache() -> dict:
    p = DIR / "embeddings.json"
    return json.loads(p.read_text()) if p.exists() else {}


def _project(texts: list[str]) -> float:
    from backend.app.extraction.rate_limiter import estimate_tokens
    from backend.app.extraction.spend_ledger import EMBED_IN_PER_M, FX_USD_TO_INR
    return sum(estimate_tokens(t) for t in texts) * EMBED_IN_PER_M / 1e6 * FX_USD_TO_INR


def embed(texts: list[str], *, client=None) -> dict:
    cache = _emb_cache()
    todo = sorted({t for t in texts if _h(t) not in cache})
    if todo:
        from backend.app.extraction.spend_gate import preflight
        proj = _project(todo)
        assert proj * PROTOCOL["pad"] <= PROTOCOL["budget_inr"] + 1e-9, proj
        preflight(stage="validation_v1_embed", projected_inr=proj, n_calls=len(todo), multiplier=PROTOCOL["pad"])
        if client is None:
            from backend.app.relationships.embeddings import GeminiEmbeddingClient
            client = GeminiEmbeddingClient(stage="validation_v1_embed")
        step = getattr(client, "BATCH", 100)
        for k in range(0, len(todo), step):
            chunk = todo[k:k + step]
            for t, v in zip(chunk, client.embed(chunk)):
                cache[_h(t)] = [round(float(x), 6) for x in v]
            (DIR / "embeddings.json").write_text(json.dumps(cache))
    return cache


def _vec(cache, t):
    v = np.asarray(cache[_h(t)], dtype=np.float32)
    return v / max(np.linalg.norm(v), 1e-12)


# ---- statistics ---------------------------------------------------------------

def auc(scores, y) -> float:
    s, y = np.asarray(scores, float), np.asarray(y, bool)
    pos, neg = s[y], s[~y]
    if len(pos) == 0 or len(neg) == 0:
        return float("nan")
    gt = (pos[:, None] > neg[None, :]).sum() + 0.5 * (pos[:, None] == neg[None, :]).sum()
    return float(gt / (len(pos) * len(neg)))


def precision_at(order_scores, y, ids, k):
    idx = sorted(range(len(y)), key=lambda i: (-order_scores[i], ids[i]))[:k]
    return float(np.mean([y[i] for i in idx])) if len(idx) == k else float("nan")


def boot_ci(fn, n, rng, B):
    vals = []
    for _ in range(B):
        i = rng.integers(0, n, n)
        v = fn(i)
        if not math.isnan(v):
            vals.append(v)
    return (round(float(np.percentile(vals, 2.5)), 3), round(float(np.percentile(vals, 97.5)), 3)) if vals else (None, None)


def _hm_se(A, n1, n0):
    q1, q2 = A / (2 - A), 2 * A * A / (1 + A)
    return math.sqrt((A * (1 - A) + (n1 - 1) * (q1 - A * A) + (n0 - 1) * (q2 - A * A)) / (n1 * n0))


def power(N, p, A=None):
    A = A or PROTOCOL["power_auc"]
    n1 = max(1, round(N * p))
    n0 = max(1, N - n1)
    z = NormalDist().inv_cdf(1 - PROTOCOL["alpha"] / 2)
    return 1 - NormalDist().cdf((z * _hm_se(0.5, n1, n0) - (A - 0.5)) / _hm_se(A, n1, n0))


def n_required(p):
    p = min(p, 1 - p) if p > 0.5 else p
    if p <= 0:
        return math.inf
    for N in range(10, 100_000):
        if power(N, p) >= PROTOCOL["power"]:
            return N
    return math.inf


# ---- the run ------------------------------------------------------------------

def _library_abstracts(slug):
    d = PUB if slug == "llm-calibration" else PUB / "library" / slug
    out = {}
    # sorted: the seeded draws index into this order, and directory listing
    # order differs between platforms and between checkouts
    for f in sorted((d / "paper").glob("*.json")):
        j = json.loads(f.read_text())
        if j.get("abstract") and j.get("year"):
            out[f.stem] = (int(j["year"]), _trunc(j["abstract"]))
    return out


def run(*, client=None, write: bool = False) -> dict:
    rng_seed = PROTOCOL["seed"]
    items, corpora = pool()
    # free fetches
    for it in items:
        citing(it["source_wid"], it["freeze_year"])
        it["cites_up_to_Y"] = citations_up_to(it["source_wid"], it["freeze_year"])
    lib_abs = {s: _library_abstracts(s) for s in LIBS}
    # choose the cap C (largest whose padded projection fits the budget)
    cache = _emb_cache()
    cap = None
    for C in PROTOCOL["cap_options"]:
        texts = {_trunc(c["abstract"]) for it in items for c in usable_citing(it["source_wid"], it["freeze_year"], C)}
        # negatives: only abstracts that can be drawn — papers older than
        # some open question's source paper in the same library
        newest = {s: max([it["source_year"] for it in items if it["library"] == s], default=0) for s in LIBS}
        texts |= {t for s in LIBS for y, t in lib_abs[s].values() if y < newest[s]}
        # every embedding the run needs, cached or not (protocol: the cap is a
        # property of the data, not of what happens to be cached already)
        if _project(sorted(texts)) * PROTOCOL["pad"] <= PROTOCOL["budget_inr"]:
            cap = C
            break
    if cap is None:
        raise SystemExit("no cap fits the ₹20 budget; protocol v1 cannot run")
    cache = embed(sorted(texts), client=client)
    fwv = {}
    for s, rc in corpora.items():
        for i, f in enumerate(rc.fw_ids):
            fwv[(s, f)] = rc.fw_vectors[i] / max(np.linalg.norm(rc.fw_vectors[i]), 1e-12)
    # tau per library (amendment 2026-10-09)
    rng = np.random.default_rng(rng_seed)
    taus = {}
    for s in LIBS:
        draws = []
        for it in [x for x in items if x["library"] == s]:
            m = len(usable_citing(it["source_wid"], it["freeze_year"], cap))
            older = [t for (y, t) in lib_abs[s].values() if y < it["source_year"]]
            if m == 0 or not older:
                continue
            ov = np.stack([_vec(cache, t) for t in older])
            v = fwv[(s, it["fw_id"])]
            for _ in range(PROTOCOL["tau_draws"]):
                pick = rng.choice(len(older), size=m, replace=len(older) < m)
                draws.append(float((ov[pick] @ v).max()))
        taus[s] = float(np.percentile(draws, PROTOCOL["tau_percentile"])) if draws else None
    # outcomes
    for it in items:
        cits = usable_citing(it["source_wid"], it["freeze_year"], cap)
        v = fwv[(it["library"], it["fw_id"])]
        sims = [float(_vec(cache, _trunc(c["abstract"])) @ v) for c in cits]
        it["n_citing_used"] = len(cits)
        it["best_cosine"] = round(max(sims), 4) if sims else None
        tau = taus[it["library"]]
        it["addressed"] = bool(sims and tau is not None and max(sims) >= tau)
    # measures
    y = [it["addressed"] for it in items]
    ids = [f'{it["library"]}|{it["fw_id"]}' for it in items]
    engine = [it["score"] for it in items]
    cite = [it["cites_up_to_Y"] for it in items]
    recency = [it["source_year"] for it in items]
    N, npos = len(items), sum(y)
    rng = np.random.default_rng(rng_seed)

    def measures(sc):
        a = auc(sc, y)
        out = {"auc": round(a, 3) if not math.isnan(a) else None}
        out["auc_ci"] = boot_ci(lambda i: auc(np.asarray(sc)[i], np.asarray(y)[i]), N,
                                np.random.default_rng(rng_seed), PROTOCOL["boot"])
        out["precision"] = {k: precision_at(sc, y, ids, k) for k in PROTOCOL["ks"]}
        return out

    res = {"engine": measures(engine), "citations_up_to_Y": measures(cite), "recency": measures(recency)}
    # permutation null (random ranking) for the engine
    perm_auc, perm_p = [], {k: [] for k in PROTOCOL["ks"]}
    yy = np.asarray(y)
    for _ in range(PROTOCOL["perm_draws"]):
        sh = rng.permutation(yy)
        perm_auc.append(auc(engine, sh))
        for k in PROTOCOL["ks"]:
            perm_p[k].append(precision_at(engine, list(sh), ids, k))
    obs = res["engine"]["auc"]
    res["random"] = {
        "auc_null_mean": round(float(np.nanmean(perm_auc)), 3),
        "p_auc": round(float(np.mean([a >= obs for a in perm_auc if not math.isnan(a)])), 4) if obs is not None else None,
        "p_precision": {k: round(float(np.mean([p >= res["engine"]["precision"][k] for p in perm_p[k]])), 4)
                        for k in PROTOCOL["ks"] if not math.isnan(res["engine"]["precision"][k])},
        "precision_null_mean": {k: round(float(np.nanmean(perm_p[k])), 3) for k in PROTOCOL["ks"]},
    }
    # engine - citation paired difference
    E, C_ = np.asarray(engine), np.asarray(cite, float)
    res["engine_minus_citation_auc_ci"] = boot_ci(
        lambda i: auc(E[i], yy[i]) - auc(C_[i], yy[i]), N, np.random.default_rng(rng_seed), PROTOCOL["boot"])
    # popularity-matched subset
    logc = {i: math.log1p(cite[i]) for i in range(N)}
    pos_i = sorted([i for i in range(N) if y[i]], key=lambda i: ids[i])
    free = set(i for i in range(N) if not y[i])
    pairs = []
    for i in pos_i:
        cand = sorted(free, key=lambda j: (abs(logc[j] - logc[i]), ids[j]))
        if cand and abs(logc[cand[0]] - logc[i]) <= PROTOCOL["caliper"]:
            pairs.append((i, cand[0]))
            free.discard(cand[0])
    mi = [i for pr in pairs for i in pr]
    if pairs:
        ms, my = E[mi], yy[mi]
        res["matched"] = {"pairs": len(pairs), "auc": round(auc(ms, my), 3),
                          "auc_ci": boot_ci(lambda i: auc(ms[i], my[i]), len(mi),
                                            np.random.default_rng(rng_seed), PROTOCOL["boot"])}
    else:
        res["matched"] = {"pairs": 0, "auc": None, "auc_ci": (None, None)}
    # power at the observed share, and the verdict
    share = npos / N if N else 0
    need = n_required(share)
    powered = N >= need
    e, d, m = res["engine"], res["engine_minus_citation_auc_ci"], res["matched"]
    enough = npos >= PROTOCOL["min_class"] and (N - npos) >= PROTOCOL["min_class"] and m["pairs"] >= PROTOCOL["min_pairs"]
    above = lambda ci, x: ci[0] is not None and ci[0] > x
    if not powered or not enough:
        verdict = "inconclusive"
    elif above(e["auc_ci"], 0.5) and above(d, 0.0) and above(m["auc_ci"], 0.5):
        verdict = "supported"
    elif above(e["auc_ci"], 0.5):
        verdict = "not supported: popularity"
    else:
        verdict = "not supported"
    out = {"protocol": PROTOCOL, "cap_used": cap, "tau": {k: (round(v, 4) if v else None) for k, v in taus.items()},
           "N": N, "addressed": npos, "share_addressed": round(share, 3),
           "n_required_at_observed_share": need, "power_at_observed_share": round(power(N, min(share, 1 - share) or 1e-9), 3),
           "powered": powered, "enough_per_class": enough, "results": res, "verdict": verdict,
           "by_library": {s: {"N": sum(1 for it in items if it["library"] == s),
                              "addressed": sum(1 for it in items if it["library"] == s and it["addressed"])} for s in LIBS},
           "items": items}
    if write:    # only the CLI writes; tests and reruns never touch the record
        DIR.mkdir(parents=True, exist_ok=True)
        (DIR / "result.json").write_text(json.dumps(out, indent=1, default=str))
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pool", action="store_true")
    ap.add_argument("--run", action="store_true")
    a = ap.parse_args()
    if a.pool:
        items, _ = pool()
        print(len(items), {s: sum(1 for i in items if i["library"] == s) for s in LIBS})
    if a.run:
        r = run(write=True)
        print(json.dumps({k: v for k, v in r.items() if k != "items"}, indent=1, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
