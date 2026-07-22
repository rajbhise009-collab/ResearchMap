"""LLMClient interface.

Deliberately narrow. An LLM in ResearchMap does ONE job: read paper text
and return a structured `PaperExtraction`. Nothing about ranking,
judging, scoring, or selecting belongs on this interface.

If you find yourself wanting to add a method here that asks the model
"which is better / more promising / more important" — stop. That logic
belongs in `reasoning/` as deterministic code.
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from pathlib import Path

from backend.app.config import get_settings
from backend.app.models import Paper, PaperExtraction


class LLMClient(ABC):
    """The only interface the pipeline uses to talk to an LLM."""

    name: str = "abstract"

    @abstractmethod
    def extract(self, paper: Paper) -> PaperExtraction:
        """Return a structured decomposition of one paper.

        Implementations must validate the model's output against
        `PaperExtraction` before returning; malformed output should raise,
        never return a placeholder.
        """
        raise NotImplementedError


class MockLLMClient(LLMClient):
    """Reads pre-computed extractions from `data/seed/extractions/`.

    Enables the entire downstream pipeline to run offline against a
    deterministic corpus. If no extraction exists on disk for a paper the
    mock raises rather than fabricating one — silent fakes are worse than
    crashes.
    """

    name = "mock-seed"

    def __init__(self, extractions_dir: Path | None = None) -> None:
        self._dir = extractions_dir or (get_settings().seed_dir / "extractions")

    def extract(self, paper: Paper) -> PaperExtraction:
        path = self._dir / f"{paper.id}.json"
        if not path.exists():
            raise FileNotFoundError(
                f"MockLLMClient has no canned extraction for paper {paper.id!r} "
                f"(looked at {path}). Refusing to fabricate one."
            )
        with path.open("r", encoding="utf-8") as f:
            raw = json.load(f)
        extraction = PaperExtraction.model_validate(raw)
        if extraction.paper_id != paper.id:
            raise ValueError(
                f"Extraction file {path} claims paper_id={extraction.paper_id!r} "
                f"but was requested for {paper.id!r}"
            )
        return extraction


class GeminiLLMClient(LLMClient):
    """Placeholder for the real Gemini Flash extractor.

    Wired up in Phase 2. Kept as an explicit `NotImplementedError` here so
    it's visible in the interface layout without pretending to work.
    """

    name = "gemini-flash"

    def extract(self, paper: Paper) -> PaperExtraction:
        raise NotImplementedError(
            "GeminiLLMClient is not implemented until Phase 2. "
            "Use MockLLMClient for offline extraction."
        )


__all__ = ["GeminiLLMClient", "LLMClient", "MockLLMClient"]
