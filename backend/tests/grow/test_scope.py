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


def _entries(slug, *, with_removed=False):
    pre = json.loads((DOM / slug / "prelabelled.json").read_text())
    out = {e["wid"]: e for e in pre["entries"]}
    if with_removed:
        out.update({r["wid"]: r["entry"] for r in pre.get("removed", [])})
    return out


@pytest.mark.parametrize("slug", list(RUN5))
def test_run5_papers_under_the_core_scope_rule(slug):
    E = _entries(slug, with_removed=True)
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
    # not-ready domains have no core scope: never grown or built unattended
    for slug in ("minimum-wage", "deep-rl-reproducibility", "microplastics-health"):
        assert not core_scope(slug, "Minimum wage and employment", "Raising wages reduced jobs.")[0]


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
    # A mock week no workflow run or e2e scenario uses: its candidates are
    # never already in the library, whatever state the data is in.
    monkeypatch.setenv("GROW_DATE", "2031-03-03")
    from backend.app.corpus import multi_domain
    from backend.app.grow import scope
    from backend.app.grow.mocks import MockOpenAlex
    oa = MockOpenAlex()
    ref = dt.date(2031, 3, 3)
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


REMOVED_2026_10_10 = {"diet-and-mortality": ["W7218462786", "W7220707047"],
                      "social-media-teen-mental-health": ["W7220846371", "W7220964018"],
                      "ml-fairness": ["W7215843351"]}


def test_owner_removed_papers_are_recorded_not_deleted():
    """The 2026-10-10 removals: out of the library's entries, kept on file
    under "removed" with the reason and the decision."""
    for slug, wids in REMOVED_2026_10_10.items():
        pre = json.loads((DOM / slug / "prelabelled.json").read_text())
        live = {e["wid"] for e in pre["entries"]}
        rem = {r["wid"]: r for r in pre.get("removed", [])}
        for w in wids:
            assert w not in live, w
            assert w in rem and rem[w]["reason"] and rem[w]["decided_on"] == "2026-10-10" and rem[w]["entry"], w


@pytest.mark.parametrize("slug", list(REMOVED_2026_10_10))
def test_removed_papers_cannot_reenter_through_selection(slug):
    """Even as a fresh candidate that passes everything else, a removed paper
    is dropped before the rubric."""
    from backend.app.corpus import records as R
    recs = {r["id"].rsplit("/", 1)[-1]: r for r in R.load(slug)["records"] + R.load(slug)["rejected_records"]}
    pre = json.loads((DOM / slug / "prelabelled.json").read_text())
    for w in REMOVED_2026_10_10[slug]:
        rec = recs.get(w) or next(r["entry"] for r in pre["removed"] if r["wid"] == w) | {"id": f"https://openalex.org/{w}"}
        cands = [{"wid": w, "reason": next(iter(core.REASON_RANK)), "detail": "test", "cited_by_count": 999}]
        chosen, drops = core.select(slug, cands, {w: rec}, ref=dt.date(2031, 3, 3))
        assert chosen == [] and drops.get("removed from the library by the owner") == 1, (w, drops)


@pytest.mark.parametrize("slug", list(REMOVED_2026_10_10))
def test_removed_papers_cannot_reenter_through_collection(slug, tmp_path, monkeypatch):
    """A batch collected later that holds a removed paper (paid for, so it is
    collected) never puts it back in the library."""
    import shutil
    d = tmp_path / slug
    d.mkdir()
    shutil.copy(DOM / slug / "prelabelled.json", d / "prelabelled.json")
    monkeypatch.setattr(core, "domains_dir", lambda: tmp_path)
    from backend.app.corpus import records as R
    monkeypatch.setattr(R, "append", lambda s, recs: None)
    pre = json.loads((d / "prelabelled.json").read_text())
    pairs = [(r["entry"], {"id": f"https://openalex.org/{r['wid']}"}) for r in pre["removed"]]
    assert core.add_to_library(slug, pairs) == []
    after = json.loads((d / "prelabelled.json").read_text())
    assert len(after["entries"]) == len(pre["entries"])


