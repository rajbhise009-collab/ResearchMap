"""Compute coherence features from OpenAlex metadata alone.

Every function here is pure: it takes a list of OpenAlex `results` dicts
(the shape returned by `/works?filter=…`) and returns a number or a small
struct. No LLM calls, no full-text fetches, no embedding model.

## The features

Each is documented with WHAT it measures and WHAT it proxies for.
"Proxies for" is the interpretive claim, and it is the thing that would
have to hold for the predictor to be right — which is why the finding
document flags each one as hypothesis, not established.

  1. `intracorpus_reference_rate` — mean, per paper, of the fraction of
     that paper's outbound references that point to OTHER papers in the
     corpus. Proxy: co-citation density; a coherent, mature field has
     papers that cite each other tightly.

  2. `citation_reciprocity` — of directed edges A→B in the corpus, what
     fraction have a matching B→A. Almost always tiny for one-shot
     literature (papers cite past work, not future), but a slightly less
     tiny value distinguishes "long-running conversation with many
     preprints across years" from "recent shared list of prior work."

  3. `citation_modularity` — Louvain-style modularity of the intra-corpus
     citation graph, computed with a tiny hand-rolled greedy community
     detector so we don't add networkx as a dependency. Proxy for
     "does the field split into cleanly separated schools of thought"
     (higher modularity → more likely to contain method-transfer holes).

  4. `review_ratio` — fraction of records whose OpenAlex `type` is
     `review` or whose title contains "survey"/"review". Proxy: high
     review ratio → the field has enough shared consensus to write
     surveys of, i.e. more consolidated / less contested.

  5. `temporal_churn` — Jensen-Shannon divergence between the year-by-
     year distribution of REFERENCED works. High churn = each cohort of
     papers cites a different past; low churn = everyone cites the same
     founding papers. Proxy: churn separates fast-moving frontier from
     established canon.

  6. `venue_concentration` — Herfindahl-Hirschman index of publication
     venues (from `primary_location.source.id`). High HHI = one or two
     venues dominate (typical of consolidated fields with a flagship
     journal/conference); low HHI = the topic is scattered across many
     venues (typical of pre-paradigmatic or interdisciplinary).

  7. `term_vector_spread` — mean pairwise cosine distance between title
     term-vectors (bag-of-words with English stopwording, no embeddings
     — that would need a paid embedding call). Proxy for topical
     breadth; a small, focused topic has low spread, a broad
     interdisciplinary sweep has high spread.

  8. `median_year`, `year_span` — corpus temporal signature. Included as
     descriptive facts, not as coherence predictors on their own.

Also returns `n_papers` for grounding.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from typing import Any, Iterable

# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------

_STOPWORDS = frozenset({
    "the", "a", "an", "and", "or", "of", "in", "on", "for", "with", "to",
    "from", "by", "at", "as", "is", "are", "was", "were", "be", "been",
    "being", "this", "that", "these", "those", "we", "our", "us", "it",
    "its", "their", "his", "her", "he", "she", "they", "them", "into",
    "via", "using", "toward", "towards", "over", "under", "between",
    "against", "based", "how", "why", "what", "when", "where", "which",
    "who", "whom", "some", "any", "all", "more", "most", "less", "least",
    "than", "such", "so", "not", "no", "one", "two", "three",
})


def _short_id(work_id: str | None) -> str | None:
    """OpenAlex IDs are URLs; the short W-id is the last path segment.
    Callers pass either form; we normalise to the short id everywhere."""
    if not work_id:
        return None
    return work_id.rsplit("/", 1)[-1]


def _title_terms(title: str) -> set[str]:
    """Lowercased content-word set, stripped of punctuation and stopwords.
    Deliberately simple — this is a term-vector proxy for topical
    spread, not a search index."""
    if not title:
        return set()
    tokens = re.findall(r"[a-z0-9]+", title.lower())
    return {t for t in tokens if len(t) > 2 and t not in _STOPWORDS}


# --------------------------------------------------------------------------
# Individual features
# --------------------------------------------------------------------------

def n_papers(records: Iterable[dict]) -> int:
    """Number of records in the corpus. Grounding number, not a feature."""
    return sum(1 for _ in records)


def intracorpus_reference_rate(records: list[dict]) -> float:
    """Mean, per paper, of the fraction of its outbound references that
    point to other papers in the SAME corpus.

    A paper with 100 references, 8 of which are also in the corpus,
    contributes 0.08. Papers with zero references contribute 0. Averaged
    over all papers with at least one reference; that's the honest
    denominator because a "0/0" isn't evidence either way."""
    ids_in_corpus = {_short_id(r.get("id")) for r in records}
    ids_in_corpus.discard(None)
    if not ids_in_corpus:
        return 0.0
    rates: list[float] = []
    for r in records:
        refs = r.get("referenced_works") or []
        if not refs:
            continue
        refs_short = {_short_id(x) for x in refs}
        rates.append(sum(1 for x in refs_short if x in ids_in_corpus) / len(refs))
    return sum(rates) / len(rates) if rates else 0.0


