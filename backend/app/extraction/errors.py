"""Extractor-side exceptions.

Deliberately narrow. The extractor either returns a valid, schema-
compliant PaperExtraction, or it raises. Silent partial output is a
correctness bug, not an operational one — never mask it.
"""


class ExtractionError(RuntimeError):
    """Base class for extraction failures."""


class ExtractionValidationError(ExtractionError):
    """The LLM's output could not be validated against the
    PaperExtraction schema, even after retries."""

    def __init__(self, paper_id: str, attempts: int, last_error: Exception):
        super().__init__(
            f"Extraction for paper {paper_id!r} failed schema validation "
            f"after {attempts} attempts: {last_error!s}"
        )
        self.paper_id = paper_id
        self.attempts = attempts
        self.last_error = last_error


class ExtractionParseError(ExtractionError):
    """The LLM's output was not valid JSON."""

    def __init__(self, paper_id: str, attempts: int, last_error: Exception):
        super().__init__(
            f"Extraction for paper {paper_id!r} produced non-JSON output "
            f"after {attempts} attempts: {last_error!s}"
        )
        self.paper_id = paper_id
        self.attempts = attempts
        self.last_error = last_error


__all__ = [
    "ExtractionError",
    "ExtractionParseError",
    "ExtractionValidationError",
]
