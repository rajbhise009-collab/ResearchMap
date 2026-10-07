"""Search index — built offline, searched in the browser. Costs nothing.

The library's own paper embeddings were made with a paid embedding model.
Embedding a *new* user query into that same space would mean a paid call
per search, and it would need a live backend — which the static export
does not have. So search here is built the other way round: we compute a
term-weight index over the library's own words at build time, ship it as
JSON, and match queries against it in the browser. No network, no spend,
no server.

That choice is also what makes the honest out-of-domain answer possible.
Because the index knows the library's whole vocabulary, it can tell the
difference between "I have nothing on this" and "I have something weak" —
a query about cardiology shares almost no meaningful vocabulary with this
library, and we can say so plainly instead of returning the least-bad
match dressed up as a result.

`tokenize()` here and `tokenize()` in frontend/lib/search.ts must stay in
lockstep; a test pins them against shared fixtures.
"""

from __future__ import annotations

import json
import math
import re
from collections import Counter
from typing import Any, Iterable

# Words carrying no topical signal. Deliberately short — over-stripping
# hurts the domain gate, since a query made only of stopwords should read
# as "no signal", not as "out of domain".
STOPWORDS = {
    "the", "and", "for", "are", "but", "not", "you", "all", "can", "her",
    "was", "one", "our", "out", "his", "has", "had", "how", "its", "who",
    "did", "does", "why", "what", "when", "which", "with", "that", "this",
    "these", "those", "from", "they", "them", "their", "there", "here",
    "have", "been", "were", "will", "would", "could", "should", "about",
    "into", "than", "then", "some", "such", "only", "other", "more", "most",
    "any", "get", "got", "use", "used", "using", "make", "makes", "made",
    "way", "ways", "does", "doing", "done", "just", "also", "very", "much",
    "many", "well", "even", "still", "yet", "own", "same", "both", "each",
    "between", "over", "under", "after", "before", "while", "during",
    "because", "where", "whether", "being", "again", "further", "once",
}
# Deliberately NOT stopwords: "know", "tell", "trust", "sure", "admit".
# "Does the model know when it doesn't know?" is the central question of
# this entire library — stripping those words would make its own subject
# unsearchable.

# Consumer phrasing -> the library's own vocabulary. Without this, someone
# asking "why does it make things up" gets nothing, while the library is
# full of papers on exactly that under the word "hallucination". Every
# entry maps everyday words onto terminology the papers actually use.
DOMAIN_SYNONYMS = {
    "lie": ["hallucination", "false", "fabricat"],
    "lies": ["hallucination", "false", "fabricat"],
    "lying": ["hallucination", "false", "fabricat"],
    "made": ["hallucination", "fabricat"],
    "invent": ["hallucination", "fabricat"],
    "invents": ["hallucination", "fabricat"],
    "fake": ["hallucination", "fabricat", "false"],
    "wrong": ["error", "incorrect", "accuracy"],
    "false": ["hallucination", "factual", "incorrect"],
    "confident": ["confidence", "calibration", "overconfidence"],
    "confidence": ["calibration", "confidence", "uncertainty"],
    "overconfident": ["overconfidence", "calibration", "miscalibration"],
    "sure": ["confidence", "certainty", "calibration"],
    "unsure": ["uncertainty", "abstention", "calibration"],
    "guess": ["uncertainty", "prediction", "confidence"],
    "guessing": ["uncertainty", "prediction", "confidence"],
    "refuse": ["abstention", "refusal", "abstain"],
    "refusal": ["abstention", "refusal", "abstain"],
    "decline": ["abstention", "abstain"],
    "admit": ["abstention", "uncertainty"],
    "trust": ["trustworthy", "reliability", "calibration"],
    "trustworthy": ["trustworthy", "reliability"],
    "reliable": ["reliability", "robustness", "trustworthy"],
    "unreliable": ["reliability", "hallucination", "error"],
    "chatbot": ["llm", "language", "model", "conversational"],
    "chatgpt": ["gpt", "llm", "language", "model"],
    "gpt": ["gpt", "llm", "language", "model"],
    "llm": ["llm", "language", "model"],
    "ai": ["model", "llm", "language"],
    "bot": ["llm", "model", "conversational"],
    "citation": ["citation", "reference", "fabricat"],
    "citations": ["citation", "reference", "fabricat"],
    "source": ["citation", "reference", "retrieval", "grounding"],
    "sources": ["citation", "reference", "retrieval", "grounding"],
    "medical": ["clinical", "medical", "health"],
    "medicine": ["clinical", "medical", "health"],
    "doctor": ["clinical", "medical"],
    "know": ["knowledge", "uncertainty", "abstention"],
    "knows": ["knowledge", "uncertainty", "abstention"],
    "aware": ["awareness", "uncertainty", "knowledge"],
    "admits": ["abstention", "uncertainty"],
    "answer": ["answer", "question", "response"],
    "answers": ["answer", "question", "response"],
    "tells": ["response", "answer", "generation"],
    "tell": ["response", "answer", "generation"],
    "safe": ["safety", "risk", "reliability"],
    "safety": ["safety", "risk"],
    "risk": ["risk", "safety"],
    "measure": ["quantification", "evaluation", "metric"],
    "measuring": ["quantification", "evaluation", "metric"],
    "detect": ["detection", "detect"],
    "detecting": ["detection", "detect"],
    "check": ["verification", "detection", "fact"],
    "checking": ["verification", "detection", "fact"],
    "verify": ["verification", "fact", "grounding"],
    "explain": ["explainability", "interpretability"],
    "explanation": ["explainability", "interpretability"],
    "understand": ["interpretability", "explainability"],
}


