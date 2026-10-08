"""THE translation layer — the single source of truth for every word the
consumer UI shows.

Nothing else in the stack is allowed to invent user-facing copy. The
frontend reads this module's output (baked into the static snapshot as
`consumer` blocks + `language.json`); it does not carry its own strings.

Two hard rules, both enforced by tests:

1. **No system jargon reaches the reader.** "orphaned future-work",
   "structural hole", "scorer", "corpus", "trust" and friends are
   internal vocabulary. They are translated here or they do not ship.
   The only jargon allowed through is research-domain terminology that
   comes from the papers themselves (e.g. "hallucination",
   "calibration", "token-probability access") — that is the subject
   matter, not our plumbing.

2. **No numeric internals reach the reader.** No trust value, no score,
   no confidence decimal, no cosine, no manifest hash. Plain counts of
   real-world things ("4 separate teams", "9 years") are facts about the
   research, not system internals, and are allowed.

Weakness must read *more* clearly in plain English, never less. Strength
is a word with a sentence explaining it — never a bar, tick or percentage.
"""

from __future__ import annotations

import re
from typing import Any

# --------------------------------------------------------------------------
# What this tool is, and what it currently covers.
# --------------------------------------------------------------------------

TAGLINE = "Find research questions nobody has answered yet."

WHAT_IT_DOES = (
    "This tool reads a library of research papers on one subject and looks "
    "for gaps — questions a paper said needed studying that no later paper "
    "in the library followed up on, problems that several teams ran into, "
    "findings that appear to disagree, and methods from one line of work "
    "that might help with a problem in another."
)

# Shown directly under the headline (which stays as written).
HEADLINE_QUALIFIER = (
    "Results come only from the papers in the selected library. They are a "
    "starting point for reading, not a verdict."
)

LIBRARY_NAME = "Language-model reliability"

LIBRARY_COVERS = (
    "how language models express confidence, when they should refuse to "
    "answer, how their uncertainty is measured, and why they state false "
    "things as fact"
)

LIBRARY_SUMMARY = (
    f"Right now the library holds 113 papers on {LIBRARY_COVERS}."
)

# The honest boundary. One domain, because building another costs real
# money and hours of batch processing.
ONE_LIBRARY_NOTE = (
    "This tool searches one library at a time. Each library is built one "
    "subject at a time by reading its papers with an AI model, so only a "
    "few subjects are covered so far."
)

# --------------------------------------------------------------------------
# Strength. Three words, each with a sentence saying what it means.
# Never a number, never a bar.
# --------------------------------------------------------------------------

STRONG = "Strong"
WORTH_A_LOOK = "Worth a look"
UNVERIFIED = "Unverified lead"

STRENGTH_MEANING = {
    STRONG: (
        "Several independent papers point at this, and we could read their "
        "full text to check."
    ),
    WORTH_A_LOOK: (
        "There is real evidence behind this, but it rests on a small number "
        "of papers — read them before trusting it."
    ),
    UNVERIFIED: (
        "This is a pattern we spotted automatically and have not verified. "
        "Treat it as a hint to investigate, not a finding."
    ),
}

STRENGTH_ORDER = {STRONG: 0, WORTH_A_LOOK: 1, UNVERIFIED: 2}


def strength_for(card: dict[str, Any]) -> str:
    """Plain-English strength label for one result.

    A method-transfer lead is never better than "worth a look": it is a
    similarity match between two papers, and unless a human-checked
    confirmation says it is substantive it stays an unverified lead.
    """
    scorer = card.get("scorer")
    tier = card.get("confidence_tier")
    if scorer == "structural_holes":
        return WORTH_A_LOOK if card.get("confirm_status") == "substantive" else UNVERIFIED
    if tier == "high":
        return STRONG
    if tier == "medium":
        return WORTH_A_LOOK
    return UNVERIFIED


# --------------------------------------------------------------------------
# The kinds of gap. Named for what they are, not for the code that found them.
# --------------------------------------------------------------------------

