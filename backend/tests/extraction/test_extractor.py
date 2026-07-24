"""Extractor orchestrator tests — the full mock path.

Covers the four "interesting cases" the brief calls for:
  - contradictory claims
  - unaddressed future work
  - stated limitation
  - malformed / partial output (retry-on-repair + hard-fail)
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from backend.app.extraction.cache import ExtractionCache
from backend.app.extraction.errors import (
    ExtractionParseError,
    ExtractionValidationError,
)
from backend.app.extraction.extractor import Extractor
from backend.app.extraction.llm_client import (
    DailyQuotaError,
    LLMClient,
    MockLLMClient,
    ProgrammableMockLLMClient,
)
from backend.app.models import Paper, PaperExtraction, Source


# --- Helpers -----------------------------------------------------------


def _paper(pid: str, title: str = "T") -> Paper:
    return Paper(
        id=pid, source=Source.SEED, source_id=pid.split(":")[-1],
        title=title, year=2024,
        abstract="An abstract on the topic.",
    )


def _valid_json_for(paper_id: str, **over) -> str:
    body = {
        "paper_id": paper_id,
        "claims": [
            {
                "id": f"{paper_id}:c1", "paper_id": paper_id,
                "text": "Our method reduces MSE by 12%.",
                "type": "finding", "confidence": 0.9,
            }
        ],
        "evidence": [
            {
                "id": f"{paper_id}:e1", "claim_id": f"{paper_id}:c1",
                "description": "See Table 3.", "strength": 0.8,
            }
        ],
        "methodologies": [],
        "limitations": [
            {
                "id": f"{paper_id}:l1", "paper_id": paper_id,
                "text": "Small sample.",
                "normalized_category": "statistical-power",
                "source_scope": "this_work",
            }
        ],
        "future_work": [
            {
                "id": f"{paper_id}:f1", "paper_id": paper_id,
                "text": "Extend to multivariate settings.",
                "addressed_by": None,
            }
        ],
        "extractor": "programmable-mock",
    }
    body.update(over)
    return json.dumps(body)


# --- Cache hit / miss --------------------------------------------------


def test_cache_miss_calls_llm_and_caches(tmp_path: Path):
    paper = _paper("openalex:W1")
    llm = ProgrammableMockLLMClient([_valid_json_for(paper.id)])
    cache = ExtractionCache(root=tmp_path)
    extractor = Extractor(llm=llm, cache=cache)

    result = extractor.extract(paper)
    assert not result.from_cache
    assert result.attempts == 1

    # Now the cache should serve the second request without hitting the LLM.
    result2 = extractor.extract(paper)
    assert result2.from_cache
    assert result2.attempts == 0
    assert llm.call_count == 1


# --- Retry-on-repair ----------------------------------------------------


def test_retry_on_malformed_then_succeeds(tmp_path: Path):
    paper = _paper("openalex:W1")
    llm = ProgrammableMockLLMClient([
        "not valid json at all",
        _valid_json_for(paper.id),
    ])
    extractor = Extractor(
        llm=llm, cache=ExtractionCache(root=tmp_path), max_retries=2,
    )
    result = extractor.extract(paper)
    assert result.attempts == 2
    assert not result.from_cache


def test_hard_fails_after_max_retries(tmp_path: Path):
    paper = _paper("openalex:W1")
    # All-garbage: the client (here the mock) exhausts its retry budget
    # (its scripted list) and hard-fails with a parse error.
    llm = ProgrammableMockLLMClient(["garbage"] * 4)
    extractor = Extractor(llm=llm, cache=ExtractionCache(root=tmp_path))
    with pytest.raises(ExtractionParseError):
        extractor.extract(paper)
    # The mock advanced through all scripted responses trying to repair.
    assert llm.call_count == 4


def test_hard_fails_on_schema_violation(tmp_path: Path):
    """Non-JSON is a parse error; JSON that violates the schema is a
    validation error. Both raise; neither returns a silent partial."""
    paper = _paper("openalex:W1")
    bad = json.dumps({"paper_id": paper.id, "claims": [{"missing_fields": True}]})
    llm = ProgrammableMockLLMClient([bad] * 4)
    extractor = Extractor(
        llm=llm, cache=ExtractionCache(root=tmp_path), max_retries=2,
    )
    with pytest.raises(ExtractionValidationError):
        extractor.extract(paper)


def test_never_returns_silent_partial(tmp_path: Path):
    """The extractor either returns a fully validated PaperExtraction
    or raises. A malformed sub-object must not slip through even if
    the top-level shape parses."""
    paper = _paper("openalex:W1")
    # JSON parses; claims list has a partial entry missing required fields.
    partial = json.dumps({
        "paper_id": paper.id,
        "claims": [{"id": f"{paper.id}:c1"}],  # missing paper_id, text, type, confidence
    })
    llm = ProgrammableMockLLMClient([partial])
    extractor = Extractor(
        llm=llm, cache=ExtractionCache(root=tmp_path), max_retries=0,
    )
    with pytest.raises(ExtractionValidationError):
        extractor.extract(paper)


def test_paper_id_mismatch_is_a_hard_error(tmp_path: Path):
    """If the model returns a different paper_id than requested, we
    refuse — this can only happen if the mock is misconfigured or a
    real model got a scrambled prompt."""
    paper = _paper("openalex:W1")
    wrong = _valid_json_for("openalex:WRONG")
    llm = ProgrammableMockLLMClient([wrong])
    extractor = Extractor(
        llm=llm, cache=ExtractionCache(root=tmp_path), max_retries=0,
    )
    with pytest.raises(ExtractionValidationError):
        extractor.extract(paper)


# --- Provenance --------------------------------------------------------


def test_prompt_hash_matches_current_prompt(tmp_path: Path):
    """The Extractor exposes the currently-loaded prompt's hash so
    callers can log it alongside cached results."""
    paper = _paper("openalex:W1")
    llm = ProgrammableMockLLMClient([_valid_json_for(paper.id)])
    extractor = Extractor(
        llm=llm, cache=ExtractionCache(root=tmp_path),
    )
    from backend.app.extraction.prompt_versions import load, latest_version
    assert extractor.prompt_hash == load(latest_version()).hash
    assert extractor.prompt_version == latest_version()


def test_cache_key_uses_prompt_hash_not_version(tmp_path: Path):
    """Two prompt versions with different bodies must never share a
    cache slot even if their versions are cosmetically similar."""
    paper = _paper("openalex:W1")
    llm = ProgrammableMockLLMClient([_valid_json_for(paper.id)] * 2)
    cache = ExtractionCache(root=tmp_path)
    extractor = Extractor(llm=llm, cache=cache)

    # Extract once to populate the cache under prompt_hash.
    r1 = extractor.extract(paper)
    assert not r1.from_cache

    # Manually simulate a different prompt hash by peeking at the
    # cache slot — a lookup under a different hash misses.
    src = extractor.input_source
    assert cache.get(paper.id, extractor.model, src, "0000deadbeef") is None
    # A different MODEL also misses even at the right prompt hash.
    assert cache.get(paper.id, "gemini:other-model", src, extractor.prompt_hash) is None
    # A different INPUT SOURCE also misses.
    assert cache.get(paper.id, extractor.model, "fulltext", extractor.prompt_hash) is None
    # The correct (model, input_source, prompt_hash) slot still hits.
    assert cache.get(paper.id, extractor.model, src, extractor.prompt_hash) is not None


# --- Compound splitting --------------------------------------------------


def test_extractor_enforces_compound_splitting(tmp_path: Path):
    """If the model emits a compound sentence in a single Claim, the
    orchestrator splits it into atoms at parse time."""
    paper = _paper("openalex:W1")
    compound_body = {
        "paper_id": paper.id,
        "claims": [
            {
                "id": f"{paper.id}:c1", "paper_id": paper.id,
                "text": (
                    "Our contributions are 1) a novel calibration objective, "
                    "2) a benchmark with 200 items, "
                    "3) a state-of-the-art result on ETTh1."
                ),
                "type": "finding", "confidence": 0.9,
            }
        ],
        "evidence": [], "methodologies": [], "limitations": [],
        "future_work": [], "extractor": "programmable-mock",
    }
    llm = ProgrammableMockLLMClient([json.dumps(compound_body)])
    extractor = Extractor(
        llm=llm, cache=ExtractionCache(root=tmp_path),
    )
    result = extractor.extract(paper)
    assert len(result.extraction.claims) == 3
    for c in result.extraction.claims:
        assert c.source_sentence_id == f"{paper.id}:c1"


# --- End-to-end mock corpus run ---------------------------------------


def test_e2e_mock_extraction_over_seed_corpus():
    """Full pipeline against the committed seed corpus with the
    MockLLMClient — the canonical offline smoke test. Exit 0 = pass."""
    from backend.app.ingestion.lit_source import SeedLitSource
    from backend.app.extraction.cache import ExtractionCache

    src = SeedLitSource()
    llm = MockLLMClient()  # reads from data/seed/extractions/
    # Use an isolated in-memory cache so we don't touch data/cache/.
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        cache = ExtractionCache(root=Path(tmp))
        extractor = Extractor(llm=llm, cache=cache)
        # Extract the first 3 seed papers.
        for paper in src.all_papers()[:3]:
            result = extractor.extract(paper)
            assert result.extraction.paper_id == paper.id
            assert not result.from_cache
            # Every claim's paper_id matches the parent.
            for c in result.extraction.claims:
                assert c.paper_id == paper.id


# --- Interesting cases the brief calls for ----------------------------


def test_contradictory_claims_case():
    """A mock paper with two claims that logically contradict.
    The extractor's job is to represent them faithfully; it does NOT
    resolve or flag them — that's Phase 4's job."""
    from tempfile import TemporaryDirectory
    paper = _paper("mock:contradiction",
                    title="Contradictory-claim fixture")
    body = json.dumps({
        "paper_id": paper.id,
        "claims": [
            {
                "id": f"{paper.id}:c1", "paper_id": paper.id,
                "text": "Larger models are always better calibrated.",
                "type": "finding", "confidence": 0.9,
            },
            {
                "id": f"{paper.id}:c2", "paper_id": paper.id,
                "text": "Larger models tend to be systematically overconfident.",
                "type": "negative", "confidence": 0.9,
            },
        ],
        "evidence": [], "methodologies": [], "limitations": [],
        "future_work": [], "extractor": "programmable-mock",
    })
    llm = ProgrammableMockLLMClient([body])
    with TemporaryDirectory() as tmp:
        extractor = Extractor(llm=llm, cache=ExtractionCache(root=Path(tmp)))
        result = extractor.extract(paper)
        assert len(result.extraction.claims) == 2
        # Contradictory content is preserved verbatim.
        texts = {c.text for c in result.extraction.claims}
        assert any("always better calibrated" in t for t in texts)
        assert any("systematically overconfident" in t for t in texts)


def test_unaddressed_future_work_case():
    """A paper with future_work items that carry addressed_by=None —
    these are the raw material the Phase-4 unfollowed-future-work
    scorer will look for."""
    from tempfile import TemporaryDirectory
    paper = _paper("mock:futurework", title="Future-work fixture")
    body = json.dumps({
        "paper_id": paper.id,
        "claims": [{
            "id": f"{paper.id}:c1", "paper_id": paper.id,
            "text": "We propose Method X.",
            "type": "method", "confidence": 0.9,
        }],
        "evidence": [], "methodologies": [], "limitations": [],
        "future_work": [
            {
                "id": f"{paper.id}:f1", "paper_id": paper.id,
                "text": "Study distribution shift explicitly.",
                "addressed_by": None,
            },
            {
                "id": f"{paper.id}:f2", "paper_id": paper.id,
                "text": "Report per-seed variance.",
                "addressed_by": None,
            },
        ],
        "extractor": "programmable-mock",
    })
    llm = ProgrammableMockLLMClient([body])
    with TemporaryDirectory() as tmp:
        extractor = Extractor(llm=llm, cache=ExtractionCache(root=Path(tmp)))
        result = extractor.extract(paper)
        fw = result.extraction.future_work
        assert len(fw) == 2
        assert all(item.addressed_by is None for item in fw)


def test_stated_limitation_case_with_scope():
    """A paper stating one this_work and one prior_work limitation.
    The scope distinction is what the persistent-limitations scorer
    consumes."""
    from tempfile import TemporaryDirectory
    paper = _paper("mock:limitation", title="Limitation fixture")
    body = json.dumps({
        "paper_id": paper.id,
        "claims": [{
            "id": f"{paper.id}:c1", "paper_id": paper.id,
            "text": "We propose an improved method.",
            "type": "method", "confidence": 0.8,
        }],
        "evidence": [], "methodologies": [],
        "limitations": [
            {
                "id": f"{paper.id}:l1", "paper_id": paper.id,
                "text": "Existing methods X are miscalibrated.",
                "normalized_category": "calibration",
                "source_scope": "prior_work",
            },
            {
                "id": f"{paper.id}:l2", "paper_id": paper.id,
                "text": "Our evaluation uses a single held-out split.",
                "normalized_category": "statistical-power",
                "source_scope": "this_work",
            },
        ],
        "future_work": [], "extractor": "programmable-mock",
    })
    llm = ProgrammableMockLLMClient([body])
    with TemporaryDirectory() as tmp:
        extractor = Extractor(llm=llm, cache=ExtractionCache(root=Path(tmp)))
        result = extractor.extract(paper)
        lims = result.extraction.limitations
        assert len(lims) == 2
        scopes = {lim.source_scope for lim in lims}
        assert scopes == {"prior_work", "this_work"}


# --- Resumability -------------------------------------------------------


class _ScriptedClient(LLMClient):
    """Succeeds for every paper except those in `fail_daily`, for which it
    raises DailyQuotaError (simulating a mid-run daily-quota abort).
    Tracks total_requests so we can prove cache hits do no API work."""

    name = "gemini:resumetest"

    def __init__(self, fail_daily: set[str]) -> None:
        self._fail = fail_daily
        self.total_requests = 0

    def generate(self, prompt: str, *, validate=None) -> str:
        pid = re.search(r"Paper ID: `([^`]+)`", prompt).group(1)
        self.total_requests += 1
        if pid in self._fail:
            raise DailyQuotaError("daily quota exhausted (test)")
        text = _valid_json_for(pid)
        if validate is not None:
            validate(text)
        return text


def test_resumption_from_killed_run_does_no_duplicate_work(tmp_path: Path):
    papers = [_paper(f"openalex:W{i}") for i in (1, 2, 3, 4)]
    cache = ExtractionCache(root=tmp_path)

    # Run 1: dies (daily quota) at the 3rd paper.
    llm1 = _ScriptedClient(fail_daily={"openalex:W3", "openalex:W4"})
    ex1 = Extractor(llm=llm1, cache=cache)
    done = []
    for p in papers:
        try:
            ex1.extract(p)
            done.append(p.id)
        except DailyQuotaError:
            break
    assert done == ["openalex:W1", "openalex:W2"]
    # The first two are durably cached before the abort.
    for pid in ("openalex:W1", "openalex:W2"):
        assert cache.get(pid, llm1.name, "abstract", ex1.prompt_hash) is not None

    # Run 2 (quota reset): same cache, working client. W1/W2 are cache
    # hits with ZERO new API calls; only W3/W4 actually hit the client.
    llm2 = _ScriptedClient(fail_daily=set())
    ex2 = Extractor(llm=llm2, cache=cache)
    results = [ex2.extract(p) for p in papers]
    assert results[0].from_cache and results[1].from_cache
    assert not results[2].from_cache and not results[3].from_cache
    assert llm2.total_requests == 2  # exactly W3 and W4 — no rework on W1/W2