@pytest.mark.parametrize("slug", ["nudge-effectiveness", "ego-depletion", "growth-mindset"])
def test_queued_core_scope_agrees_with_the_blind_audit(slug):
    """Each queued domain's core scope agrees with its blind audit (auditor
    'on-domain' = in; borderline and off-domain = out) on at least 80%."""
    d = DOM / slug
    items = {i["wid"]: i for i in json.loads((d / "audit_blind.json").read_text())["items"]}
    lab = json.loads((d / "audit_blind_labels.json").read_text())["labels"]
    agree = sum(core_scope(slug, i["title"], i.get("abstract"))[0] == (lab[w]["label"] == "on-domain")
                for w, i in items.items())
    assert agree >= 0.8 * len(items), (slug, agree, len(items))


@pytest.mark.parametrize("slug", ["nudge-effectiveness", "ego-depletion", "growth-mindset"])
def test_queued_libraries_are_built_only_from_in_scope_papers(slug):
    """The prepared list a queued build extracts holds only in-scope papers;
    the rest are kept on file with their reason."""
    pre = json.loads((DOM / slug / "prelabelled.json").read_text())
    assert pre["entries"] and all(core_scope(slug, e.get("title") or "", e.get("abstract"))[0] for e in pre["entries"])
    assert all(x["reason"] and x["entry"] for x in pre.get("scope_excluded", []))


def test_paid_paper_outside_scope_is_collected_kept_and_not_published(tmp_path, monkeypatch):
    """A paper already paid for that fails the scope at collection (e.g. Diet
    W7221006525) is kept under scope_excluded, reported, never published,
    and never raises."""
    import shutil
    slug = "diet-and-mortality"
    (tmp_path / slug).mkdir()
    shutil.copy(DOM / slug / "prelabelled.json", tmp_path / slug / "prelabelled.json")
    monkeypatch.setattr(core, "domains_dir", lambda: tmp_path)
    from backend.app.corpus import records as R
    monkeypatch.setattr(R, "append", lambda s, recs: None)
    fx = json.loads((Path(__file__).parent / "fixtures" / "scope_exclusion_w7221006525.json").read_text())
    pairs = [(x["entry"], x["record"]) for x in fx["pairs"]]
    out: list[dict] = []
    added = core.add_to_library(slug, pairs, ref=dt.date(2026, 10, 12), excluded=out)
    after = json.loads((tmp_path / slug / "prelabelled.json").read_text())
    assert "W7221006525" not in added and "W7221006525" not in {e["wid"] for e in after["entries"]}
    assert [x["wid"] for x in out] == ["W7221006525"] and out[0]["reason"]
    assert "W7221006525" in {x["wid"] for x in after["scope_excluded"]}
    # collected again (e.g. a rerun): not duplicated
    core.add_to_library(slug, pairs, ref=dt.date(2026, 10, 12), excluded=[])
    again = json.loads((tmp_path / slug / "prelabelled.json").read_text())
    assert [x["wid"] for x in again["scope_excluded"]].count("W7221006525") == 1


def test_removal_record_gives_a_reason_for_every_change():
    """docs/releases/2026-10-10-removals.json: the 5 removals, ₹0, and every
    result that changed has a stated rule (nothing UNEXPLAINED)."""
    rec = json.loads((DOM.parents[1] / "docs" / "releases" / "2026-10-10-removals.json").read_text())
    assert {(r["slug"], r["wid"]) for r in rec["removed"]} == \
        {(s, w) for s, ws in REMOVED_2026_10_10.items() for w in ws}
    assert rec["spend_inr"] == 0.0
    for slug, d in rec["results_changed"].items():
        for r in d["removed_shown"] + d["removed_not_shown"]:
            assert r["reason"] and r["reason"] != "UNEXPLAINED", (slug, r)
    ml = rec["results_changed"]["ml-fairness"]
    assert (ml["shown_before"], ml["shown_after"]) == (60, 58)
    assert sorted(r["id"] for r in ml["removed_shown"]) == ["opp-ml-fairness-orphan-openalex-w3159960173-f1",
                                                            "opp-ml-fairness-orphan-openalex-w3203106571-f2"]
