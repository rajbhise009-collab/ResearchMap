"""Choose the next libraries (free: OpenAlex metadata + open full text only).

  python -m backend.app.corpus.domain_selection            # fetch, probe, score
  python -m backend.app.corpus.domain_selection --report   # table only (cached)

Per candidate:
  1. the coherence predictor's features on the 100 most-cited matching works
     (backend/app/coherence; one OpenAlex list call, cached);
  2. a REAL full-text probe: the 25 most-cited works go through the same
     retrieval code the libraries use (corpus/multi_domain.retrieve_fulltext_one:
     arXiv via OpenAlex locations or Semantic Scholar, arXiv title search,
     Unpaywall/Europe PMC). The share that yields text >= 3000 characters is
     the full-text rate. Not OA flags;
  3. three judgement scores, each written down with its reason below:
     reputation for active disagreement, audience diversity versus the
     existing libraries, and medical/social-advice risk.

Composite (weights fixed before scoring, contestedness weighted heavily
because disagreement-based discovery has only worked in contested fields):
  contestedness = 0.7 * reputation + 0.3 * predictor contested_score   (0.45)
  full-text rate                                                         (0.25)
  audience diversity                                                     (0.15)
  1 - advice risk                                                        (0.15)
Gate: at least 300 matching works in OpenAlex (room to build and grow).
"""

from __future__ import annotations

import argparse
import json
import time
from dataclasses import dataclass
from pathlib import Path

import httpx

from backend.app.coherence import features as F
from backend.app.coherence.fetch import CACHE, DomainSpec, _api_key, fetch_domain

W = {"contest": 0.45, "fulltext": 0.25, "audience": 0.15, "safety": 0.15}
MIN_MATCHES = 300
PROBE_N = 25


@dataclass
class Candidate:
    spec: DomainSpec
    reputation: float          # 0..1 active, published disagreement
    reputation_why: str
    audience: float            # 0..1 new readership vs existing libraries
    audience_why: str
    advice_risk: float         # 0..1 risk a reader takes results as advice
    advice_why: str
    health_or_social: bool     # gets a plain "not advice" note


def _s(slug, name, filt):
    return DomainSpec(slug=slug, name=name, filt=filt, reputation="candidate")