KINDS = {
    "unfollowed_future_work": {
        "id": "unfollowed_future_work",
        "name": "An unfollowed question",
        "short": "A question a paper said needed studying, that nothing else "
                 "in this library followed up on",
        "long": "When researchers finish a paper they usually name the "
                "questions they could not get to. We collected those, then "
                "checked whether any later paper in this library actually "
                "went and did the work. These are the ones where nothing did.",
    },
    "unaddressed_limitation": {
        "id": "unaddressed_limitation",
        "name": "A problem several teams hit",
        "short": "A problem that several independent teams ran into",
        "long": "Papers describe the limits of their own work. When separate "
                "teams — who did not build on each other — keep reporting the "
                "same limit, that is a sign of a real obstacle rather than "
                "one group's bad luck.",
    },
    "method_transfer": {
        "id": "method_transfer",
        "name": "A method that might transfer",
        "short": "A method from one area that might solve a problem in another",
        "long": "Two groups of papers that barely cite each other. One group "
                "has a method; the other reports a problem that method looks "
                "related to. Nobody appears to have tried connecting them — "
                "but we matched them by similarity, so this needs a human to "
                "check whether the connection is real.",
    },
    "disagreement": {
        "id": "disagreement",
        "name": "A disagreement between papers",
        "short": "Two papers whose findings disagree",
        "long": "Two papers in this library that report findings pointing in "
                "opposite directions, where neither resolves the other.",
    },
}

# Internal scorer name -> kind. Kept here so no other module maps it.
SCORER_TO_KIND = {
    "orphaned_future_work": "unfollowed_future_work",
    "persistent_limitations": "unaddressed_limitation",
    "structural_holes": "method_transfer",
    "unresolved_contradictions": "disagreement",
}


def kind_for(card: dict[str, Any]) -> dict[str, str]:
    gap = card.get("gap_type") or SCORER_TO_KIND.get(card.get("scorer", ""), "")
    return KINDS.get(gap, KINDS["unfollowed_future_work"])


# The empty state for disagreements is a finding, not a blank panel.
NO_DISAGREEMENTS = {
    "headline": "No disagreements found among the pairs we checked.",
    "body": (
        "We compared pairs of very similar claims from different papers in "
        "this library, and none was flagged as conflicting. That is a "
        "measurement, not proof that the papers agree: two findings that "
        "disagree but are worded differently are never compared, and papers "
        "outside the library are not included. Why this library shows none "
        "has not been established."
    ),
    "link_label": "Read how we checked",
}

# --------------------------------------------------------------------------
# Caveats — the honest small print, in plain English, always shown inline.
# --------------------------------------------------------------------------

CAVEATS = {
    "corpus_relative": {
        "label": "Only checked within these 113 papers",
        "text": "Nothing in this library followed this up — but this library "
                "is 113 papers, not the whole field. Somebody outside it may "
                "well have answered this already. Check before you invest.",
    },
    "mixed_fidelity": {
        "label": "Based partly on summaries only",
        "text": "For some of these papers we only had the summary, not the "
                "full text. Papers we could read in full reveal far more about "
                "their own limits, so this may be built on an incomplete "
                "picture.",
    },
    "generic_category": {
        "label": "Broadly worded",
        "text": "The problem these papers describe is worded broadly enough "
                "that they may not be running into quite the same thing.",
    },
    "construct_gated": {
        "label": "Narrow reading",
        "text": "This was matched on a specific technical reading of the "
                "topic, so related work phrased differently may have been "
                "missed.",
    },
    "semantic_lead": {
        "label": "A promising match we haven't verified",
        "text": "We matched these two papers because their wording is close, "
                "not because anyone confirmed the connection makes sense. "
                "It may not survive contact with an expert.",
    },
}