def _stem(w: str) -> str:
    """Crude suffix stripping. Must match the TypeScript twin exactly."""
    for suf, repl in (("ies", "y"), ("ing", ""), ("edly", ""), ("ly", ""),
                      ("ed", ""), ("es", ""), ("s", "")):
        if len(w) > len(suf) + 2 and w.endswith(suf):
            return w[: -len(suf)] + repl
    return w


def tokenize_pairs(text: str) -> list[tuple[str, str]]:
    """(stem, original word) for every content word. Keeping the original
    alongside the stem is what lets the domain gate consult the everyday-
    phrasing table, which is keyed on unstemmed words."""
    out: list[tuple[str, str]] = []
    for raw in re.findall(r"[a-z0-9]+", (text or "").lower()):
        # "ai" and "llm" are two- and three-letter words that a reader is more
        # likely to type than anything else in this subject, so short tokens
        # survive when the everyday-phrasing table knows them.
        too_short = len(raw) < 3 and raw not in DOMAIN_SYNONYMS
        if too_short or raw in STOPWORDS or raw.isdigit():
            continue
        stem = _stem(raw)
        if stem in STOPWORDS:
            continue
        out.append((stem, raw))
    return out


def tokenize(text: str) -> list[str]:
    """Lowercase -> alphanumeric runs -> drop stopwords/short -> stem.

    Returns single-word stems plus bigrams (stem_a__stem_b) for every
    adjacent token pair. The index builder keeps bigrams that appear
    in ≥ `PHRASE_MIN_DOC_FREQ` docs so core multi-word phrases like
    "demographic parity" register as a single vocab entry, which both
    boosts their retrieval weight and makes a bare phrase query land
    as in_domain instead of a weaker two-word intersection.
    """
    pairs = tokenize_pairs(text)
    singles = [t for t, _ in pairs]
    bigrams = [f"{singles[i]}__{singles[i+1]}"
                for i in range(len(singles) - 1)]
    return singles + bigrams


# Mimimum document frequency for a bigram/trigram to survive. ≤2 is
# usually noise; 3 has worked across all 3 current libraries as the
# "a real phrase, not a coincidental two-word adjacency" boundary.
PHRASE_MIN_DOC_FREQ = 3


def expand_query(tokens: Iterable[str], raw_words: Iterable[str]) -> list[str]:
    """Add domain vocabulary implied by everyday words in the query."""
    out = list(tokens)
    for w in raw_words:
        for syn in DOMAIN_SYNONYMS.get(w, []):
            out.append(_stem(syn))
    return out


