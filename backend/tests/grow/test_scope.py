"""Weekly growth's core-scope rule (backend/app/grow/scope.py): the domain's
core population and outcome, deterministic, on top of the rubric (whose
borderline papers are already excluded)."""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import pytest

from backend.app.grow import core
from backend.app.grow.scope import core_scope

DOM = Path(__file__).resolve().parents[3] / "data" / "domains"

# The 9 papers weekly-grow run #5 added (2026-10-09): verdicts under the rule.
RUN5 = {
    "diet-and-mortality": {"W7218462786": False, "W7220707047": False, "W7220864522": True},
    "ml-fairness": {"W7214947317": True, "W7215843351": True, "W7219603619": True},
    "social-media-teen-mental-health": {"W7220393051": True, "W7220846371": False, "W7220964018": False},
}


def _entries(slug):
    return {e["wid"]: e for e in json.loads((DOM / slug / "prelabelled.json").read_text())["entries"]}


@pytest.mark.parametrize("slug", list(RUN5))
def test_run5_papers_under_the_core_scope_rule(slug):
    E = _entries(slug)
    for wid, want in RUN5[slug].items():
        ok, why = core_scope(slug, E[wid]["title"], E[wid].get("abstract"))
        assert ok is want, (wid, why)


def test_background_mention_of_mortality_does_not_count():
    ab = ("Noncommunicable diseases account for a major share of global mortality, while key behavioral "
          "risks are shaped by environments. We argue for structural policy.")
    assert not core_scope("diet-and-mortality", "Beyond lifestyle advice", ab)[0]
    assert core_scope("diet-and-mortality", "Fibre intake",
                      "Higher fibre intake was associated with lower all-cause mortality (HR 0.8).")[0]
    assert core_scope("diet-and-mortality", "Healthy eating and CVD",
                      "Main Outcomes and Measures: fatal and nonfatal coronary heart disease.")[0]


def test_population_and_outcome_both_required_for_social_media():
    s = "social-media-teen-mental-health"
    assert core_scope(s, "Instagram use and depression among adolescents", "")[0]
    assert not core_scope(s, "Instagram use and depression", "A survey of adults aged 30-65.")[0]
    assert not core_scope(s, "Instagram use among adolescents", "We measured screen time.")[0]


def test_fairness_must_be_about_algorithmic_decisions():
    s = "ml-fairness"
    assert core_scope(s, "Equality of Opportunity in Supervised Learning", "")[0]
    assert not core_scope(s, "Fair pay for nurses", "Wages were compared across hospitals.")[0]
    assert not core_scope(s, "Deep learning for chest X-ray", "A model segments the lungs.")[0]


def test_unknown_library_is_not_grown_unattended():
    assert not core_scope("nudge-effectiveness", "Nudges and savings", "Default enrolment raised savings.")[0]


@pytest.mark.parametrize("slug,max_fail", [("ml-fairness", 0.10)])
def test_rule_keeps_the_fields_founding_papers(slug, max_fail):
    """Calibration: the rule must not reject the field's own founding papers
    (ML fairness: at most 10% of the original on-domain papers)."""
    on = [e for e in _entries(slug).values() if e.get("label") == "on-domain" and e.get("added_by") != "weekly-grow"]
    fails = [e["wid"] for e in on if not core_scope(slug, e["title"], e.get("abstract"))[0]]
    assert len(fails) <= max_fail * len(on), fails


def test_every_founding_diet_paper_that_reports_mortality_passes():
    from backend.app.grow.scope import MORTALITY
    for e in _entries("diet-and-mortality").values():
        if e.get("label") != "on-domain" or e.get("added_by") == "weekly-grow":
            continue
        text = f"{e['title']} {e.get('abstract') or ''}"
        if MORTALITY.search(text):
            assert core_scope("diet-and-mortality", e["title"], e.get("abstract"))[0], e["wid"]


def test_selection_drops_borderline_and_out_of_scope(monkeypatch):
    """Wiring: select() keeps only rubric 'on-domain' papers that also pass
    the core scope; both kinds of drop are counted."""
    monkeypatch.setenv("GROW_DATE", "2026-10-12")
    from backend.app.corpus import multi_domain
    from backend.app.grow import scope
    from backend.app.grow.mocks import MockOpenAlex
    oa = MockOpenAlex()
    ref = dt.date(2026, 10, 12)
    cands = core.find_candidates("social-media-teen-mental-health", oa, ref=ref, errors=[])
    recs = core.fetch_records(oa, [c["wid"] for c in cands])
    real_classify, real_scope = multi_domain.classify, scope.core_scope
    first, second = sorted(recs)[0], sorted(recs)[1]
    monkeypatch.setattr(multi_domain, "classify", lambda rec, **k: ("borderline", "test") if
                        rec["id"].endswith(first) else real_classify(rec, **k))
    monkeypatch.setattr(scope, "core_scope", lambda slug, t, a: (False, "test") if t == recs[second]["title"]
                        else real_scope(slug, t, a))
    chosen, drops = core.select("social-media-teen-mental-health", cands, recs, ref=ref)
    wids = {e["wid"] for e, _ in chosen}
    assert first not in wids and second not in wids
    assert drops.get("rubric: borderline", 0) >= 1 and drops.get("outside the core scope", 0) >= 1
    assert chosen and all("core scope:" in e["rationale"] for e, _ in chosen)
