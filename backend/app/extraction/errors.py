"""Extractor-side exceptions.

Deliberately narrow. The extractor either returns a valid, schema-
compliant PaperExtraction, or it raises. Silent partial output is a
correctness bug, not an operational one — never mask it.
"""


class ExtractionError(RuntimeError):
    """Base class for extraction failures."""


class RetryableResponseError(RuntimeError):
    """A 200 response that is UNUSABLE and worth retrying: bad JSON,
    schema-invalid, or paper_id mismatch. Raised by a `validate`
    callback passed into `LLMClient.generate`, caught by the client's
    retry loop. `kind` lets the caller map the final failure to the
    right hard error type.

    kind ∈ {"parse", "schema", "paper_id"}.
    """

    def __init__(self, kind: str, message: str):
        super().__init__(message)
        self.kind = kind


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
    "RetryableResponseError",
]