def raw_words(text: str) -> list[str]:
    return [w for w in re.findall(r"[a-z0-9]+", (text or "").lower()) if len(w) >= 2]


# --------------------------------------------------------------------------
# Index construction
# --------------------------------------------------------------------------

TOP_TERMS_PER_DOC = 45
# Separate single-vs-bigram caps so bigrams (which outnumber singles 10×
# in some libraries and tend to have higher idf) don't evict single
# content words like "hallucination" from a doc's term vector.
TOP_SINGLES_PER_DOC = 45
TOP_BIGRAMS_PER_DOC = 25


def _doc_text_for_opportunity(card: dict[str, Any], consumer: dict[str, Any]) -> str:
    parts = [consumer["headline"], consumer["kind"], consumer["why"]]
    for e in card.get("evidence_trail", []):
        if e.get("text"):
            parts.append(e["text"])
    for p in card.get("supporting_papers", []):
        if p.get("title"):
            parts.append(p["title"])
    return " ".join(parts)


def _doc_text_for_paper(detail: dict[str, Any]) -> str:
    parts = [detail.get("title") or "", detail.get("abstract") or ""]
    for c in detail.get("claims", []):
        parts.append(c.get("text") or "")
    for l in detail.get("limitations", []):
        parts.append(l.get("text") or "")
        parts.append((l.get("normalized_category") or "").replace("-", " "))
    for f in detail.get("future_work", []):
        parts.append(f.get("text") or "")
    for m in detail.get("methodologies", []):
        parts.append(m.get("name") or "")
    return " ".join(parts)


def _compute_gate_thresholds(out_docs: list[dict[str, Any]],
                              n_docs: int) -> dict[str, float]:
    """Pick per-library gate thresholds from the library's own data.

    The default constants below were tuned against LLM-calibration,
    whose central term "calibration" appears in ~40% of docs. On a
    narrower library (Diet: top-breadth term is "disease" at ~16%;
    ML-fairness: "fairness" at ~9%), the same thresholds mislabel the
    library's OWN subject as "borderline".

    Rule: pick `in_domain_breadth` so the library's top-5 highest-
    breadth non-stopword terms clear it. Floor it at 0.03 so a very
    thin library can't drop the gate to zero. Ceiling at the LLM-cal
    default so a wide library doesn't accidentally loosen it.
    """
    # Pick a breadth threshold the library's defining terms clear.
    #
    # The original LLM-cal-tuned 0.18 breadth gate turned out to be too
    # tight for every library — including LLM-cal itself. Its own central
    # terms like `hallucination` (0.127) and `calibration` (0.095) sit
    # well below 0.18 and were being reported as "borderline" instead of
    # in-domain. On the thinner libraries the same gate hid their
    # defining subjects: `alcohol` on Diet is 0.093, `fairness` on
    # ml-fairness is 0.090.
    #
    # Empirically across the current 3 libraries, a flat 0.045 lets the
    # defining-subject terms through while keeping the real OOD queries
    # ("treatment for melanoma", "camera calibration for stereo vision")
    # OOD via the coverage gate. The breadth gate's actual job in the
    # bigger picture is just to block the "every word is a stopword-like
    # common ML word" collision case, which rarely clears 2-3% breadth
    # on any library.
    #
    # Kept as a per-library field so a future narrow library can tighten
    # it (via a hand override on the stats pipeline) without changing
    # the shipped constant.
    # Floor at 0.045 for smaller libraries (n<150). For bigger ones
    # (LLM-cal n=189) use a slightly higher gate so a 15-paper common-
    # word collision doesn't look in_domain.
    in_domain_breadth = 0.09 if n_docs >= 150 else 0.045
    # Best-score gate: the thin libraries need a lower bar too, since
    # a single-term query over a smaller corpus produces smaller
    # per-doc cosine scores. Scale with corpus size.
    in_domain_best = max(0.025, min(0.05, 5.0 / max(50, n_docs)))
    # Keep coverage + rescue thresholds library-independent; those are
    # vocabulary-coverage, not corpus-density, and already behave on
    # all three libraries.
    return {
        "in_domain_coverage": IN_DOMAIN_COVERAGE,
        "in_domain_best": round(in_domain_best, 4),
        "in_domain_breadth": round(in_domain_breadth, 4),
        "rescue_coverage": RESCUE_COVERAGE,
        "rescue_best": RESCUE_BEST,
        "rescue_breadth": RESCUE_BREADTH,
    }


