"""One growth run: target split, per-run budget, the widening candidate
search (never loosened), batch vs sync, bounded follow-on checks, and runs
that may start at any time (labels, deadline, crash-safe sync)."""
from __future__ import annotations

import datetime as dt
import importlib.util
import json
import sys
import time
from pathlib import Path

import pytest
import yaml

from backend.app.grow import core, plan

REPO = Path(__file__).resolve().parents[3]
REF = dt.date(2027, 3, 17)


def _rw():
    sys.path.insert(0, str(REPO / "tools" / "grow"))
    spec = importlib.util.spec_from_file_location("run_weekly_plan", REPO / "tools" / "grow" / "run_weekly.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


# ---- config/growth.json ------------------------------------------------------

def test_committed_settings_are_valid_and_the_target_is_55():
    st = plan.load()
    assert st.target_papers_per_run == 55 and st.mode == "batch"
    assert 0 < st.per_run_cost_cap_inr <= 2000
    c = json.loads((REPO / "config" / "growth.json").read_text())
    for k in plan.DEFAULTS:
        assert k in c, k                                    # every setting is visible in the file
    m = json.loads((REPO / "config" / "money.json").read_text())
    assert not {"growth_horizon_weeks", "growth_horizon_start", "weekly_budget_max_inr"} & set(m)


@pytest.mark.parametrize("bad", [{"mode": "fast"}, {"target_papers_per_run": -1}, {"per_run_cost_cap_inr": -2},
                                 {"openalex_max_calls_per_run": 0}, {"target_papers_per_run": 501}])
def test_invalid_settings_are_refused(tmp_path, bad):
    p = tmp_path / "growth.json"
    p.write_text(json.dumps(bad))
    with pytest.raises(ValueError):
        plan.load(p)


def test_target_split_by_fair_rotation():
    assert plan.split_target(55, ["a", "b", "c", "d"]) == {"a": 14, "b": 14, "c": 14, "d": 13}
    assert plan.split_target(3, ["a", "b", "c", "d"]) == {"a": 1, "b": 1, "c": 1, "d": 0}
    assert sum(plan.split_target(55, list("abcdef")).values()) == 55
    assert plan.split_target(10, []) == {}
    st = plan.load()
    assert plan.candidate_need(14, st) == 21 and plan.candidate_need(0, st) == 0


def test_shortfall_says_why_in_plain_words():
    r = plan.shortfall_reasons(target=55, planned=20, budget_inr=25.0, cap_inr=25.0, available_inr=140.0,
                               exhausted={"diet-and-mortality": 9}, over_budget=17)
    assert r[0] == "planned 20 of the target 55 papers"
    assert any("did not fit this run's budget" in x and "per_run_cost_cap_inr" in x for x in r)
    assert any(x.startswith("diet-and-mortality: every search tier tried; 9 fewer") and "not loosened" in x
               for x in r)
    r = plan.shortfall_reasons(target=55, planned=30, budget_inr=10.0, cap_inr=150.0, available_inr=10.0,
                               exhausted={}, over_budget=25)
    assert any("money available" in x and "money rule" in x for x in r)
    assert plan.shortfall_reasons(target=5, planned=5, budget_inr=1, cap_inr=1, available_inr=1,
                                  exhausted={}, over_budget=0) == []


# ---- the widening search -----------------------------------------------------

@pytest.fixture
def mock_oa(monkeypatch, tmp_path):
    monkeypatch.setenv("GROW_DATE", REF.isoformat())
    monkeypatch.setenv("GROW_MOCK_STATE", str(tmp_path / "state"))
    monkeypatch.setattr(core, "pending_path", lambda slug: tmp_path / f"none-{slug}.json")

    def make(deep: bool):
        if deep:
            monkeypatch.setenv("GROW_MOCK_DEEP", "1")
        else:
            monkeypatch.delenv("GROW_MOCK_DEEP", raising=False)
        from backend.app.grow.mocks import MockOpenAlex
        return MockOpenAlex()
    return make


def test_search_stops_at_the_need_after_the_first_tier(mock_oa):
    r = core.search("ml-fairness", core.CallBudget(mock_oa(False), 600), ref=REF, need=2, errors=[])
    f = r["funnel"]
    assert len(r["chosen"]) == 2 and [t["tier"] for t in f["tiers"]] == ["recent"] and not f["exhausted"]


def test_search_widens_until_enough_without_loosening_anything(mock_oa):
    oa = mock_oa(True)
    r = core.search("ml-fairness", core.CallBudget(oa, 600), ref=REF, need=20, errors=[])
    f = r["funnel"]
    assert len(r["chosen"]) == 20 and not f["exhausted"]
    assert [t["tier"] for t in f["tiers"]] == list(core.SEARCH_TIERS)
    assert f["tiers"][-1]["kept"] > 0                                # the vocabulary tier supplied the rest
    # the planted rejects are still rejected (rubric, duplicates)
    assert f["dropped"].get("rubric: off-domain") and f["dropped"].get("duplicate among candidates")
    assert f["dropped"].get("already in library (id/DOI/title)")
    # every kept paper passes the unchanged rubric and core scope
    from backend.app.corpus.multi_domain import _abstract_of, classify
    from backend.app.corpus.multi_domain_reason import DOMAINS
    from backend.app.grow.scope import core_scope
    for e, rec in r["chosen"]:
        assert classify(rec, abstract=_abstract_of(rec), config=DOMAINS["ml-fairness"])[0] == "on-domain"
        assert core_scope("ml-fairness", rec.get("title") or "", _abstract_of(rec))[0]


def test_search_reports_honestly_when_a_library_runs_out(mock_oa):
    r = core.search("diet-and-mortality", core.CallBudget(mock_oa(False), 600), ref=REF, need=30, errors=[])
    f = r["funnel"]
    assert f["exhausted"] and f["short"] == 30 - len(r["chosen"]) > 0 and f["stopped"] is None
    assert [t["tier"] for t in f["tiers"]] == list(core.SEARCH_TIERS)


def test_search_stops_at_the_call_budget_and_says_so(mock_oa):
    r = core.search("ml-fairness", core.CallBudget(mock_oa(True), 3), ref=REF, need=20, errors=[])
    f = r["funnel"]
    assert "call budget" in (f["stopped"] or "") and not f["exhausted"]


def test_search_tiers_use_filter_lists_only():
    """Every candidate query is filter= (1 credit), never search=."""
    seen = []

    class Rec:
        def get(self, path, params):
            seen.append(params)
            return {"results": []}
    for tier in core.SEARCH_TIERS:
        core.tier_candidates(tier, "ml-fairness", Rec(), ref=REF, errors=[])
    assert seen and all("search" not in p and "filter" in p for p in seen)
    years = [p["filter"] for p in seen if "title_and_abstract.search" in p["filter"]]
    assert [f.rsplit("publication_year:", 1)[1] for f in years] == ["2026-2027", "2022-2025", "2017-2021"]
    assert all(f.count("publication_year:") == 1 for f in years)       # the seed filter's own year was removed


# ---- allocation ----------------------------------------------------------------

def _prep(n, inr=1.0):
    return {"items": [{"entry": {"wid": f"W{i}"}, "inr": inr, "inr_sync": inr * 2, "src": "abstract"}
                      for i in range(n)], "dropped": {}}


def test_allocate_stops_at_the_target_and_others_fill_a_short_library():
    prep = {"a": _prep(1), "b": _prep(10), "c": _prep(10)}
    picked = core.allocate(prep, core.Budget(1e9), {}, ["a", "b", "c"], target=9)
    assert [len(picked[s]) for s in "abc"] == [1, 4, 4]
    assert prep["b"]["dropped"]["beyond the run's target"] + prep["c"]["dropped"]["beyond the run's target"] == 12


def test_sync_costs_twice_and_fits_half_as_many():
    prep = {"a": _prep(10)}
    assert len(core.allocate(prep, core.Budget(15.0), {}, ["a"], mode="batch")["a"]) == 10   # 10 x 1.5
    prep = {"a": _prep(10)}
    assert len(core.allocate(prep, core.Budget(15.0), {}, ["a"], mode="sync")["a"]) == 5     # 5 x 2 x 1.5
    assert prep["a"]["dropped"]["over this run's budget"] == 5


def test_sync_price_is_the_interactive_rate():
    from backend.app.corpus.multi_domain_extract import cost
    assert cost(1000, 1000, batch=False) / cost(1000, 1000, batch=True) == pytest.approx(plan.SYNC_COST_FACTOR)


# ---- mode sync: never paid twice, never stranded -----------------------------

class _LLM:
    def __init__(self):
        self.calls = 0

    def set_run_context(self, **_k):
        pass

    def generate(self, prompt, **_k):
        import re
        from backend.app.grow.mocks import _extraction
        self.calls += 1
        return json.dumps(_extraction(re.search(r"(openalex:W\d+)", prompt).group(1), None))


def _sync_items(slug, n):
    from backend.app.grow.mocks import MockOpenAlex
    oa = MockOpenAlex()
    r = core.search(slug, oa, ref=REF, need=n, errors=[])
    out = []
    for e, rec in r["chosen"]:
        e.update(input_source="abstract_only", fulltext_source=None, abstract_only=True)
        prompt, src, inr = core._prompt_for(e)
        out.append({"entry": e, "record": rec, "prompt": prompt, "src": src, "inr": inr, "inr_sync": inr * 2})
    return out


@pytest.fixture
def sandbox(monkeypatch, tmp_path, mock_oa):
    """A scratch library dir + extraction cache + ledger, so sync can run for real (mocked LLM)."""
    import shutil
    slug = "ml-fairness"
    d = tmp_path / "domains"
    shutil.copytree(core.domains_dir() / slug, d / slug, ignore=shutil.ignore_patterns("cache", "extractions"))
    monkeypatch.setattr(core, "domains_dir", lambda: d)
    from backend.app.corpus import records
    monkeypatch.setattr(records, "append", lambda slug, recs: None)
    from backend.app.extraction import cache as C
    monkeypatch.setattr(C, "CACHE_DIR", tmp_path / "cache", raising=False)
    orig = C.ExtractionCache.__init__

    def _init(self, *a, **k):
        orig(self, tmp_path / "cache")
    monkeypatch.setattr(C.ExtractionCache, "__init__", _init)
    import backend.app.extraction.spend_gate as G
    monkeypatch.setattr(G, "preflight", lambda **k: {"allowed": True})
    return slug, d


def test_sync_adds_papers_in_the_run_and_a_rerun_pays_nothing(sandbox, monkeypatch):
    slug, d = sandbox
    items = _sync_items(slug, 3)
    assert len(items) == 3
    llm = _LLM()
    cl = core.Clients(openalex=None, batch=None, embed=None, llm=llm, fulltext=lambda e, r: None)
    pushes = []
    r = core.extract_sync(slug, cl, core.Budget(100.0), items, ref=REF, checkpoint=pushes.append)
    assert llm.calls == 3 and len(r["added"]) == 3 and r["mode"] == "sync"
    assert pushes and pushes[0].startswith("sync extraction of")          # pushed BEFORE the first call
    assert not core.inflight_path(slug).exists()
    pre = json.loads((d / slug / "prelabelled.json").read_text())
    assert {it["entry"]["wid"] for it in items} <= {e["wid"] for e in pre["entries"]}
    # the same papers again (e.g. a rerun): the cache answers, nothing is paid
    r2 = core.extract_sync(slug, cl, core.Budget(100.0), items, ref=REF)
    assert llm.calls == 3 and r2["added"] == []                           # already in the library


def test_a_stopped_sync_run_is_finished_from_the_cache_for_free(sandbox):
    slug, d = sandbox
    items = _sync_items(slug, 2)
    llm = _LLM()
    cl = core.Clients(openalex=None, batch=None, embed=None, llm=llm, fulltext=lambda e, r: None)
    from backend.app.extraction.cache import ExtractionCache
    core._write(core.inflight_path(slug), {"slug": slug, "started_on": REF.isoformat(), "projected_inr": 1.0,
                                           "src": {it["entry"]["wid"]: it["src"] for it in items},
                                           "entries": [it["entry"] for it in items],
                                           "records": [it["record"] for it in items]})
    assert core._sync_one(items[0], cl, slug=slug, cache=ExtractionCache()) == "ok"   # paid before the stop
    fin = core.finish_inflight(slug, ref=REF)
    assert llm.calls == 1                                              # finishing calls no API
    assert fin["added"] == [f"openalex:{items[0]['entry']['wid']}"] and len(fin["failed"]) == 1
    assert not core.inflight_path(slug).exists() and core.finish_inflight(slug, ref=REF) is None


# ---- bounded follow-on checks -----------------------------------------------

def test_fwmatch_cap_marks_only_fully_classified_items(monkeypatch, tmp_path):
    from backend.app.reasoning import run_library_scorers as S

    class C:
        def __init__(self, fw, to):
            self.fw_id, self.to_paper_id = fw, to
    cands = [C("f1", "p1"), C("f1", "p2"), C("f2", "p3"), C("f3", "p4")]

    class RC:
        fw_ids = ["f1", "f2", "f3", "f4"]

        class _loaded:
            @staticmethod
            def future_work():
                return [(type("FW", (), {"id": f, "text": f"text {f}"})(), None) for f in ("f1", "f2", "f3", "f4")]
    monkeypatch.setattr(S, "fw_candidates", lambda slug: (RC, cands))
    ap = tmp_path / "addr.jsonl"
    monkeypatch.setattr(S, "addressals_path", lambda slug: ap)
    monkeypatch.setattr(S.F, "build_prompt", lambda c, t: f"{c.fw_id}->{c.to_paper_id}")
    monkeypatch.setattr(S, "_project", lambda prompts: 0.1 * len(prompts))
    sent = {}

    def run_batch(slug, stage, prompts, **k):
        sent.update(prompts)
        return {k_: "x" for k_ in prompts}, {"projected_inr": 0.1}
    monkeypatch.setattr(S, "_run_batch", run_batch)
    monkeypatch.setattr(S.F, "parse_verdict", lambda t: ("not_addressed", "j", ""))

    class A:
        def __init__(self, c):
            self.c = c

        def model_dump_json(self):
            return json.dumps({"id": f"fwa:{self.c.fw_id}__{self.c.to_paper_id}"})
    monkeypatch.setattr(S.F, "to_addressal", lambda c, *a, **k: A(c))
    monkeypatch.setattr(S.F, "prompt_hash", lambda: "h")
    marked = []
    import backend.app.reasoning.library_corpus as LC
    monkeypatch.setattr(LC, "mark_fw_checked", lambda slug, ids: marked.extend(ids))
    monkeypatch.setattr(S, "_state", lambda slug, stage: tmp_path / "state.json")
    dry = S.fwmatch("x", dry_run=True, max_items=2)
    assert dry["to_classify"] == 2 and dry["carried_over"] == 2
    S.fwmatch("x", dry_run=False, client=object(), max_items=2)
    assert len(sent) == 2                                              # f1's two pairs
    assert sorted(marked) == ["f1", "f4"]                              # f2, f3 still have unclassified pairs
    marked.clear()
    sent.clear()
    S.fwmatch("x", dry_run=False, client=object(), max_items=2)        # the next run carries on
    assert sorted(sent) == ["f2||p3", "f3||p4"] and sorted(marked) == ["f1", "f2", "f3", "f4"]


def test_disagreement_checks_are_capped_per_run():
    src = (REPO / "backend" / "app" / "grow" / "core.py").read_text()
    body = src[src.index("def _followon("):]
    assert "n_fit = min(n_fit, st.max_disagreement_pairs_per_run)" in body
    assert "max_items=st.max_fw_pairs_per_run" in body and "max_items=st.max_confirm_leads_per_run" in body
    assert body.count("wait_timeout_s=followon_wait_s()") == 2


def test_followon_waits_keep_time_for_the_gates(monkeypatch):
    monkeypatch.delenv("GROW_DEADLINE_TS", raising=False)
    assert core.followon_wait_s() == core.FOLLOWON_WAIT_S
    monkeypatch.setenv("GROW_DEADLINE_TS", str(time.time() + core.GATE_RESERVE_S + 600))
    assert 590 <= core.followon_wait_s() <= 600
    monkeypatch.setenv("GROW_DEADLINE_TS", str(time.time() + 60))
    assert core.followon_wait_s() == 0.0                               # pending; collected by the next run


def test_job_timeout_fits_under_githubs_six_hours_and_the_run_plans_for_less():
    d = yaml.safe_load((REPO / ".github" / "workflows" / "weekly-grow.yml").read_text())
    job = d["jobs"]["grow"]
    assert 300 <= job["timeout-minutes"] < 360
    grow = next(s for s in job["steps"] if s.get("name") == "Grow, gate, publish")
    budget_min = int(grow["env"]["GROW_TIME_BUDGET_S"]) / 60
    assert budget_min + 20 <= job["timeout-minutes"]                    # install and the failure report fit too
    assert grow["env"]["GROW_MODE"] == "${{ inputs.mode }}"
    assert grow["env"]["GROW_TARGET_PAPERS"] == "${{ inputs.target_papers }}"


# ---- runs that start any time ---------------------------------------------------

def test_each_run_on_a_day_gets_its_own_label(monkeypatch, tmp_path):
    rw = _rw()
    monkeypatch.setattr(rw, "ROOT", tmp_path)
    (tmp_path / "docs" / "releases").mkdir(parents=True)
    assert rw.run_label("2026-11-16") == "2026-11-16"
    (tmp_path / "docs" / "releases" / "2026-11-16.json").write_text("{}")
    assert rw.run_label("2026-11-16") == "2026-11-16-2"
    monkeypatch.setattr(rw, "_REMOTE_GROW", ["grow/2026-11-16-2"])
    assert rw.run_label("2026-11-16") == "2026-11-16-3"
    rw.record_run("2026-11-16-3")
    assert rw.run_label("2026-11-16") == "2026-11-16-4"
    assert rw.run_label("2026-11-17") == "2026-11-17"
    runs = json.loads((tmp_path / "data" / "grow" / "runs.json").read_text())["runs"]
    assert runs[-1]["label"] == "2026-11-16-3" and runs[-1]["started_at"]


def test_republish_accepts_a_labelled_branch_and_still_refuses_junk(monkeypatch):
    rw = _rw()
    src = (REPO / "tools" / "grow" / "run_weekly.py").read_text()
    import re
    rx = re.search(r're\.fullmatch\(r"(grow/[^"]+)", branch\)', src).group(1)
    for ok in ("grow/2026-11-16", "grow/2026-11-16-2", "grow/2026-11-16-12"):
        assert re.fullmatch(rx, ok)
    for bad in ("grow/2026-11-16-x", "main", "grow/2026-11-16-2;rm", "grow/../main"):
        assert not re.fullmatch(rx, bad)
    assert rw is not None


def test_publish_branch_reports_a_failed_push_instead_of_crashing():
    """It used to reference an undefined name (NameError) on a failed push."""
    src = (REPO / "tools" / "grow" / "run_weekly.py").read_text()
    body = src[src.index("def publish_branch("):src.index('if __name__ == "__main__":')]
    assert "r.returncode" not in body and "pushed, _moved, err = _push(" in body


def test_dry_run_reports_both_modes_runtime_and_the_money_verdict():
    src = (REPO / "tools" / "grow" / "run_weekly.py").read_text()
    body = src[src.index("def dry_run()"):src.index("def registry_queued()")]
    for s in ('for m in ("batch", "sync")', "money allows it?", "estimate_minutes(", "candidates seen",
              "dropped by reason", "_NoPaid()"):
        assert s in body, s
    rw = _rw()
    b = rw.estimate_minutes(mode="batch", papers=55, fulltext=20, calls=250, kept=80)
    s = rw.estimate_minutes(mode="sync", papers=55, fulltext=20, calls=250, kept=80)
    assert rw.FIXED_MIN < b < s < 330                                   # sync adds the extraction time
