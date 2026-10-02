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
    RetryableResponseError,
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
        """Extract one paper. Cache hit skips the LLM. On a miss the
        client's unified retry layer handles rate limiting, transient
        HTTP failures, AND unusable-response retries (via the validator
        we pass); it either returns usable text or raises. We then
        augment (compound-split, authoritative provenance) and CACHE
        BEFORE returning, so a run that dies mid-way resumes with zero
        rework."""
        cached = self._cache.get(
            paper.id, self.model, self._input_source, self._prompt.hash,
        )
        if cached is not None:
            return ExtractionResult(extraction=cached, from_cache=True, attempts=0)

        rendered = self._render(paper)
        validator = self._make_validator(paper)
        requests_before = getattr(self._llm, "total_requests", 0)
        try:
            raw = self._llm.generate(rendered, validate=validator)
        except RetryableResponseError as e:
            # The client exhausted its attempts on an unusable response.
            # Map the typed reason to the right hard error, naming the
            # paper. Never persist a partial/malformed extraction.
            attempts = getattr(self._llm, "total_requests", 0) - requests_before
            if e.kind == "parse":
                raise ExtractionParseError(paper.id, attempts, e) from e
            raise ExtractionValidationError(paper.id, attempts, e) from e

        # `raw` already passed the validator (parse + schema + paper_id).
        extraction = self._parse_validate_augment(paper, raw)
        self._cache.put(
            paper.id, self.model, self._input_source, self._prompt.hash,
            extraction,
        )
        attempts = max(1, getattr(self._llm, "total_requests", 1) - requests_before)
        return ExtractionResult(
            extraction=extraction, from_cache=False, attempts=attempts,
        )

    # --- Internals --------------------------------------------------

    def _make_validator(self, paper: Paper):
        """Build the `validate` callback passed to the client's retry
        loop. Raises RetryableResponseError (with a typed `kind`) on any
        unusable response so the client retries within its budget."""
        def _validate(text: str) -> None:
            try:
                data = json.loads(text)
            except json.JSONDecodeError as e:
                raise RetryableResponseError("parse", str(e)) from e
            # A valid extraction is an object; some paper responses have
            # come back as a bare list (likely the model returned the
            # claims array without wrapping it). Treat that as a
            # retryable parse failure instead of an unhandled
            # AttributeError that halts the whole run.
            if not isinstance(data, dict):
                raise RetryableResponseError(
                    "parse",
                    f"model returned top-level {type(data).__name__}, "
                    "expected a JSON object with paper_id/claims/…")
            if data.get("paper_id") != paper.id:
                raise RetryableResponseError(
                    "paper_id",
                    f"model returned paper_id={data.get('paper_id')!r} "
                    f"but expected {paper.id!r}",
                )
            # Validate against the schema (with authoritative provenance
            # filled so the model's echoed/missing values don't fail it).
            probe = dict(data)
            probe["extractor"] = self._llm.name
            probe["extracted_at"] = datetime.now(timezone.utc).isoformat()
            try:
                PaperExtraction.model_validate(probe)
            except ValidationError as e:
                raise RetryableResponseError("schema", str(e)) from e
        return _validate

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
