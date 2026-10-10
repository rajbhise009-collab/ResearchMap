"""Core scope for WEEKLY GROWTH (deterministic; no language model).

The domain rubric (backend/app/corpus/multi_domain.classify) decides whether
a paper is about the domain at all; weekly growth only takes its
"on-domain" papers (borderline is excluded). Unattended growth then also
requires the domain's CORE population and outcome, in the paper's own
words (title or abstract):

  diet-and-mortality               a mortality or survival outcome: in the
                                   title, or in an abstract sentence that
                                   reports a result (association, risk,
                                   cohort, trial...), not a background mention
  social-media-teen-mental-health  adolescents or young people AND a
                                   mental-health outcome
  ml-fairness                      fairness of algorithmic decisions: a
                                   fairness term and an algorithm/model term
                                   in the same sentence (or both in the title)

A library without an entry here is not grown unattended past the rubric.
The check is applied when candidates are selected, never to papers already
submitted or published.
"""
from __future__ import annotations

import re

_SENT = re.compile(r"(?<=[.!?])\s+")


def _rx(*terms: str) -> re.Pattern:
    return re.compile(r"\b(?:" + "|".join(terms) + r")", re.I)


# a sentence that reports a result about the outcome, not a background mention
RESULT = _rx(r"associat", r"risk (?:of|for|ratio)", r"(?:higher|lower|reduced|increased|excess|relative) risk",
             r"hazard", r"\bHR\b", r"\bRR\b", r"\bOR\b", r"odds", r"cohort",
             r"follow[- ]?up", r"predict", r"reduc", r"increas", r"lower", r"higher", r"inverse", r"linked",
             r"effect", r"trial", r"meta-analys", r"prospective", r"incidence",
             # outcome-definition sentences ("Main outcomes: fatal and nonfatal CHD")
             r"attributable", r"estimated", r"modell?ed", r"impacts? on",
             r"outcome", r"endpoint", r"end point", r"documented", r"ascertain", r"events?\b", r"cases\b")
MORTALITY = _rx(r"mortality", r"death(?:s)?\b", r"died\b", r"survival\b", r"life expectancy",
                r"fatal(?:ity|ities)?\b", r"case[- ]fatality", r"lifespan", r"longevity")
YOUNG = _rx(r"adolescen", r"teen", r"youth", r"young (?:people|person|adult)", r"juvenile",
            r"minors\b", r"(?:high|secondary|middle) school", r"school[- ]?(?:age|children|students)",
            r"children\b", r"child\b", r"girls\b", r"boys\b", r"kids\b", r"gen(?:eration)? ?z\b",
            r"undergraduate", r"students\b", r"emerging adult", r"young (?:women|men)",
            r"aged (?:1[0-9]|2[0-4])\b")
MENTAL = _rx(r"mental[- ]health", r"mental illness", r"depress", r"anxi", r"psychological distress",
             r"well[- ]?being", r"loneliness", r"suicid", r"self[- ]harm", r"eating disorder",
             r"body (?:image|dissatisfaction)", r"psychiatric", r"internali[sz]ing", r"life satisfaction",
             r"emotional (?:problems|distress)", r"psychological (?:health|symptoms)")
FAIR = _rx(r"fair(?:ness|ly)?\b", r"unfair", r"bias(?:es|ed)?\b", r"discriminat", r"disparat", r"disparit", r"equalit",
           r"equit", r"inequit", r"demographic parity", r"equali[sz]ed odds", r"protected (?:attribute|group)")
ALGO = _rx(r"algorithm", r"machine[- ]learning", r"\bML\b", r"artificial intelligence", r"\bAI\b",
           r"classifier", r"predictive model", r"(?:automated|algorithmic) decision", r"neural network",
           r"deep learning", r"risk (?:assessment )?(?:tool|score|model)", r"recommender", r"language model",
           r"\bmodels?\b", r"(?:supervised|representation|statistical) learning", r"\blearn(?:ing|ed)\b",
           r"predict", r"classif", r"regression", r"ranking", r"data mining", r"big data",
           r"risk assessment", r"representations?\b", r"automated", r"scoring", r"recidivism")


# --- queued domains (built unattended when the money rule allows) ----------
NUDGE = _rx(r"nudg", r"choice architecture", r"default (?:option|effect|setting|enrol)", r"\bdefaults?\b",
            r"automatic(?:ally)? enrol", r"opt[- ]out", r"opt[- ]in", r"social[- ]norms?", r"social comparison",
            r"reminders?", r"framing", r"salience", r"commitment device", r"active (?:choice|decision)",
            r"positional", r"(?:descriptive|injunctive) norms?", r"normative (?:information|messages?|feedback)",
            r"passive (?:choices?|decisions?|savers?)", r"automatic (?:contribution|escalation)")
