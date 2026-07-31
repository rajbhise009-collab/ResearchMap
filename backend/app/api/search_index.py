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
    """Lowercase -> alphanumeric runs -> drop stopwords/short -> stem."""
    return [t for t, _ in tokenize_pairs(text)]


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

    # Terms seen exactly once are usually typos or one-off strings; keeping
    # them bloats the payload without helping either matching or the gate.
    vocab = {t: c for t, c in df.items() if c >= 2}
    idf = {t: math.log((n_docs + 1) / (c + 0.5)) for t, c in vocab.items()}
    max_idf = max(idf.values()) if idf else 1.0

    out_docs = []
    for d in docs:
        tf = Counter(t for t in d["tokens"] if t in idf)
        if not tf:
            continue
        peak = max(tf.values())
        weights = {t: (0.5 + 0.5 * c / peak) * idf[t] for t, c in tf.items()}
        top = dict(sorted(weights.items(), key=lambda kv: -kv[1])[:TOP_TERMS_PER_DOC])
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
# strong document match, not a faint one.
RESCUE_COVERAGE = 0.28
RESCUE_BEST = 0.20
# How much of the library has to say *something* before we claim the subject
# is covered. A question built entirely from generic machine-learning words
# ("image recognition accuracy") is understood word-for-word and will match a
# handful of papers, but the library holds no body of work on it — breadth is
# what tells those apart from a question this library is genuinely about.
BREADTH_IN_DOMAIN = 0.18


def search(index: dict[str, Any], query: str, limit: int = 20) -> dict[str, Any]:
    """Returns verdict (`in_domain` | `borderline` | `out_of_domain` |
    `empty`) plus ranked hits and the numbers behind the decision."""
    pairs = tokenize_pairs(query)
    words = [w for _, w in pairs]
    base = [t for t, _ in pairs]
    idf: dict[str, float] = index["idf"]
    max_idf: float = index["max_idf"]

    if not base:
        return {"verdict": "empty", "coverage": 0.0, "best": 0.0,
                "breadth": 0.0, "hits": [], "n_matched": 0,
                "known": [], "unknown": [], "expanded": []}

    # A word counts as understood if the library uses it, or if it is
    # everyday phrasing for something the library does use ("make things up"
    # -> hallucination). Words in neither camp are genuinely foreign, and
    # that is what the out-of-domain answer rests on.
    def understood(tok: str, word: str) -> bool:
        if tok in idf:
            return True
        return any(_stem(s) in idf for s in DOMAIN_SYNONYMS.get(word, []))

    known = [t for t, w in pairs if understood(t, w)]
    unknown = [t for t, w in pairs if not understood(t, w)]
    known_mass = sum(idf.get(t, max_idf) for t in known)
    unknown_mass = len(unknown) * max_idf * UNKNOWN_WEIGHT
    coverage = known_mass / (known_mass + unknown_mass) if (known_mass + unknown_mass) else 0.0

    expanded = expand_query(base, words)
    qtf = Counter(t for t in expanded if t in idf)
    qvec: dict[str, float] = {}
    if qtf:
        peak = max(qtf.values())
        qw = {t: (0.5 + 0.5 * c / peak) * idf[t] for t, c in qtf.items()}
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
    hits.sort(key=lambda h: -h["score"])
    best = hits[0]["score"] if hits else 0.0
    breadth = len(hits) / index["n_docs"] if index["n_docs"] else 0.0

    if coverage >= IN_DOMAIN_COVERAGE and best >= IN_DOMAIN_BEST and breadth >= BREADTH_IN_DOMAIN:
        verdict = "in_domain"
    elif coverage >= IN_DOMAIN_COVERAGE and best > 0:
        # We understood every word, but the library holds only a thin scatter
        # on it — the edge of what it covers, and we say so.
        verdict = "borderline"
    elif coverage >= RESCUE_COVERAGE and best >= RESCUE_BEST:
        verdict = "borderline"
    else:
        verdict = "out_of_domain"

    return {"verdict": verdict, "coverage": round(coverage, 4),
            "best": round(best, 5), "breadth": round(breadth, 4),
            "hits": hits[:limit], "n_matched": len(hits),
            "known": known, "unknown": unknown,
            "expanded": sorted(set(qvec))}


def load(path) -> dict[str, Any]:
    return json.loads(open(path).read())