CANDIDATES: list[Candidate] = [
    Candidate(_s("microplastics-health", "Microplastics and human health",
                 "title_and_abstract.search:(microplastic OR nanoplastic) AND (human OR health OR exposure OR toxic),"
                 "type:article|preprint,publication_year:>2018"),
              0.7, "Open disputes over detection methods, contamination of samples and dose-response in humans.",
              0.8, "Environmental-health readers; no overlap with diet or ML.",
              0.5, "Readers may ask 'are microplastics harming me'; exposure advice risk is moderate.", True),
    Candidate(_s("intermittent-fasting", "Intermittent fasting and time-restricted eating",
                 "title_and_abstract.search:(\"intermittent fasting\" OR \"time-restricted eating\" OR "
                 "\"time-restricted feeding\" OR \"alternate-day fasting\"),type:article|preprint,publication_year:>2012"),
              0.8, "Trials disagree on whether benefits exceed plain calorie restriction (e.g. Lowe 2020 vs earlier small trials).",
              0.4, "Overlaps the Diet library's readers.",
              0.8, "Directly actionable eating advice; high risk of being read as a recommendation.", True),
    Candidate(_s("coffee-health", "Coffee, caffeine and health",
                 "title_and_abstract.search:(coffee OR caffeine) AND (mortality OR cardiovascular OR cancer OR "
                 "\"risk of\"),type:article|preprint,publication_year:>2010"),
              0.6, "Observational results flip across outcomes and doses; fewer head-on disputes than diet staples.",
              0.3, "Strong overlap with the Diet library.",
              0.8, "'Is coffee good for me' is the first question readers bring.", True),
    Candidate(_s("growth-mindset", "Growth-mindset interventions",
                 "title_and_abstract.search:(\"growth mindset\" OR \"mindset intervention\" OR "
                 "\"implicit theories of intelligence\"),type:article|preprint,publication_year:>2010"),
              0.9, "Large trials and meta-analyses disagree sharply (Yeager 2019 vs Sisk 2018, Macnamara 2023).",
              0.9, "Education and psychology readers; new audience.",
              0.3, "Teachers might apply it, but it is not medical advice.", True),
    Candidate(_s("ego-depletion", "Ego depletion and psychology replication debates",
                 "title_and_abstract.search:(\"ego depletion\" OR \"self-control depletion\" OR \"power posing\" OR "
                 "\"registered replication report\"),type:article|preprint,publication_year:>2010"),
              0.95, "Canonical replication dispute (Hagger 2016 RRR vs the original depletion literature).",
              0.9, "Psychology readers; new audience.",
              0.1, "Low advice risk.", False),
    Candidate(_s("social-media-teen-mental-health", "Social media and adolescent mental health",
                 "title_and_abstract.search:(\"social media\" OR \"screen time\" OR smartphone) AND (adolescent OR "
                 "adolescents OR teen OR youth) AND (depression OR anxiety OR \"mental health\" OR \"well-being\"),"
                 "type:article|preprint,publication_year:>2014"),
              0.95, "Openly contested (Twenge/Haidt vs Orben/Przybylski; effect-size and specification debates).",
              0.9, "Parents, educators, policy readers; new audience.",
              0.6, "Parents may read results as advice about their children; needs a not-advice note.", True),
    Candidate(_s("deep-rl-reproducibility", "Deep reinforcement learning: evaluation and reproducibility",
                 "title_and_abstract.search:(\"deep reinforcement learning\") AND (reproducibility OR benchmark OR "
                 "\"continuous control\" OR evaluation),type:article|preprint,publication_year:>2016"),
              0.7, "Henderson 2018 and Agarwal 2021 dispute evaluation practice; many results fail to reproduce.",
              0.3, "ML readers; overlaps LLM calibration and ML fairness.",
              0.0, "No advice risk.", False),
    Candidate(_s("minimum-wage", "Minimum wage and employment",
                 "title_and_abstract.search:(\"minimum wage\") AND (employment OR jobs OR labor OR labour),"
                 "type:article|preprint,publication_year:>1995"),
              0.95, "Classic economics dispute (Card-Krueger vs Neumark-Wascher; Seattle studies disagree).",
              1.0, "Economics and policy readers; new audience.",
              0.2, "Policy, not personal advice.", True),
    Candidate(_s("empirical-software-engineering", "Empirical software engineering (defect prediction)",
                 "title_and_abstract.search:(\"defect prediction\" OR \"bug prediction\" OR \"fault prediction\") AND "
                 "(empirical OR replication OR reproducibility),type:article|preprint,publication_year:>2015"),
              0.6, "Disputes over metrics and datasets (Shepperd 2014 researcher bias vs replies).",
              0.5, "Software engineers; partial overlap with ML readers.",
              0.0, "No advice risk.", False),
    Candidate(_s("nudge-effectiveness", "Nudges and choice architecture: do they work?",
                 "title_and_abstract.search:(nudge OR nudging OR \"choice architecture\" OR \"default effect\") AND "
                 "(effect OR effectiveness OR meta-analysis OR intervention),type:article|preprint,publication_year:>2012"),
              0.9, "Mertens 2022 meta-analysis vs Maier 2022 (no evidence after bias correction).",
              0.9, "Behavioural-science and policy readers; new audience.",
              0.2, "Low advice risk.", True),
    Candidate(_s("vitamin-d", "Vitamin D supplementation and health outcomes",
                 "title_and_abstract.search:(\"vitamin D\") AND (supplementation OR trial) AND (mortality OR cancer OR "
                 "fracture OR cardiovascular),type:article|preprint,publication_year:>2010"),
              0.85, "Observational benefit vs null large trials (VITAL, D-Health).",
              0.5, "Health readers; partial overlap with Diet.",
              0.9, "Supplement advice risk is high.", True),
    Candidate(_s("stereotype-threat", "Stereotype threat",
                 "title_and_abstract.search:(\"stereotype threat\"),type:article|preprint,publication_year:>2005"),
              0.85, "Meta-analyses disagree on whether the effect survives publication-bias correction.",
              0.9, "Psychology and education readers; new audience.",
              0.2, "Low advice risk.", True),
]


def _probe_dir(slug: str) -> Path:
    return CACHE / slug