CONFIRM_STATUS = {
    "substantive": {
        "label": "Checked — looks like a real connection",
        "text": "We went back over both papers and the method does appear to "
                "address the problem. That check was done by a language model "
                "reading the two papers, not by a specialist, so it raises the "
                "odds without settling them.",
    },
    "trivial": {
        "label": "Checked — the connection is superficial",
        "text": "On re-reading, the two papers only look similar on the "
                "surface. Probably not worth pursuing.",
    },
    "not_addressing": {
        "label": "Checked — the method doesn't address the problem",
        "text": "On re-reading, the method does not actually address the "
                "problem it was matched to.",
    },
    "unconfirmed": {
        "label": "Not checked yet",
        "text": "Nobody has re-read this pair to see whether the connection "
                "is real.",
    },
}

ABSTRACT_ONLY = {
    "label": "Summary only",
    "text": "We only had this paper's summary, not the full text. Papers we "
            "can read in full tell us far more about what went wrong in them, "
            "so we know less about this one than the others.",
}

FULL_TEXT = {"label": "Full text", "text": "We read this paper in full."}


def caveats_for(card: dict[str, Any]) -> list[dict[str, str]]:
    """Plain-English caveats for a result, in the order they should be read."""
    is_hole = card.get("scorer") == "structural_holes"
    status = (card.get("confirm_status") or "unconfirmed") if is_hole else None
    # A lead somebody went back and checked must not also be described as
    # unverified — that reads as a contradiction and undersells a real check.
    # The confirmation note replaces the unverified-match caveat.
    checked = status == "substantive"

    out: list[dict[str, str]] = []
    for c in card.get("caveats", []):
        code = c.get("code", "")
        if checked and code == "semantic_lead":
            continue
        t = CAVEATS.get(code)
        if t:
            out.append({"code": code, **t})
    if is_hole and status:
        cs = CONFIRM_STATUS.get(status)
        if cs:
            out.append({"code": f"confirm_{status}", **cs})
    return out


# --------------------------------------------------------------------------
# Turning stored research terminology into something readable.
# --------------------------------------------------------------------------

# Slugs whose plain reading is genuinely unclear. Everything else is just
# de-slugged, because it is the papers' own terminology and inventing a
# paraphrase for it would be putting words in their mouth.
CATEGORY_OVERRIDES = {
    "task-scope-limitation": "only tested on a narrow set of tasks",
    "black-box-constraint": "no access to the model's internals",
    "black-box-access-restriction": "no access to the model's internals",
    "api-access-constraints": "limited by what the model's API exposes",
    "token-probability-access-required": "needs the model's raw output "
                                         "probabilities, which are often unavailable",
    "output-probability-inaccessibility": "the model's output probabilities "
                                          "were not available",
    "english-only": "only tested in English",
    "small-sample-size": "tested on too few examples",
    "computational-cost": "too expensive to run at scale",
    "lack-of-ground-truth": "no reliable correct answer to compare against",
    "absence-of-ground-truth": "no reliable correct answer to compare against",
    "llm-overconfidence": "the model states wrong answers confidently",
    "model-miscalibration": "the model's stated confidence doesn't match how "
                            "often it is right",
    "hallucinations": "the model states things that are not true",
    "lack-of-theoretical-guarantees": "no mathematical guarantee it works",
    "single-model-evaluated": "only one model was tested",
    "limited-model-scope": "only a few models were tested",
    "prompt-sensitivity": "results change a lot depending on how you word the "
                          "prompt",
    "inference-latency": "too slow to run in real time",
}


def readable_category(slug: str) -> str:
    """`task-scope-limitation` -> `only tested on a narrow set of tasks`."""
    if slug in CATEGORY_OVERRIDES:
        return CATEGORY_OVERRIDES[slug]
    return slug.replace("-", " ").replace("_", " ").strip()


