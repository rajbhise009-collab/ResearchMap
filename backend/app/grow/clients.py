"""Build the weekly-growth clients. Real clients need OPENALEX_API_KEY and
GEMINI_API_KEY in the environment; a missing one is a clean stop, never a
fallback to anything else. Mock clients are only for the offline end-to-end
test and are refused unless GROW_MOCK=1 is set explicitly."""

from __future__ import annotations

import os

from backend.app.grow.core import Clients, GrowStop


def real_clients() -> Clients:
    missing = [k for k in ("OPENALEX_API_KEY", "GEMINI_API_KEY") if not os.environ.get(k)]
    if missing:
        raise GrowStop(
            f"missing secret(s): {', '.join(missing)}",
            "Add the missing repository secret(s) under Settings → Secrets and variables → "
            "Actions, then run “Weekly grow” once from the Actions tab.")
    import httpx

    from backend.app.config import get_settings
    from backend.app.corpus.multi_domain import retrieve_fulltext_one
    from backend.app.extraction.batch_client import GeminiBatchClient
    from backend.app.extraction.llm_client import GeminiLLMClient
    from backend.app.refresh.weekly_candidates import LiveOpenAlexClient
    from backend.app.relationships.embeddings import GeminiEmbeddingClient
    model = get_settings().gemini_model
    try:
        batch = GeminiBatchClient(model_name=model)          # validates the model exists
    except Exception as e:  # noqa: BLE001
        raise GrowStop(f"Gemini model unavailable: {type(e).__name__}",
                       f"The configured model ({model}) could not be used. Check that the "
                       "GEMINI_API_KEY secret is valid and that the model still exists; "
                       "change GEMINI_MODEL in the workflow if Google retired it.") from None
    http = httpx.Client(timeout=25.0, follow_redirects=True,
                        headers={"User-Agent": "ResearchMap/0.3 weekly-grow"})
    return Clients(
        openalex=LiveOpenAlexClient(os.environ["OPENALEX_API_KEY"]),
        batch=batch,
        embed=GeminiEmbeddingClient(stage="grow_embed"),
        llm=GeminiLLMClient(validate_model=False),
        fulltext=lambda e, r: retrieve_fulltext_one(e, r, client=http),
    )


def make_clients() -> Clients:
    if os.environ.get("GROW_MOCK") == "1":
        from backend.app.grow.mocks import mock_clients
        return mock_clients(os.environ.get("GROW_MOCK_FIXTURE"))
    return real_clients()