def fulltext_probe(c: Candidate, payload: dict) -> dict:
    """Top PROBE_N works by citations through the libraries' own retrieval."""
    from backend.app.corpus.multi_domain import retrieve_fulltext_one
    out_p = _probe_dir(c.spec.slug) / "fulltext_probe.json"
    if out_p.exists():
        return json.loads(out_p.read_text())
    recs = sorted(payload["results"], key=lambda r: -(r.get("cited_by_count") or 0))[:PROBE_N]
    wids = [r["id"].rsplit("/", 1)[-1] for r in recs]
    def _get():
        with httpx.Client(timeout=60.0) as h:
            r = h.get("https://api.openalex.org/works",
                      params={"filter": "openalex_id:" + "|".join(wids), "per-page": str(PROBE_N),
                              "api_key": _api_key()})
            r.raise_for_status()
            return r.json().get("results", [])
    full = _retry(_get)
    by = {r["id"].rsplit("/", 1)[-1]: r for r in full}
    rows = []
    with httpx.Client(timeout=25.0, follow_redirects=True,
                      headers={"User-Agent": "ResearchMap/0.3 domain-probe"}) as client:
        for w in wids:
            rec = by.get(w, {})
            e = {"wid": w, "openalex_id": rec.get("id") or f"https://openalex.org/{w}",
                 "doi": rec.get("doi"), "title": rec.get("display_name"),
                 "year": rec.get("publication_year"), "cited_by_count": rec.get("cited_by_count")}
            try:
                src = retrieve_fulltext_one(e, rec, client=client)
            except Exception as ex:  # noqa: BLE001
                src = None
                e["error"] = type(ex).__name__
            rows.append({"wid": w, "title": e["title"], "source": src})
    res = {"n": len(rows), "with_fulltext": sum(1 for r in rows if r["source"]),
           "by_source": {}, "rows": rows, "date": time.strftime("%Y-%m-%d")}
    for r in rows:
        k = r["source"] or "abstract_only"
        res["by_source"][k] = res["by_source"].get(k, 0) + 1
    res["rate"] = round(res["with_fulltext"] / max(1, res["n"]), 3)
    out_p.write_text(json.dumps(res, indent=1))
    return res


def _retry(fn, *args, tries: int = 6):
    """OpenAlex returns 429 under bursts: back off and retry. Errors are
    re-raised without the request URL (it carries the API key)."""
    for k in range(tries):
        try:
            return fn(*args)
        except httpx.HTTPStatusError as e:
            code = e.response.status_code
            if code == 429 and k < tries - 1:
                time.sleep(2 ** k * 3)
                continue
            raise RuntimeError(f"OpenAlex HTTP {code}") from None
        except httpx.HTTPError as e:
            if k < tries - 1:
                time.sleep(2 ** k * 3)
                continue
            raise RuntimeError(f"OpenAlex {type(e).__name__}") from None


def score(c: Candidate, *, probe: bool = True) -> dict:
    payload = _retry(fetch_domain, c.spec)
    feats = F.features(payload["results"])
    v = F.verdict(feats)
    pr = fulltext_probe(c, payload) if probe else json.loads(
        (_probe_dir(c.spec.slug) / "fulltext_probe.json").read_text())
    contest = 0.7 * c.reputation + 0.3 * v["contested_score"]
    comp = (W["contest"] * contest + W["fulltext"] * pr["rate"]
            + W["audience"] * c.audience + W["safety"] * (1 - c.advice_risk))
    n = (payload.get("meta") or {}).get("count") or 0
    return {"slug": c.spec.slug, "name": c.spec.name, "matches": n, "gate_ok": n >= MIN_MATCHES,
            "predictor_contested": v["contested_score"], "predictor_mt": v["method_transfer_score"],
            "reputation": c.reputation, "contestedness": round(contest, 3),
            "fulltext_rate": pr["rate"], "fulltext_by_source": pr["by_source"],
            "audience": c.audience, "advice_risk": c.advice_risk,
            "composite": round(comp, 3) if n >= MIN_MATCHES else None,
            "why": {"reputation": c.reputation_why, "audience": c.audience_why, "advice": c.advice_why},
            "filter": c.spec.filt, "health_or_social": c.health_or_social}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", nargs="*")
    a = ap.parse_args()
    rows = []
    for c in CANDIDATES:
        if a.only and c.spec.slug not in a.only:
            continue
        r = score(c)
        print(f"{r['slug']:<34} matches={r['matches']:<6} contest={r['contestedness']:.2f} "
              f"ft={r['fulltext_rate']:.2f} comp={r['composite']}", flush=True)
        rows.append(r)
    out = CACHE / "selection.json"
    old = json.loads(out.read_text()) if out.exists() else {}
    old.update({r["slug"]: r for r in rows})
    out.write_text(json.dumps(old, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