BEHAVIOUR = _rx(r"behavio", r"uptake", r"take[- ]up", r"enrol", r"participation", r"saving", r"vaccinat",
                r"consumption", r"energy use", r"choices?\b", r"donat", r"complian", r"adherence", r"purchas",
                r"contribution", r"attendance", r"turnout")
DEPLETION = _rx(r"ego[- ]depletion", r"deplet", r"strength model", r"limited (?:energy|resource)",
                r"self-regulatory fatigue", r"resource model")
SELF_CONTROL = _rx(r"self[- ]control", r"self[- ]regulat", r"willpower", r"persisten", r"performance",
                   r"stroop", r"handgrip", r"subsequent task", r"second task", r"inhibition", r"replicat")
MINDSET = _rx(r"growth[- ]mindset", r"fixed[- ]mindset", r"mindsets?\b", r"implicit theor", r"theories of intelligence",
              r"incremental theor", r"entity theor", r"self-theories", r"beliefs about intelligence", r"malleab")
LEARNING = _rx(r"achievement", r"academic", r"grades?\b", r"\bgpa\b", r"performance", r"learning", r"motivation",
               r"students?", r"children", r"school", r"math", r"test scores", r"persistence", r"attainment")

QUEUED_SCOPES = {
    # slug: (description, construct, outcome)
    "nudge-effectiveness": ("a nudge or choice-architecture intervention and a behaviour it changes",
                            NUDGE, BEHAVIOUR),
    "ego-depletion": ("ego depletion (the limited-resource model) and a self-control outcome",
                      DEPLETION, SELF_CONTROL),
    "growth-mindset": ("growth mindset / implicit theories of intelligence and a learning or achievement outcome",
                       MINDSET, LEARNING),
}


def _pair(text_title: str, text_abstract: str, a: re.Pattern, b: re.Pattern) -> tuple[bool, str]:
    """Both terms in the title, or both in one sentence."""
    x, y = _hit(a, text_title), _hit(b, text_title)
    if x and y:
        return True, f"title: {x!r} + {y!r}"
    for s in _sentences(f"{text_title}. {text_abstract or ''}"):
        x, y = _hit(a, s), _hit(b, s)
        if x and y:
            return True, f"same sentence: {x!r} + {y!r}"
    return False, "no sentence pairs the construct with the outcome"


def _sentences(text: str) -> list[str]:
    return [s for s in _SENT.split(text or "") if s.strip()]


def _hit(rx: re.Pattern, text: str) -> str | None:
    m = rx.search(text or "")
    return m.group(0) if m else None


_HYPHENS = str.maketrans({c: "-" for c in "\u2010\u2011\u2012\u2013\u2014\u2212"})


def core_scope(slug: str, title: str, abstract: str | None) -> tuple[bool, str]:
    """(passes, reason) for a weekly-growth candidate."""
    title = (title or "").translate(_HYPHENS)
    abstract = (abstract or "").translate(_HYPHENS)
    text = f"{title}. {abstract or ''}"
    if slug == "diet-and-mortality":
        h = _hit(MORTALITY, title)
        if h:
            return True, f"mortality/survival outcome in title: {h!r}"
        for sent in _sentences(abstract or ""):
            h, r = _hit(MORTALITY, sent), _hit(RESULT, sent)
            if h and r:
                return True, f"mortality/survival outcome reported: {h!r} with {r!r}"
        return False, ("no mortality or survival outcome: not in the title, and no abstract sentence reports "
                       "one (a background mention does not count)")
    if slug == "social-media-teen-mental-health":
        y, m = _hit(YOUNG, text), _hit(MENTAL, text)
        if y and m:
            return True, f"young population {y!r} + mental-health outcome {m!r}"
        missing = [n for n, v in (("adolescents/young people", y), ("a mental-health outcome", m)) if not v]
        return False, "missing " + " and ".join(missing)
    if slug == "ml-fairness":
        f_t, a_t = _hit(FAIR, title), _hit(ALGO, title)
        if f_t and a_t:
            return True, f"title: fairness {f_t!r} + algorithmic {a_t!r}"
        for s in _sentences(text):
            f, a = _hit(FAIR, s), _hit(ALGO, s)
            if f and a:
                return True, f"same sentence: fairness {f!r} + algorithmic {a!r}"
        return False, "no sentence pairs a fairness term with an algorithm/model term"
    if slug in QUEUED_SCOPES:
        _desc, a, b = QUEUED_SCOPES[slug]
        return _pair(title, abstract or "", a, b)
    return False, f"no core scope defined for {slug!r}; not grown unattended"
