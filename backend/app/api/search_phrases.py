"""Generated search phrases per library, from each library's OWN index.

Shared by the search tests (backend/tests/api/test_search_autogen.py) and the
smoke checks (tools/qa/smoke.py, which also runs in the daily health
workflow). Standard library only: the daily workflow installs nothing but
Playwright.

For each built library (frontend/public/data/libraries.json): its 15 most
distinctive two-word phrases taken from its own document titles (both words
in at most 15% of this library's documents and rarer in every other
library). REFUSE: 5 queries far from every library.
"""
from __future__ import annotations

import json
import math
import re
from pathlib import Path

from backend.app.api.search_index import STOPWORDS, _stem

DATA = Path(__file__).resolve().parents[3] / "frontend" / "public" / "data"
LIBS = json.loads((DATA / "libraries.json").read_text())["libraries"]
MAX_SHARE = 0.15
# Far from every library this project could hold (not "stock market": an
# economics or behavioural library may legitimately cover markets).
REFUSE = ["melanoma treatment", "volcano eruption forecasting", "camera calibration for stereo vision",
          "quantum computing error correction", "medieval castle architecture"]


def _idx(lib):
    d = DATA if lib["snapshot_path"] == "/data" else DATA / lib["snapshot_path"].removeprefix("/data/")
    return json.loads((d / "search-index.json").read_text())


INDEX = {l["slug"]: _idx(l) for l in LIBS}


def _df_share(idx: dict) -> dict[str, float]:
    n = idx["n_docs"]
    return {t: max(0.0, (n + 1) / math.exp(v) - 0.5) / n for t, v in idx["idf"].items() if "__" not in t}


def queries(slug: str) -> list[str]:
    return queries_for(INDEX[slug], [INDEX[s] for s in INDEX if s != slug])


def _distinct_pairs(idx: dict, others: list[dict], titles: list[str]) -> list[str]:
    """Two-word phrases from `titles`, both words distinctive for this index
    (in at most MAX_SHARE of its documents and rarer in every other)."""
    here = _df_share(idx)
    other_shares = [_df_share(o) for o in others]
    # Distinctive AND specific: very common words (e.g. "models" in a
    # language-model library) are deliberately answered "borderline" by the
    # search gate, so they are not used as must-be-in-domain tests.
    score = {t: here[t] - max((o.get(t, 0.0) for o in other_shares), default=0.0)
             for t in here if here[t] <= MAX_SHARE}
    pair_score: dict[str, float] = {}
    for title in titles:
        words = [w for w in re.findall(r"[a-z][a-z-]+", title.lower()) if w not in STOPWORDS and len(w) > 3]
        for a, b in zip(words, words[1:]):
            sa, sb = score.get(_stem(a), -1), score.get(_stem(b), -1)
            if sa > 0 and sb > 0:
                pair_score[f"{a} {b}"] = max(pair_score.get(f"{a} {b}", 0), sa + sb)
    return [p for p, _s in sorted(pair_score.items(), key=lambda x: (-x[1], x[0]))]


def queries_for(idx: dict, others: list[dict]) -> list[str]:
    """The 15 most distinctive two-word phrases from this index's document
    titles (papers and results alike)."""
    return _distinct_pairs(idx, others, [d["title"] for d in idx["docs"]])[:15]


# --- the smoke checks' settled search ----------------------------------------

# The hand-picked searches (each verified against its library below, like
# every generated one).
SETTLED = {"diet-and-mortality": "alc", "ml-fairness": "fair", "llm-calibration": "halluc"}
NEED_GAPS_MIN = 3        # a library showing at least this many results must show gaps for its search
HIT_LIMIT = 24           # the search page shows the top 24 hits (frontend/app/components/Ask.tsx)


def smoke_phrase_for(slug: str, idx: dict, others: list[dict], *, shown_results: int,
                     settled: str | None = None) -> dict:
    """The search the smoke checks run for a library, verified against its
    built index before the browser ever runs it.

    A library showing at least NEED_GAPS_MIN results must answer its search
    in_domain with at least one result card (an "opportunity" hit) among
    the hits the page shows; the phrase is chosen to do exactly that. The
    candidates: the hand-picked phrase, then the library's most distinctive
    title phrases, then the most distinctive phrases of its own result
    headlines (so a library that has results always has a phrase that
    reaches one). If none does, the result still demands gaps, so the
    check fails loudly; it is never loosened. A library showing fewer
    results is checked on results only, with the reason recorded.

    Returns {query, need_gaps, gap_hits, hits, verdict, reason}."""
    from backend.app.api.search_index import search
    need = shown_results >= NEED_GAPS_MIN
    results_titles = [d["title"] for d in idx["docs"] if d.get("type") == "opportunity"]
    cands: list[str] = []
    for q in ([settled] if settled else []) + queries_for(idx, others) + _distinct_pairs(idx, others, results_titles):
        if q and q not in cands:
            cands.append(q)
    first_ok = None
    for q in cands:
        r = search(idx, q, HIT_LIMIT, expand_trailing=True)
        hits = r.get("hits", [])
        gaps = sum(1 for h in hits if h.get("type") == "opportunity")
        row = {"query": q, "need_gaps": need, "gap_hits": gaps, "hits": len(hits), "verdict": r["verdict"]}
        if r["verdict"] != "in_domain" or not hits:
            continue
        if not need:
            return {**row, "reason": f"{slug} shows {shown_results} result(s), fewer than {NEED_GAPS_MIN}: "
                                     "the search is checked for results only"}
        if gaps:
            return {**row, "reason": f"verified against the built index: {gaps} result card(s) "
                                     f"among {len(hits)} hits"}
        first_ok = first_ok or row
    if first_ok:
        return {**first_ok, "reason": f"NO candidate phrase reaches a result card in {slug} "
                                      f"({len(cands)} tried); the check still requires one"}
    return {"query": slug.replace("-", " "), "need_gaps": need, "gap_hits": 0, "hits": 0, "verdict": "none",
            "reason": f"NO candidate phrase is answered in_domain by {slug} ({len(cands)} tried)"}


def smoke_phrase(slug: str, shown_results: int) -> dict:
    """smoke_phrase_for on the built site's own index for `slug`."""
    return smoke_phrase_for(slug, INDEX[slug], [INDEX[s] for s in INDEX if s != slug],
                            shown_results=shown_results, settled=SETTLED.get(slug))
