"""LLMClient interface tests. GeminiLLMClient is instantiated but
never has .generate() invoked — no live spend."""

from __future__ import annotations

import pytest

from backend.app.extraction.llm_client import (
    GeminiLLMClient,
    MockLLMClient,
    ProgrammableMockLLMClient,
)


def test_mock_llm_extracts_paper_id_from_prompt(tmp_path):
    """MockLLMClient regex-extracts `Paper ID: `<id>`` from the
    rendered prompt and returns the canned JSON for that id."""
    # Set up a fake extractions dir with one canned file.
    (tmp_path / "openalex:W1.json").write_text('{"paper_id": "openalex:W1"}')
    mock = MockLLMClient(extractions_dir=tmp_path)
    prompt = "some header\nPaper ID: `openalex:W1`\nrest of prompt"
    assert mock.generate(prompt) == '{"paper_id": "openalex:W1"}'


def test_mock_llm_refuses_without_paper_id_marker(tmp_path):
    mock = MockLLMClient(extractions_dir=tmp_path)
    with pytest.raises(RuntimeError):
        mock.generate("prompt with no id marker")


def test_mock_llm_refuses_unknown_paper(tmp_path):
    mock = MockLLMClient(extractions_dir=tmp_path)
    with pytest.raises(FileNotFoundError):
        mock.generate("Paper ID: `openalex:W_unknown`")


def test_programmable_mock_returns_sequence():
    mock = ProgrammableMockLLMClient(["one", "two", "three"])
    assert mock.generate("prompt A") == "one"
    assert mock.generate("prompt B") == "two"
    assert mock.generate("prompt C") == "three"
    assert mock.call_count == 3


def test_programmable_mock_raises_when_exhausted():
    mock = ProgrammableMockLLMClient(["one"])
    mock.generate("x")
    with pytest.raises(StopIteration):
        mock.generate("x")


def test_gemini_client_refuses_without_api_key():
    """The Gemini client MUST refuse to instantiate without an API key.
    Otherwise an autonomy-policy violation (paid-API spend without
    approval) could slip through."""
    with pytest.raises(RuntimeError):
        GeminiLLMClient()


def test_gemini_client_instantiates_with_explicit_key():
    """Given an explicit key, the constructor succeeds. No .generate()
    is invoked in this test — that would be a paid API call."""
    client = GeminiLLMClient(api_key="fake-test-key")
    assert client.name == "gemini-gemini-2.5-flash"
    # We deliberately do NOT call client.generate(). That would spend.