def _sentence(text: str, limit: int = 240) -> str:
    """First clean sentence of a quoted item, trimmed and capitalised."""
    t = " ".join((text or "").split()).strip().strip('"').strip()
    if not t:
        return ""
    if len(t) > limit:
        cut = t[:limit].rsplit(" ", 1)[0]
        t = cut.rstrip(".,;:") + "…"
    return t[0].upper() + t[1:]


def _trail(card: dict[str, Any], kind: str) -> list[dict[str, Any]]:
    return [e for e in card.get("evidence_trail", []) if e.get("kind") == kind]


def _cs(card: dict[str, Any], key: str) -> float | None:
    v = card.get("component_scores", {}).get(key)
    return None if v is None else float(v)


def _int(v: float | None) -> int | None:
    return None if v is None else int(round(v))


# --------------------------------------------------------------------------
# Headlines — what this opportunity IS, in the reader's language, built from
# the papers' own words. Never a template with an internal ID in it.
# --------------------------------------------------------------------------

def headline(card: dict[str, Any]) -> str:
    scorer = card.get("scorer")

    if scorer == "orphaned_future_work":
        items = _trail(card, "future_work")
        if items and items[0].get("text"):
            return _sentence(items[0]["text"])
        return "A question that was raised and never followed up"

    if scorer == "persistent_limitations":
        m = re.search(r"limitation '([^']+)'", card.get("title", ""))
        cat = readable_category(m.group(1)) if m else "the same problem"
        n = _int(_cs(card, "n_independent"))
        who = f"{n} separate teams" if n else "Several separate teams"
        return f"{who} ran into the same wall: {cat}"

    if scorer == "structural_holes":
        m = re.search(r"'([^']+)'", card.get("title", ""))
        method = m.group(1) if m else "A method from another line of work"
        papers = _trail(card, "paper")
        # Evidence-trail paper items carry the title in `text`.
        target = (papers[1].get("title") or papers[1].get("text")) if len(papers) > 1 else None
        if target:
            return f"“{method}” might solve a problem reported by “{_sentence(target, 120)}”"
        return f"“{method}” might solve a problem reported in another line of work"

    if scorer == "unresolved_contradictions":
        return "Two papers report findings that disagree"

    return _sentence(card.get("title", "")) or "A gap in the research"


def why_it_surfaced(card: dict[str, Any]) -> str:
    """One paragraph: why this came up, in plain English, with real facts."""
    scorer = card.get("scorer")

    if scorer == "orphaned_future_work":
        yrs = _int(_cs(card, "years_unfollowed"))
        near = _int(_cs(card, "near_later"))
        papers = _trail(card, "paper")
        src = papers[0].get("title") if papers else None
        bits = ["A paper" if not src else f"The paper “{_sentence(src, 110)}”",
                "said this needed studying."]
        if yrs:
            bits.append(f"That was {yrs} years ago.")
        if near:
            bits.append(
                f"Since then {near} later papers in this library worked on "
                "closely related topics, and none of them took this up."
            )
        else:
            bits.append("No later paper in this library took it up.")
        return " ".join(bits)

    if scorer == "persistent_limitations":
        n = _int(_cs(card, "n_independent"))
        ft = _int(_cs(card, "n_fulltext"))
        span = _int(_cs(card, "timespan"))
        who = f"{n} separate research teams" if n else "Several separate teams"
        s = (f"{who} each reported hitting this in their own work. They did not "
             "build on each other, so this is unlikely to be one group's bad luck.")
        if span:
            s += f" Their papers span {span} years."
        if ft:
            s += (f" We could read {ft} of them in full, which is where teams "
                  "describe what actually went wrong.")
        return s

    if scorer == "structural_holes":
        cross = _int(_cs(card, "cross_citations_AB"))
        s = ("One paper has a method. Another reports a problem the method "
             "looks related to.")
        if cross == 0:
            s += (" The two lines of work never cite each other, so it does not "
                  "look like anyone has tried this.")
        s += (" We matched them by comparing how the two papers are worded — "
              "which is a starting point, not proof.")
        return s

    return card.get("explanation", "")


