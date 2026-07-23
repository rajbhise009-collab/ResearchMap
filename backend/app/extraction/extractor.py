"""Extraction orchestrator.

Given a Paper and an LLMClient, produce a validated `PaperExtraction`
by rendering a version-pinned prompt, calling the model, parsing the
JSON output, validating against the schema, enforcing the compound-
splitting contract, and attaching provenance (prompt hash) to every
record.

On repeated validation failure the orchestrator raises
`ExtractionValidationError`. **Never** returns a silent partial. The
downstream reasoning engine's evidence chain assumes atomicity and
completeness — a silent partial breaks it in ways that show up as
incorrect scoring, not a runtime error.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from pydantic import ValidationError

from backend.app.extraction.cache import ExtractionCache
from backend.app.extraction.errors import (
    ExtractionParseError,
    ExtractionValidationError,
)
from backend.app.extraction.llm_client import LLMClient
from backend.app.extraction.parse import enforce_compound_splitting
from backend.app.extraction.prompt_versions import (
    PromptVersion,
    latest_version,
    load,
)
from backend.app.models import Paper, PaperExtraction


DEFAULT_MAX_RETRIES = 2


@dataclass
class ExtractionResult:
    """The extractor's return value. `extraction` is the validated,
    compound-split, provenance-attached PaperExtraction. `from_cache`
    is True when the cache satisfied the request without an LLM call."""

    extraction: PaperExtraction
    from_cache: bool
    attempts: int  # number of LLM calls made (0 on cache hit)


class Extractor:
    """Stateless orchestrator. One instance can extract many papers."""

    def __init__(
        self,
        llm: LLMClient,
        prompt_version: str | None = None,
        cache: ExtractionCache | None = None,
        max_retries: int = DEFAULT_MAX_RETRIES,
        input_source: str = "abstract",
    ) -> None:
        self._llm = llm
        self._prompt: PromptVersion = load(prompt_version or latest_version())
        self._cache = cache if cache is not None else ExtractionCache()
        self._max_retries = max_retries
        if input_source not in ("abstract", "fulltext"):
            raise ValueError(
                f"input_source must be 'abstract' or 'fulltext', "
                f"got {input_source!r}"
            )
        self._input_source = input_source

    @property
    def prompt_hash(self) -> str:
        return self._prompt.hash

    @property
    def prompt_version(self) -> str:
        return self._prompt.version

    @property
    def input_source(self) -> str:
        return self._input_source

    # --- Public API -------------------------------------------------

    @property
    def model(self) -> str:
        """The model identity used in the cache key and provenance —
        the LLM client's `name` (e.g. 'gemini:gemini-3.6-flash',
        'mock-seed')."""
        return self._llm.name

    def extract(self, paper: Paper) -> ExtractionResult:
        """Extract one paper. Cache hit skips the LLM; cache miss calls
        the LLM up to `max_retries + 1` times before giving up."""
        cached = self._cache.get(
            paper.id, self.model, self._input_source, self._prompt.hash,
        )
        if cached is not None:
            return ExtractionResult(extraction=cached, from_cache=True, attempts=0)

        rendered = self._render(paper)
        attempts = 0
        last_error: Exception | None = None
        while attempts <= self._max_retries:
            attempts += 1
            raw = self._llm.generate(rendered)
            try:
                extraction = self._parse_validate_augment(paper, raw)
                self._cache.put(
                    paper.id, self.model, self._input_source,
                    self._prompt.hash, extraction,
                )
                return ExtractionResult(
                    extraction=extraction, from_cache=False, attempts=attempts,
                )
            except (ExtractionParseError, ExtractionValidationError) as e:
                # Retry — some models are stochastic and self-correct.
                last_error = e.last_error
                continue

        # Distinguish parse vs. validation for observability.
        if isinstance(last_error, json.JSONDecodeError):
            raise ExtractionParseError(paper.id, attempts, last_error)
        raise ExtractionValidationError(
            paper.id, attempts, last_error or RuntimeError("unknown failure"),
        )

    # --- Internals --------------------------------------------------

    def _render(self, paper: Paper) -> str:
        fulltext_section = ""
        if paper.fulltext:
            fulltext_section = f"\nFull text:\n\n```\n{paper.fulltext}\n```\n"
        return self._prompt.render(
            paper_id=paper.id,
            title=paper.title,
            year=paper.year if paper.year is not None else "",
            venue=paper.venue or "",
            authors=", ".join(paper.authors) if paper.authors else "",
            abstract=paper.abstract or "",
            fulltext_section=fulltext_section,
        )

    def _parse_validate_augment(
        self, paper: Paper, raw: str
    ) -> PaperExtraction:
        """Parse raw model output → validate against schema → enforce
        compound-splitting → attach prompt-hash provenance."""
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as e:
            raise ExtractionParseError(paper.id, 1, e) from e

        # Provenance is authoritative from OUR side, not the model's.
        # The model tends to ECHO the example values from the prompt's
        # schema block (e.g. "extractor": "gemini-flash-2.5", a stale
        # literal, and a made-up "extracted_at"). Those would
        # misattribute the extraction — the very corruption the
        # model-in-cache-key work guards against. Always override with
        # the true model identity and the real extraction time.
        data["extractor"] = self._llm.name
        data["extracted_at"] = datetime.now(timezone.utc).isoformat()
        # A paper_id mismatch would indicate a mock/prompt bug — refuse.
        if data.get("paper_id") != paper.id:
            raise ExtractionValidationError(
                paper.id, 1,
                ValueError(
                    f"model returned paper_id={data.get('paper_id')!r} "
                    f"but expected {paper.id!r}"
                ),
            )

        try:
            extraction = PaperExtraction.model_validate(data)
        except ValidationError as e:
            raise ExtractionValidationError(paper.id, 1, e) from e

        extraction = enforce_compound_splitting(extraction)
        return extraction


__all__ = [
    "DEFAULT_MAX_RETRIES",
    "ExtractionResult",
    "Extractor",
]