def citation_reciprocity(records: list[dict]) -> float:
    """Fraction of directed A→B edges that have a matching B→A edge.

    Both directions being observed within one paper set requires either
    preprint/revision cross-citation, or two contemporaneous papers
    citing each other's earlier work. On any well-formed academic corpus
    this is a small number; the *shape* of it is what matters —
    consistently zero means "no citation loops of any kind," while
    non-zero suggests running conversation."""
    ids_in_corpus = {_short_id(r.get("id")) for r in records}
    ids_in_corpus.discard(None)
    directed_edges: set[tuple[str, str]] = set()
    for r in records:
        src = _short_id(r.get("id"))
        if src is None:
            continue
        for tgt in r.get("referenced_works") or []:
            t = _short_id(tgt)
            if t and t in ids_in_corpus and t != src:
                directed_edges.add((src, t))
    if not directed_edges:
        return 0.0
    reciprocal = sum(1 for (a, b) in directed_edges if (b, a) in directed_edges)
    return reciprocal / len(directed_edges)


# --------------------------------------------------------------------------
# Modularity — a small greedy community detector
# --------------------------------------------------------------------------

def _adjacency(records: list[dict]) -> tuple[dict[str, set[str]], list[str]]:
    """Undirected intra-corpus citation graph (edges symmetrised)."""
    ids = [_short_id(r.get("id")) for r in records]
    ids = [i for i in ids if i is not None]
    corpus = set(ids)
    adj: dict[str, set[str]] = {i: set() for i in ids}
    for r in records:
        src = _short_id(r.get("id"))
        if src is None:
            continue
        for tgt in r.get("referenced_works") or []:
            t = _short_id(tgt)
            if t and t in corpus and t != src:
                adj[src].add(t)
                adj[t].add(src)
    return adj, ids


def _modularity(adj: dict[str, set[str]], community: dict[str, int]) -> float:
    """Newman modularity Q of the partition."""
    m2 = sum(len(v) for v in adj.values())  # 2m
    if m2 == 0:
        return 0.0
    q = 0.0
    for i, ni in adj.items():
        ki = len(ni)
        ci = community[i]
        for j, nj in adj.items():
            if community[j] != ci:
                continue
            aij = 1.0 if j in ni else 0.0
            q += aij - (ki * len(nj)) / m2
    return q / m2