# --------------------------------------------------------------------------
# Assembling the consumer view of one result.
# --------------------------------------------------------------------------

# A method-transfer lead the confirmation step rejected is not a result:
# it moves to "Set aside after checking". The reason is chosen by code from
# the label; the checker's own wording is not shown.
SET_ASIDE_REASONS = {
    "not_addressing": ("A language-model check found that the method does not actually "
                       "address this problem; the two are related in topic only."),
    "trivial": ("A language-model check found that the idea reduces to running a broader "
                "evaluation or applying a known method to new data."),
}
VISIBLE_VERDICTS = (None, "genuine")


def set_aside_for(card: dict[str, Any]) -> dict[str, str] | None:
    if card.get("scorer") == "structural_holes" and card.get("confirm_status") in SET_ASIDE_REASONS:
        return {"verdict": "set_aside",
                "verdict_label": "Set aside after checking",
                "verdict_reason": SET_ASIDE_REASONS[card["confirm_status"]]}
    return None


def is_visible(card: dict[str, Any]) -> bool:
    """A result counts and is searchable only if nothing set it aside."""
    v = card.get("verdict") or (card.get("consumer") or {}).get("verdict")
    return v in VISIBLE_VERDICTS


def consumer_card(card: dict[str, Any]) -> dict[str, Any]:
    """The plain-English face of one opportunity. No internals cross over."""
    k = kind_for(card)
    s = strength_for(card)
    # An unfollowed question is shown in the researcher's own words, so its
    # headline is a quotation rather than copy we wrote.
    quoted = card.get("scorer") == "orphaned_future_work"
    return {
        "headline_is_quoted": quoted,
        "headline": headline(card),
        "kind": k["name"],
        "kind_id": k["id"],
        "kind_short": k["short"],
        "kind_long": k["long"],
        "strength": s,
        "strength_meaning": STRENGTH_MEANING[s],
        "why": why_it_surfaced(card),
        "caveats": caveats_for(card),
        "paper_count": len(card.get("supporting_papers", [])),
        **(set_aside_for(card) or {}),
    }


def consumer_paper(paper: dict[str, Any]) -> dict[str, Any]:
    """The plain-English face of one paper."""
    ao = bool(paper.get("abstract_only"))
    return {
        "fidelity": ABSTRACT_ONLY if ao else FULL_TEXT,
        "claims_label": "What this paper says it found",
        "limitations_label": "What the authors said didn't work",
        "future_work_label": "What the authors said should be studied next",
        "methods_label": "How they did it",
        "citations_label": "Related papers in this library",
        "no_claims": "We didn't extract any findings from this paper.",
        "no_limitations": (
            "This paper didn't state any limits on its own work — or we only "
            "had its summary, where authors rarely mention them."
            if ao else
            "This paper didn't state any limits on its own work."
        ),
        "no_future_work": "This paper didn't name anything to study next.",
        "no_methods": "We didn't extract a method description from this paper.",
    }


# --------------------------------------------------------------------------
# Search-result framing: in-domain / borderline / out-of-domain.
# --------------------------------------------------------------------------

SEARCH = {
    "placeholder": "What do you want to know about?",
    "hint": "Try: why do language models sound confident when they're wrong?",
    "searching": "Looking through the library…",
    "in_domain": {
        "note": "",
    },
    "borderline": {
        "label": "This is at the edge of what the library covers",
        "note": (
            "We found some related work, but your question sits on the edge of "
            "this library's subject. The results below may be partial — and "
            "there may be plenty of good work on this that simply isn't here."
        ),
    },
    "out_of_domain": {
        "label": "That's not in this library",
        "note": (
            "We didn't find anything on that. Rather than show you weak matches "
            "dressed up as answers, here's the honest position: this library "
            "only covers {covers}."
        ),
        "what_we_have": "What this library does cover",
        "build_cta": "Want a library on this subject?",
    },
    "no_results": {
        "label": "Nothing matched",
        "note": "Your question looks like it's about this library's subject, "
                "but no specific result matched closely enough to show.",
    },
}

