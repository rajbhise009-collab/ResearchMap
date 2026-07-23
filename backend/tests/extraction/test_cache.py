"""ExtractionCache tests."""

from __future__ import annotations

from pathlib import Path

from backend.app.extraction.cache import ExtractionCache
from backend.app.models import (
    Claim,
    ClaimType,
    Limitation,
    LimitationScope,
    PaperExtraction,
)


def _sample_extraction(paper_id: str = "openalex:W1") -> PaperExtraction:
    return PaperExtraction(
        paper_id=paper_id,
        claims=[Claim(id=f"{paper_id}:c1", paper_id=paper_id,
                       text="Sample.", type=ClaimType.FINDING,
                       confidence=0.9)],
        limitations=[Limitation(id=f"{paper_id}:l1", paper_id=paper_id,
                                 text="Small sample.",
                                 normalized_category="statistical-power",
                                 source_scope=LimitationScope.THIS_WORK)],
        extractor="test",
    )


MODEL = "gemini:test-model"


def test_cache_miss_returns_none(tmp_path: Path):
    cache = ExtractionCache(root=tmp_path)
    assert cache.get("openalex:W1", MODEL, "abcdef012345") is None


def test_cache_put_then_get_roundtrips(tmp_path: Path):
    cache = ExtractionCache(root=tmp_path)
    original = _sample_extraction()
    cache.put(original.paper_id, MODEL, "abcdef012345", original)
    fetched = cache.get(original.paper_id, MODEL, "abcdef012345")
    assert fetched is not None
    assert fetched.paper_id == original.paper_id
    assert len(fetched.claims) == 1
    assert fetched.claims[0].text == "Sample."


def test_cache_isolates_by_prompt_hash(tmp_path: Path):
    """Different prompt hashes for the same paper get separate slots."""
    cache = ExtractionCache(root=tmp_path)
    v1 = _sample_extraction("openalex:W1")
    v2 = _sample_extraction("openalex:W1")
    # Force a distinguishing field.
    v1_dict = v1.model_dump()
    v1_dict["extractor"] = "v1"
    v1 = PaperExtraction.model_validate(v1_dict)
    v2_dict = v2.model_dump()
    v2_dict["extractor"] = "v2"
    v2 = PaperExtraction.model_validate(v2_dict)

    cache.put("openalex:W1", MODEL, "aaaaaaaaaaaa", v1)
    cache.put("openalex:W1", MODEL, "bbbbbbbbbbbb", v2)

    assert cache.get("openalex:W1", MODEL, "aaaaaaaaaaaa").extractor == "v1"
    assert cache.get("openalex:W1", MODEL, "bbbbbbbbbbbb").extractor == "v2"


def test_cache_isolates_by_model(tmp_path: Path):
    """Same paper + same prompt hash but DIFFERENT model must not
    collide — this is the correctness bug the model-in-key fixes."""
    cache = ExtractionCache(root=tmp_path)
    a = _sample_extraction("openalex:W1")
    a = PaperExtraction.model_validate({**a.model_dump(), "extractor": "model-A"})
    b = _sample_extraction("openalex:W1")
    b = PaperExtraction.model_validate({**b.model_dump(), "extractor": "model-B"})

    cache.put("openalex:W1", "gemini:model-A", "samehash1234", a)
    cache.put("openalex:W1", "gemini:model-B", "samehash1234", b)

    assert cache.get("openalex:W1", "gemini:model-A", "samehash1234").extractor == "model-A"
    assert cache.get("openalex:W1", "gemini:model-B", "samehash1234").extractor == "model-B"
    # A third model that never wrote gets a clean miss.
    assert cache.get("openalex:W1", "gemini:model-C", "samehash1234") is None


def test_corrupt_cache_entry_is_a_miss(tmp_path: Path):
    """A malformed on-disk file should be treated as a MISS, not a
    fatal error. Next put() replaces it."""
    cache = ExtractionCache(root=tmp_path)
    path = cache._key_path("openalex:W1", MODEL, "abcdef012345")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("this is not json", encoding="utf-8")
    assert cache.get("openalex:W1", MODEL, "abcdef012345") is None