def citation_modularity(records: list[dict]) -> float:
    """Greedy Louvain-style modularity of the intra-corpus citation graph.

    Deterministic, self-contained implementation of the local-moving
    phase of Louvain. Each node in its own community to start; iterate
    over nodes in a fixed order; each node moves to the neighbouring
    community offering the biggest Q gain (or stays). Repeat until an
    entire pass moves no nodes.

    O(iterations · edges · avg-community-count-of-neighbours) — for a
    100-node, ~200-edge citation graph that is small enough to close
    over its convergence in well under a second, and does the same job
    on 500-node graphs.

    Bounded in [-0.5, 1]; higher = more community structure. Zero on an
    empty graph. A field split into cleanly separated schools scores
    high; a random citation web scores near zero."""
    adj, nodes = _adjacency(records)
    m2 = sum(len(v) for v in adj.values())
    if len(nodes) < 2 or m2 == 0:
        return 0.0
    inv_m2 = 1.0 / m2

    community = {n: i for i, n in enumerate(nodes)}
    # For fast Q-gain: track weighted degree (== degree since unweighted)
    # per node, and total degree of each community.
    degree = {n: len(adj[n]) for n in nodes}
    comm_deg: dict[int, int] = {}
    for n, c in community.items():
        comm_deg[c] = comm_deg.get(c, 0) + degree[n]

    max_passes = 20
    for _pass in range(max_passes):
        moved = False
        for n in nodes:
            cn = community[n]
            kn = degree[n]
            # Neighbour communities and this node's own connections into each.
            k_i_in: dict[int, int] = {}
            # sorted: ties between equal gains must not depend on set order
            # (Python's per-process hash seed), or the score changes run to run
            for nb in sorted(adj[n]):
                k_i_in[community[nb]] = k_i_in.get(community[nb], 0) + 1
            # Remove n from its current community for a fair delta.
            comm_deg[cn] -= kn
            k_i_in_cn = k_i_in.get(cn, 0)
            best_c = cn
            best_gain = 0.0
            for c, k_in in k_i_in.items():
                # ΔQ for moving n into c:
                #   (k_in / m) − (kn · Σ_tot[c] / (2 m²))
                # (equivalent up to constants to the Louvain formula, and
                # rejecting c == cn keeps the "stay" option honest via
                # best_gain == 0 → best_c == cn).
                gain = k_in * inv_m2 - kn * comm_deg[c] * inv_m2 * inv_m2
                if gain > best_gain:
                    best_gain = gain
                    best_c = c
            comm_deg[best_c] = comm_deg.get(best_c, 0) + kn
            if best_c != cn:
                community[n] = best_c
                moved = True
        if not moved:
            break

    return round(_modularity(adj, community), 4)


# --------------------------------------------------------------------------
# Review ratio, temporal churn, venue concentration, term-vector spread
# --------------------------------------------------------------------------

_REVIEW_HINTS = re.compile(r"\b(survey|review|overview|systematic)\b", re.I)


def review_ratio(records: list[dict]) -> float:
    """Fraction of records that are reviews or surveys.

    Uses two signals: OpenAlex `type == 'review'`, or title/display_name
    containing survey/review/overview/systematic. Either one counts."""
    if not records:
        return 0.0
    hits = 0
    for r in records:
        if r.get("type") == "review":
            hits += 1
            continue
        title = r.get("display_name") or r.get("title") or ""
        if _REVIEW_HINTS.search(title):
            hits += 1
    return hits / len(records)


def temporal_churn(records: list[dict]) -> float:
    """Jensen-Shannon divergence, averaged pairwise across year cohorts,
    over the distribution of referenced works.

    For each publication year with at least K papers, form a probability
    distribution over the referenced-works most-cited (Counter → normalise).
    Compute mean JS divergence across consecutive years. High divergence
    means each year is reading a very different set of prior work (fast-
    moving frontier); low divergence means everyone is grounded in the
    same canon (established consensus)."""
    K = 3
    by_year: dict[int, Counter] = {}
    for r in records:
        year = r.get("publication_year")
        if year is None:
            continue
        refs = [_short_id(x) for x in (r.get("referenced_works") or [])]
        by_year.setdefault(int(year), Counter()).update(x for x in refs if x)
    years = sorted(y for y, c in by_year.items() if sum(c.values()) >= K)
    if len(years) < 2:
        return 0.0
    divs: list[float] = []
    for y1, y2 in zip(years, years[1:]):
        divs.append(_js_divergence(by_year[y1], by_year[y2]))
    return round(sum(divs) / len(divs), 4)