# The honest cost of the thing we're offering. Non-functional for now, and
# the UI says so.
BUILD_LIBRARY = {
    "title": "Libraries on new subjects",
    # The only text the consumer view shows. Cost, time and the pre-flight
    # predictor are developer-mode details (?dev=1): nothing here may imply
    # a purchase or a build that runs from this page.
    "consumer_body": (
        "Libraries are built one subject at a time, and there isn't one on "
        "this subject yet. If you'd like one, you can suggest it on the "
        "contact page."
    ),
    "body": (
        "A library is built by collecting papers on a subject and reading each "
        "one with an AI model to pull out what it found, what didn't work, and "
        "what it said should be studied next. That is the expensive part."
    ),
    "estimate_label": "What it would take",
    "estimates": [
        ("Papers collected", "about 100–150, the same size as this one"),
        ("AI reading cost", "roughly $8–15 in model usage"),
        ("Time", "3–5 hours, mostly waiting on batch processing"),
        ("Then", "the same search you just tried would work on that subject"),
    ],
    "not_yet": (
        "This panel is a preview, not a working button. Building a library "
        "isn't automated yet, and it spends real money, so it needs a human "
        "to start it. The estimates above are here so you know exactly what "
        "would happen and what it would cost — not so you can trigger it "
        "from this page. If you want a library built for a subject you care "
        "about, get in touch with the maintainer."
    ),
    "predictor_note": (
        "The pre-flight score you see is a hypothesis-driven diagnostic, "
        "not a validated predictor. On the three libraries built so far "
        "its ranking did not match what was found (see the "
        "domain-coherence-predictor working note). Reading it as a "
        "guarantee would be wrong."
    ),
}

# --------------------------------------------------------------------------
# Everything else the interface says.
# --------------------------------------------------------------------------

FOOTER_SCOPE_PREFIX = "Working prototype · currently shown"
FOOTER_SCOPE_SUFFIX = "Not a comprehensive research tool."

# Legacy constant kept for backwards-compat with any caller that reads
# the raw string. The actual footer uses the dynamic client component
# `FooterScope.tsx` that reads the active library and renders
# "{PREFIX}: {n_papers} papers on {library_name}. {SUFFIX}" live.
FOOTER_SCOPE = (
    f"{FOOTER_SCOPE_PREFIX}: 113 papers on {LIBRARY_NAME.lower()}. "
    f"{FOOTER_SCOPE_SUFFIX}"
)

# Short plain-language privacy note. Rendered in the footer on the
# public deploy so a visitor knows what the deployed site collects
# (page views only — Vercel Web Analytics free tier) and what stays
# on their device (the search itself; the .bib and .csv downloads).
PRIVACY_NOTE = {
    "label": "Privacy",
    "body": (
        "On the public deploy this page sends anonymised page-view "
        "counts to Vercel Web Analytics (which URLs got visited, "
        "roughly what country, no cookies, no cross-site tracking, no "
        "identifiers). What you type into the search box runs against "
        "an index in your browser — the query itself is NOT sent to "
        "any server. Downloads (.bib, .csv) are generated locally. The local "
        ".app / .command versions and ?dev=1 opt out of analytics "
        "entirely."
    ),
}

# Multi-library manifest — the one place a user-facing view learns that
# other libraries exist. Kept in sync with
# backend/app/api/multi_library_export.py::LIBRARIES; anything visible
# to the reader lives here so the translation-layer honesty tests can
# police it.
def _site_name() -> str:
    """The site name lives in frontend/site.config.json (one place to rename)."""
    import json as _json
    from pathlib import Path as _Path
    f = _Path(__file__).resolve().parents[3] / "frontend" / "site.config.json"
    return _json.loads(f.read_text())["siteName"]