def build_index(opportunities: list[dict[str, Any]],
                papers: list[dict[str, Any]]) -> dict[str, Any]:
    """Term-weight index over the library. `opportunities` carry a
    `consumer` block; `papers` are full detail records."""
    docs: list[dict[str, Any]] = []

    for card in opportunities:
        docs.append({
            "type": "opportunity",
            "ref": card["slug"],
            "title": card["consumer"]["headline"],
            "kind": card["consumer"]["kind_id"],
            "strength": card["consumer"]["strength"],
            "tokens": tokenize(_doc_text_for_opportunity(card, card["consumer"])),
        })
    for p in papers:
        docs.append({
            "type": "paper",
            "ref": p["wid"],
            "title": p.get("title") or p["wid"],
            "kind": "paper",
            "strength": "",
            "tokens": tokenize(_doc_text_for_paper(p)),
        })

    n_docs = len(docs)
    df = Counter()
    for d in docs:
        df.update(set(d["tokens"]))

    # Single-word terms seen exactly once are usually typos or one-off
    # strings; keeping them bloats the payload without helping either
    # matching or the gate. Bigrams (containing "__") need the stricter
    # PHRASE_MIN_DOC_FREQ because many two-word adjacencies are
    # coincidental; only phrases that recur in several papers are real
    # multi-word subjects.
    def _keep(term: str, c: int) -> bool:
        if "__" in term:
            return c >= PHRASE_MIN_DOC_FREQ
        return c >= 2
    vocab = {t: c for t, c in df.items() if _keep(t, c)}
    idf = {t: math.log((n_docs + 1) / (c + 0.5)) for t, c in vocab.items()}
    max_idf = max(idf.values()) if idf else 1.0

    out_docs = []
    for d in docs:
        tf = Counter(t for t in d["tokens"] if t in idf)
        if not tf:
            continue
        peak = max(tf.values())
        weights = {t: (0.5 + 0.5 * c / peak) * idf[t] for t, c in tf.items()}
        # Keep the top-N single words AND the top-M bigrams separately,
        # then union. This prevents bigrams (high-idf, abundant) from
        # evicting content singles like "hallucination" from a doc's
        # term vector.
        singles_sorted = sorted(
            ((t, w) for t, w in weights.items() if "__" not in t),
            key=lambda kv: -kv[1])[:TOP_SINGLES_PER_DOC]
        bigrams_sorted = sorted(
            ((t, w) for t, w in weights.items() if "__" in t),
            key=lambda kv: -kv[1])[:TOP_BIGRAMS_PER_DOC]
        top = dict(singles_sorted + bigrams_sorted)
        # A document's own title (a gap's headline, a paper's title) is what
        # a reader types. Its words always stay in the vector, at their
        # computed weight, even when a very common word (e.g. "fairness" in
        # the fairness library) would otherwise be cut by the top-N limit.
        for t in tokenize(d["title"]):
            if t in weights and t not in top:
                top[t] = weights[t]
        norm = math.sqrt(sum(v * v for v in top.values())) or 1.0
        out_docs.append({
            "type": d["type"], "ref": d["ref"], "title": d["title"],
            "kind": d["kind"], "strength": d["strength"],
            "terms": {t: round(v / norm, 4) for t, v in top.items()},
        })

    return {
        "n_docs": n_docs,
        "max_idf": round(max_idf, 4),
        "idf": {t: round(v, 4) for t, v in idf.items()},
        "docs": out_docs,
        "synonyms": DOMAIN_SYNONYMS,
        "stopwords": sorted(STOPWORDS),
        # Per-library gate thresholds derived from THIS library's data.
        # The frontend's `search()` reads these when present; absent =
        # falls back to the LLM-cal-tuned constants.
        "gate": _compute_gate_thresholds(out_docs, n_docs),
    }