def _js_divergence(a: Counter, b: Counter) -> float:
    """Jensen-Shannon divergence between two multiset frequency
    distributions. Returns in [0, 1] when base-2 log is used."""
    ta = sum(a.values()); tb = sum(b.values())
    if ta == 0 or tb == 0:
        return 0.0
    keys = set(a) | set(b)
    pa = {k: a.get(k, 0) / ta for k in keys}
    pb = {k: b.get(k, 0) / tb for k in keys}
    pm = {k: (pa[k] + pb[k]) / 2 for k in keys}

    def _kl(p: dict, q: dict) -> float:
        s = 0.0
        for k in p:
            if p[k] > 0 and q[k] > 0:
                s += p[k] * math.log2(p[k] / q[k])
        return s

    return 0.5 * _kl(pa, pm) + 0.5 * _kl(pb, pm)


def venue_concentration(records: list[dict]) -> float:
    """Herfindahl-Hirschman index over publication venue IDs.

    Bounded in [0, 1]; 1 = every paper in one venue, 1/n = perfectly
    uniform. Reads OpenAlex's `primary_location.source.id`. Papers with
    no venue (arXiv preprints without published metadata) are dropped
    from the denominator so preprint-heavy fields aren't penalised as
    "diffuse" just because they lack DOIs yet."""
    venue_ids: list[str] = []
    for r in records:
        src = ((r.get("primary_location") or {}).get("source") or {}).get("id")
        if src:
            venue_ids.append(src)
    if not venue_ids:
        return 0.0
    counts = Counter(venue_ids)
    n = len(venue_ids)
    return round(sum((c / n) ** 2 for c in counts.values()), 4)


def term_vector_spread(records: list[dict]) -> float:
    """Mean pairwise Jaccard *distance* between title term-sets.

    We use Jaccard rather than cosine because bag-of-words vectors
    without embedding weights make cosine roughly equivalent to Jaccard
    anyway, and Jaccard has cleaner "0 to 1" semantics: 0 = all titles
    share every word (impossible in practice; think ~0.4-0.6 for a
    focused field), 1 = no title shares any word with any other.

    Sampled at random over up to 200 pairs if the corpus is large, so
    the cost stays O(N) with fixed constant."""
    term_sets: list[set[str]] = []
    for r in records:
        t = r.get("display_name") or r.get("title") or ""
        s = _title_terms(t)
        if s:
            term_sets.append(s)
    if len(term_sets) < 2:
        return 0.0
    # Bounded pair enumeration keeps this cheap and deterministic.
    pairs: list[tuple[int, int]] = []
    limit = 200
    for i in range(len(term_sets)):
        for j in range(i + 1, len(term_sets)):
            pairs.append((i, j))
            if len(pairs) >= limit:
                break
        if len(pairs) >= limit:
            break
    dists: list[float] = []
    for i, j in pairs:
        a, b = term_sets[i], term_sets[j]
        u = len(a | b)
        if u == 0:
            continue
        dists.append(1.0 - len(a & b) / u)
    return round(sum(dists) / len(dists), 4) if dists else 0.0