# Paper counts for the multi-domain libraries come from their corpus files,
# never a literal (a merge changes them).
def _domain_n_papers(slug: str) -> int:
    import json as _json
    from pathlib import Path as _Path
    f = (_Path(__file__).resolve().parents[3] / "data" / "domains" / slug
         / "prelabelled.json")
    return len(_json.loads(f.read_text())["entries"])


LIBRARIES_NOTE = {
    "label": "Libraries in this project",
    "intro": (
        "Each library is one subject read through the same pipeline. "
        "The library currently on screen is the one this URL renders; "
        "to switch, use the picker at the top of the page or append "
        "?lib=<slug> to any URL (?lib= wins over the stored choice)."
    ),
    "items": [
        {
            "slug": "llm-calibration",
            "name": "Language-model reliability",
            "n_papers": 113,
            "note": "The oldest, most-scored library in the project.",
        },
        {
            "slug": "diet-and-mortality",
            "name": "Diet and all-cause mortality",
            "n_papers": _domain_n_papers("diet-and-mortality"),
            "note": (
                "Research-literature analysis, not dietary or medical "
                "advice. Some papers here disagree with each other, "
                "for example on red meat and on alcohol (checked by hand, "
                "not by experts). Take medical "
                "decisions to a clinician who knows you."
            ),
        },
        {
            "slug": "ml-fairness",
            "name": "Algorithmic fairness in machine learning",
            "n_papers": _domain_n_papers("ml-fairness"),
            "note": (
                "Some definitions of fairness are mathematically proven "
                "unable to all hold at once. Our disagreement check found "
                "no conflicting claims among the papers read; why is not "
                "established."
            ),
        },
    ],
}

# Attribution required by the upstream data sources and honest for the
# reader who wants to know where anything here came from.
ATTRIBUTION = {
    "label": "Sources",
    "intro": (
        "Paper metadata, citations and abstracts come from these openly "
        "licensed sources. Only short, structured extractions (claims, "
        "limitations, future-work statements) are shown here — full text "
        "was read to produce those extractions, not republished."
    ),
    "items": [
        ("OpenAlex", "https://openalex.org/", "primary source of paper metadata, citations and abstracts (CC0)"),
        ("Semantic Scholar", "https://www.semanticscholar.org/", "metadata enrichment"),
        ("Unpaywall", "https://unpaywall.org/", "open-access PDFs for extraction"),
        ("Europe PMC", "https://europepmc.org/", "open-access full-text (JATS) for extraction"),
        ("arXiv", "https://arxiv.org/", "preprint full-text for extraction"),
    ],
}

UI = {
    "product_name": _site_name(),
    "tagline": TAGLINE,
    "what_it_does": WHAT_IT_DOES,
    "headline_qualifier": HEADLINE_QUALIFIER,
    "library_name": LIBRARY_NAME,
    "library_covers": LIBRARY_COVERS,
    "library_summary": LIBRARY_SUMMARY,
    "footer_scope": FOOTER_SCOPE,
    "footer_scope_prefix": FOOTER_SCOPE_PREFIX,
    "footer_scope_suffix": FOOTER_SCOPE_SUFFIX,
    "one_library_note": ONE_LIBRARY_NOTE,
    "results_heading": "What we found",
    "evidence_heading": "The evidence",
    "evidence_intro": "Every result here comes from specific papers. These are "
                      "the ones behind this one.",
    "papers_behind": "Papers behind this",
    "what_they_said": "What they said",
    "uncertain_heading": "What's uncertain about this",
    "read_more": "See the full story",
    "back_to_results": "Back to results",
    "browse_all": "Browse everything in the library",
    "all_opportunities": "Everything we found",
    "all_papers": "All papers",
    "strength_explainer": "How sure are we?",
    "no_results_generic": "Nothing to show here.",
    # The findings reports are the raw working notes behind the method. They
    # are technical on purpose, and saying so is more honest than either
    # hiding them or paraphrasing them into something they aren't.
    "findings_heading": "How we checked our own work",
    "findings_intro": "Where the method has limits, we wrote them down rather "
                      "than smoothing them over.",
    "budget_note": "Spending note: our own call-by-call spending ledger records "
                   "more model spend than Google's billing console showed when "
                   "we last checked. We budget against the ledger, the higher "
                   "of the two.",
    "audit_doubts_heading": "Our own verdicts we now doubt",
    "findings_are_technical": "This is a working note written for the people "
                              "building this tool, so it uses technical "
                              "shorthand rather than the plain wording used "
                              "everywhere else.",
}