# --------------------------------------------------------------------------
# The domain gate — the honest bit. Mirrored in TypeScript for the browser;
# kept here so it can be tested directly.
# --------------------------------------------------------------------------

# An absent word is the loudest signal there is. Nobody types "melanoma" by
# accident, so a word the library has never seen is almost always the
# subject of the question — and it has to outweigh the handful of ordinary
# English words ("treatment", "stage", "early") that surround it and that
# happen to appear somewhere in any large body of text. Hence the multiplier:
# one unknown word costs more than several bland known ones.
UNKNOWN_WEIGHT = 3.5

IN_DOMAIN_COVERAGE = 0.62
IN_DOMAIN_BEST = 0.05
# A weak-vocabulary query is only rescued into "borderline" by a genuinely
# strong document match, not a faint one — AND enough documents matching
# that the topic really has a foothold in the library. Breadth is what stops
# the failure mode this project has documented six times: "calibration of
# medical imaging equipment" uses "calibration" and "medical" correctly but
# in an unrelated sense. Both are frequent enough that one high-scoring
# document exists (an EHR-LLM paper stacking "medical" hits), but only a
# handful of documents match — no body of work — so breadth catches it
# where coverage and best alone did not.
RESCUE_COVERAGE = 0.28
RESCUE_BEST = 0.20
RESCUE_BREADTH = 0.24
# How much of the library has to say *something* before we claim the subject
# is covered. A question built entirely from generic machine-learning words
# ("image recognition accuracy") is understood word-for-word and will match a
# handful of papers, but the library holds no body of work on it — breadth is
# what tells those apart from a question this library is genuinely about.
BREADTH_IN_DOMAIN = 0.18


