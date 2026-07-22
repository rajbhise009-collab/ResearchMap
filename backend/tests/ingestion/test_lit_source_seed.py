"""SeedLitSource + MockLLMClient — the offline-runnable backbone."""

from __future__ import annotations

import pytest

from backend.app.extraction.llm_client import MockLLMClient
from backend.app.ingestion.lit_source import SeedLitSource


def test_seed_source_loads_all_papers(seed_dir):
    src = SeedLitSource(seed_dir=seed_dir)
    papers = src.all_papers()
    assert 30 <= len(papers) <= 50, f"expected 30-50 seed papers, got {len(papers)}"
    ids = {p.id for p in papers}
    assert len(ids) == len(papers), "seed paper IDs must be unique"
    # Every seed paper carries the seed: prefix and no DOI (fixture rule).
    for p in papers:
        assert p.id.startswith("seed:")
        assert p.doi is None


def test_seed_source_search_matches_by_query(seed_dir):
    src = SeedLitSource(seed_dir=seed_dir)
    hits = list(src.search("PatchTST", limit=100))
    assert hits, "expected some PatchTST papers in the seed corpus"
    assert all("patchtst" in (h.title.lower() + (h.abstract or "").lower()) for h in hits)


def test_seed_source_get_by_id_roundtrips(seed_dir):
    src = SeedLitSource(seed_dir=seed_dir)
    p = src.get_by_id("seed:0001")
    assert p is not None
    assert p.id == "seed:0001"
    assert src.get_by_id("seed:9999") is None


def test_mock_llm_returns_valid_extraction_for_every_seed_paper(seed_dir):
    """Route the seed papers through the mock via the current
    `.generate(prompt)` interface — the prompt just needs to contain
    the `Paper ID: `<id>`` marker the mock regex-extracts."""
    import json
    from backend.app.models import PaperExtraction
    src = SeedLitSource(seed_dir=seed_dir)
    llm = MockLLMClient()
    for paper in src.all_papers():
        prompt = f"header\nPaper ID: `{paper.id}`\nabstract goes here"
        raw = llm.generate(prompt)
        ext = PaperExtraction.model_validate(json.loads(raw))
        assert ext.paper_id == paper.id
        # Extractions must contain at least one claim and one limitation.
        assert ext.claims, f"no claims for {paper.id}"
        assert ext.limitations, f"no limitations for {paper.id}"
        # Every evidence item must point at a real claim in the same bundle.
        claim_ids = {c.id for c in ext.claims}
        for ev in ext.evidence:
            assert ev.claim_id in claim_ids


def test_mock_llm_refuses_to_fabricate_unknown_paper(seed_dir):
    llm = MockLLMClient()
    with pytest.raises(FileNotFoundError):
        llm.generate("Paper ID: `seed:9999`")