# Developer-mode copy is deliberately exempt from the jargon ban: its entire
# job is to show the internals the consumer view hides.
DEV_UI = {
    "toggle": "Developer mode",
    "on_note": "Developer mode is on — showing raw scores, scorer internals, "
               "and pipeline provenance.",
    "raw_values": "Raw values",
    "scorer_heading": "Scorer",
    "components_heading": "Component scores",
    "provenance_heading": "Pipeline provenance",
    "search_heading": "Query analysis",
    "json_heading": "Underlying JSON",
    "corpus_heading": "Corpus composition",
    "spend_heading": "Cumulative spend",
    "findings_heading": "Methodological findings",
}


def language_pack() -> dict[str, Any]:
    """The whole vocabulary, exported for the frontend to read. One source."""
    return {
        "ui": UI,
        "dev": DEV_UI,
        "kinds": KINDS,
        "caveats": CAVEATS,
        "confirm_status": CONFIRM_STATUS,
        "strength_meaning": STRENGTH_MEANING,
        "strength_order": STRENGTH_ORDER,
        "abstract_only": ABSTRACT_ONLY,
        "full_text": FULL_TEXT,
        "search": SEARCH,
        "build_library": BUILD_LIBRARY,
        "no_disagreements": NO_DISAGREEMENTS,
        "attribution": ATTRIBUTION,
        "libraries_note": LIBRARIES_NOTE,
        "privacy_note": PRIVACY_NOTE,
    }


# --------------------------------------------------------------------------
# The jargon ban, kept next to the vocabulary it polices so the test and the
# copy can never drift apart.
# --------------------------------------------------------------------------

# Our plumbing. These strings could never occur in a paper's own prose, so
# finding one anywhere a reader can see it — including inside quoted text —
# means something leaked.
PLUMBING_TERMS = [
    "scorer", "component_score", "gap_type", "confirm_status", "input_source",
    "abstract_only", "schema_version", "manifest", "n_independent",
    "trust score", "cosine",
    # `openalex:` (with colon) is the paper-id prefix we never want in consumer
    # copy — matches "openalex:W4399803256" etc. The bare word `OpenAlex` is a
    # legitimate data-source name used in the attribution footer.
    "openalex:",
    "phase 4", "phase 5", "phase 6",
    "confidence tier",
]

# Our names for things, which a reader should never meet — but which are
# ordinary words in this field ("corpus" is a body of text; "epistemic
# uncertainty" is a standard term). Banned in copy we write; allowed when
# they appear inside a sentence quoted verbatim from a paper, because
# rewriting a researcher's own words would be putting words in their mouth.
AUTHORED_BANNED = [
    "orphaned", "orphan", "structural hole", "persistent limitation",
    "unresolved contradiction", "semantic lead", "corpus", "epistemic",
]

BANNED_JARGON = PLUMBING_TERMS + AUTHORED_BANNED


def jargon_hits(text: str, quoted: bool = False) -> list[str]:
    """Banned internal vocabulary found in a consumer-facing string.

    `quoted=True` for text lifted verbatim from a paper: only our plumbing
    is disqualifying there, since the field's own terminology is the
    subject matter and is allowed through by design.
    """
    low = (text or "").lower()
    terms = PLUMBING_TERMS if quoted else BANNED_JARGON
    return [j for j in terms if j in low]