def year_stats(records: list[dict]) -> tuple[int | None, int | None]:
    """(median_year, year_span). Descriptive only."""
    years = sorted(int(r["publication_year"])
                   for r in records if r.get("publication_year") is not None)
    if not years:
        return (None, None)
    n = len(years)
    median = years[n // 2] if n % 2 == 1 else (years[n // 2 - 1] + years[n // 2]) // 2
    return (median, years[-1] - years[0])


# --------------------------------------------------------------------------
# The whole feature vector
# --------------------------------------------------------------------------

def features(records: list[dict]) -> dict[str, Any]:
    """Compute every feature for a given OpenAlex records list."""
    median, span = year_stats(records)
    return {
        "n_papers": n_papers(records),
        "intracorpus_reference_rate": round(intracorpus_reference_rate(records), 4),
        "citation_reciprocity": round(citation_reciprocity(records), 4),
        "citation_modularity": citation_modularity(records),
        "review_ratio": round(review_ratio(records), 4),
        "temporal_churn": temporal_churn(records),
        "venue_concentration": venue_concentration(records),
        "term_vector_spread": term_vector_spread(records),
        "median_year": median,
        "year_span": span,
    }


# --------------------------------------------------------------------------
# Interpretive layer: turning features into a plain-language verdict
# --------------------------------------------------------------------------

# Everything here is a HYPOTHESIS. See docs/findings/domain-coherence-
# predictor.md for the reasoning and its unvalidated status.

def contested_score(f: dict) -> float:
    """A hypothesis-driven 0-to-1 "contestedness" score.

    Higher = we EXPECT more contradiction signal here. This is the
    predictor's headline number, and it is HYPOTHESIS-DRIVEN, not
    fit to data — we have exactly ONE domain with a ground-truth
    yield measurement (n=1). What follows is our current reasoning
    about which observable proxies signal contestedness. The finding
    document tracks the reversal below (v0.1 → v0.2), which is a warning
    about how tempting it is to write "obvious" hypotheses that turn out
    wrong the moment there's data.

    ## Hypothesis v0.2 (used here)

    A CONTESTED field, per the observed cross-domain patterns in our
    9-domain fetch:
      + HIGH review ratio.  Counter-intuitive but consistent across our
        sample: reputationally-contested domains (deep-RL, microplastics,
        empirical SE, ML fairness) publish 5-10× more surveys/reviews
        than reputationally-consolidated ones (protein, formal methods,
        transformers). Reviews are largely RESPONSES to disagreement —
        systematic reviews, meta-analyses, "what we know and don't
        know" — not consolidation writeups.
      + LOW citation reciprocity.  Consolidated fields show occasional
        preprint↔published cycles (~3% in protein and transformer); a
        churning contested field cites forward more than it converses
        with itself.
      + MODERATE-to-LOW citation modularity.  A cleanly-partitioned
        graph (protein-structure-prediction: 0.25) means the field's
        camps aren't really in dialogue; a contested field's camps
        argue enough to cite each other (0.30-0.45).

    ## Hypothesis v0.1 (WRONG — kept in the finding as a cautionary tale)

    The first draft assumed reviews signalled consolidation ("ready to
    write the textbook"). The data flipped that: reputationally-
    contested fields have the highest review ratios (up to 0.25 for
    microplastics). Weights inverted in v0.2. This is what n=1 lets you
    do — one direction reversal — and no more.
    """
    r = f["review_ratio"]
    recip = f["citation_reciprocity"]
    m = f["citation_modularity"]

    # Each term maps its feature to a [0, 1] contribution in the
    # v0.2 direction; average.
    terms = [
        min(1.0, r * 4.0),                   # 25% reviews already very high
        1.0 - min(1.0, recip * 25.0),        # 4% reciprocity ⇒ consolidated
        1.0 - min(1.0, max(0.0, m - 0.30) * 3.0),  # <=0.30 max, >0.60 zero
    ]
    terms = [max(0.0, min(1.0, t)) for t in terms]
    return round(sum(terms) / len(terms), 3)


def method_transfer_score(f: dict) -> float:
    """Hypothesis: structural-hole leads (method-transfer) need HIGH
    modularity (distinct clusters that could borrow from each other)
    AND intra-corpus references present so we can detect the "weakly
    bridged" case at all.

    This is the ONE composite our own domain provides a directional
    anchor for: llm-calibration produced structural-hole leads at
    N=113, so the predictor should place it somewhere in the middle-
    to-high band, not at the extremes."""
    m = f["citation_modularity"]
    ic = f["intracorpus_reference_rate"]
    terms = [
        min(1.0, max(0.0, m) * 2.5),         # 0.40 already good, 0.60+ saturated
        min(1.0, ic * 20.0),                 # 5% intra-refs already saturated
    ]
    return round(sum(terms) / len(terms), 3)


def verdict(f: dict) -> dict[str, Any]:
    """Bundle the two scores plus a plain-language read."""
    c = contested_score(f)
    mt = method_transfer_score(f)

    def band(x: float) -> str:
        if x >= 0.65: return "high"
        if x >= 0.40: return "moderate"
        return "low"

    return {
        "contested_score": c,
        "contested_band": band(c),
        "method_transfer_score": mt,
        "method_transfer_band": band(mt),
        "caveat": (
            "These scores are HYPOTHESIS-DRIVEN, not validated. The "
            "predictor has been calibrated on a single ground-truth "
            "domain (n=1). Treat as a discussion aid, not a decision."
        ),
    }