def search(index: dict[str, Any], query: str, limit: int = 20,
            *, prefix_last: bool = False,
            expand_trailing: bool = False) -> dict[str, Any]:
    """Returns verdict + ranked hits and the numbers behind the decision.

    `verdict` is one of `in_domain` | `borderline` | `out_of_domain` |
    `empty` | `typing`. `typing` is new: it means "the trailing word is
    still being spelled out and the complete-token count of what's been
    typed so far isn't enough to form a verdict". The UI should treat
    `typing` like "show results, no banner" — never render a refusal.

    `prefix_last` is for type-ahead: when True, the LAST whitespace-
    terminated token of the raw query is treated as a prefix and
    expanded against the vocabulary (any term whose stem starts with
    the typed prefix joins the retrieval set). The verdict is computed
    EXCLUDING that trailing prefix token so a half-typed word cannot
    produce an out_of_domain label.

    `expand_trailing` is for the Enter / Ask path: if the trailing
    token has prefix matches, treat the user as having typed its best
    match (highest DF — the most common library term starting with
    those letters) for BOTH retrieval AND verdict. So "alc" + Enter
    behaves like "alcohol" + Enter.
    """
    pairs = tokenize_pairs(query)
    words = [w for _, w in pairs]
    base = [t for t, _ in pairs]
    idf: dict[str, float] = index["idf"]
    max_idf: float = index["max_idf"]

    # Prefix expansion for the last typed word (if it isn't already a
    # vocab entry). The TOKENIZER drops words shorter than 3 chars; we
    # mirror that threshold here so one- or two-letter trailing text is
    # ignored entirely — otherwise typing "a" against Diet would expand
    # into every vocab term starting with "a".
    prefix_added: list[str] = []
    trailing_is_prefix = False
    # The best prefix expansion (highest DF) — used by expand_trailing
    # and surfaced in the result so the UI can offer a neutral hint
    # like "Showing matches for 'alc…'".
    best_prefix: str | None = None
    if (prefix_last or expand_trailing) and query and not query[-1].isspace():
        last_raw = re.findall(r"[a-z0-9]+", query.lower())
        tail = last_raw[-1] if last_raw else ""
        if tail and len(tail) >= 3:
            tail_stem = _stem(tail)
            if tail_stem not in idf:
                matches = [t for t in idf
                            if t.startswith(tail_stem) and "__" not in t]
                if matches:
                    trailing_is_prefix = True
                    prefix_added = matches
                    # Pick the highest-DF match as the "most likely
                    # finish". `idf` is log((n+1)/(df+0.5)) — lower idf
                    # ⇒ higher df ⇒ more frequent in the corpus.
                    best_prefix = min(matches, key=lambda t: idf[t])
            elif prefix_last and not expand_trailing:
                # A complete vocab word that is also the start of a MORE
                # frequent library term ("fair" -> "fairness") is still
                # being typed. Typing-time only: Enter never rewrites a
                # real word.
                longer = [t for t in idf if t != tail_stem and "__" not in t
                          and t.startswith(tail_stem) and idf[t] < idf[tail_stem]]
                if longer:
                    trailing_is_prefix = True
                    prefix_added = longer
                    best_prefix = min(longer, key=lambda t: idf[t])

    # On Enter / Ask: swap the trailing prefix out of `pairs` for its
    # best completion so coverage and the whole-query verdict read as
    # if the full word had been typed.
    if expand_trailing and trailing_is_prefix and best_prefix is not None:
        if pairs and _stem(pairs[-1][1]) not in idf:
            pairs = pairs[:-1] + [(best_prefix, best_prefix)]
            base = [t for t, _ in pairs]
            words = [w for _, w in pairs]
            trailing_is_prefix = False   # it's a complete token now

    if not base and not prefix_added:
        return {"verdict": "empty", "coverage": 0.0, "best": 0.0,
                "breadth": 0.0, "hits": [], "n_matched": 0,
                "known": [], "unknown": [], "expanded": [],
                "typing": False, "trailing_prefix": None}

    # A word counts as understood if the library uses it, or if it is
    # everyday phrasing for something the library does use ("make things up"
    # -> hallucination). Words in neither camp are genuinely foreign, and
    # that is what the out-of-domain answer rests on.
    def understood(tok: str, word: str) -> bool:
        if tok in idf:
            return True
        return any(_stem(s) in idf for s in DOMAIN_SYNONYMS.get(word, []))

    # Exclude the trailing-prefix token from the known/unknown
    # classification — it's still being typed, so it cannot push the
    # verdict either way. Keep it ONLY in the retrieval set below.
    verdict_pairs = (pairs[:-1] if trailing_is_prefix else list(pairs))
    known = [t for t, w in verdict_pairs if understood(t, w)]
    unknown = [t for t, w in verdict_pairs if not understood(t, w)]
    known_mass = sum(idf.get(t, max_idf) for t in known)
    unknown_mass = len(unknown) * max_idf * UNKNOWN_WEIGHT
    coverage = (known_mass / (known_mass + unknown_mass)
                if (known_mass + unknown_mass) else 0.0)

    # Adjacent-pair bigrams: so a query like "demographic parity" matches
    # the shipped bigram vocab entry `demographic__parity` (indexed when
    # the phrase appears in ≥PHRASE_MIN_DOC_FREQ docs) and lands on the
    # library's own technical concept rather than the two-word
    # intersection.
    bigrams = [f"{base[i]}__{base[i+1]}" for i in range(len(base) - 1)]
    expanded = expand_query(base, words) + bigrams + prefix_added
    qtf = Counter(t for t in expanded if t in idf)
    qvec: dict[str, float] = {}
    if qtf:
        peak = max(qtf.values())
        # Exact-token matches should rank above prefix-only matches, so
        # halve the TF weight of terms that only appeared via prefix
        # expansion. This keeps "alcohol" matching the alcohol gaps
        # before any random "alcohol-related" term from a prefix query.
        prefix_set = set(prefix_added) - set(base)
        qw = {t: (0.5 + 0.5 * c / peak) * idf[t] * (0.5 if t in prefix_set else 1.0)
              for t, c in qtf.items()}
        norm = math.sqrt(sum(v * v for v in qw.values())) or 1.0
        qvec = {t: v / norm for t, v in qw.items()}

    hits = []
    for d in index["docs"]:
        terms = d["terms"]
        score = sum(w * terms[t] for t, w in qvec.items() if t in terms)
        if score > 0:
            matched = sorted((t for t in qvec if t in terms),
                             key=lambda t: -qvec[t] * terms[t])[:6]
            hits.append({"type": d["type"], "ref": d["ref"], "title": d["title"],
                         "kind": d["kind"], "strength": d["strength"],
                         "score": round(score, 5), "matched": matched})
    # Rank: higher score first; gaps (type=opportunity) above papers on tie.
    hits.sort(key=lambda h: (-h["score"], 0 if h["type"] == "opportunity" else 1))
    best = hits[0]["score"] if hits else 0.0
    breadth = len(hits) / index["n_docs"] if index["n_docs"] else 0.0

    # Per-library gate thresholds live on the index; the LLM-cal-tuned
    # constants are the fallback for an older index without them.
    g = index.get("gate") or {}
    in_cov  = float(g.get("in_domain_coverage", IN_DOMAIN_COVERAGE))
    in_best = float(g.get("in_domain_best",     IN_DOMAIN_BEST))
    in_br   = float(g.get("in_domain_breadth",  BREADTH_IN_DOMAIN))
    r_cov   = float(g.get("rescue_coverage",    RESCUE_COVERAGE))
    r_best  = float(g.get("rescue_best",        RESCUE_BEST))
    r_br    = float(g.get("rescue_breadth",     RESCUE_BREADTH))

    # Specific-term bypass: a query whose understood tokens (singles OR
    # bigrams) are highly specific to this library — very high IDF, e.g.
    # "COMPAS", "demographic parity", "semantic entropy" — gets
    # in_domain even when only a handful of papers mention it. Rare
    # technical terms don't need the breadth gate; one or two
    # authoritative hits is the signal. Only applies when coverage is
    # 1.0 (every token known) so a rare word beside an OOD one can't
    # sneak through.
    HIGH_IDF = max_idf * 0.55
    matched_specifically = [t for t in qvec if idf.get(t, 0.0) >= HIGH_IDF]
    specific_hit = (coverage >= 0.95 and best > 0
                    and matched_specifically and breadth > 0)

    if coverage >= in_cov and best >= in_best and breadth >= in_br:
        verdict = "in_domain"
    elif specific_hit:
        verdict = "in_domain"
    elif coverage >= in_cov and best > 0:
        # We understood every word, but the library holds only a thin scatter
        # on it — the edge of what it covers, and we say so.
        verdict = "borderline"
    elif coverage >= r_cov and best >= r_best and breadth >= r_br:
        verdict = "borderline"
    else:
        verdict = "out_of_domain"

    # TYPING state: a half-typed trailing word must never land as
    # out_of_domain. If the complete tokens (verdict_pairs) are empty
    # OR the only "signal" came from the trailing prefix, call it
    # "typing" — the UI treats it as "show results, no banner". When
    # the complete tokens by themselves ARE in_domain / borderline,
    # keep that verdict (user is specifying further, not asking
    # something foreign).
    # Complete tokens still drive refusal: "camera cal" is refused on
    # account of "camera" (after the UI's pause), not held in "typing".
    if trailing_is_prefix and not verdict_pairs:
        verdict = "typing"

    return {"verdict": verdict, "coverage": round(coverage, 4),
            "best": round(best, 5), "breadth": round(breadth, 4),
            # Mirrors lib/search.ts: gaps and papers capped separately
            # (shown in separate sections), then merged in score order.
            "hits": sorted([h for h in hits if h["type"] == "opportunity"][:limit]
                           + [h for h in hits if h["type"] != "opportunity"][:limit],
                           key=lambda h: (-h["score"], 0 if h["type"] == "opportunity" else 1)),
            "n_matched": len(hits),
            "known": known, "unknown": unknown,
            "expanded": sorted(set(qvec)),
            "typing": trailing_is_prefix,
            "trailing_prefix": best_prefix}


def load(path) -> dict[str, Any]:
    return json.loads(open(path).read())
