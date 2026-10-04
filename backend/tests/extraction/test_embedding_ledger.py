"""Embedding calls go through the spend ledger: headroom is checked before
each paid chunk and every successful chunk is recorded. Mock transport and
a temp ledger only — the real embedding API is never called."""

from __future__ import annotations

import json

import httpx
import pytest

from backend.app.extraction.spend_ledger import (
    LEDGER_PATH,
    SpendCapExceededError,
    SpendLedger,
    default_ledger_path,
)
from backend.app.relationships.embeddings import GeminiEmbeddingClient


def _client(handler, ledger=None, stage="embed_test"):
    http = httpx.Client(transport=httpx.MockTransport(handler))
    return GeminiEmbeddingClient(api_key="fake", model_name="gemini-embedding-001",
                                 dim=4, client=http, stage=stage, ledger=ledger)


def _ok(request: httpx.Request) -> httpx.Response:
    n = len(json.loads(request.content)["requests"])
    return httpx.Response(200, json={"embeddings": [{"values": [1, 0, 0, 0]}] * n})


def test_each_chunk_is_recorded_with_estimated_tokens():
    led = SpendLedger.load()
    c = _client(_ok)
    c.BATCH = 2
    c.embed(["a" * 30, "b" * 30, "c" * 30])          # 2 chunks
    entries = json.loads(led.path.read_text())["entries"]
    assert [e["n_texts"] for e in entries] == [2, 1]
    assert all(e["kind"] == "embedding" and e["stage"] == "embed_test"
               and e["tokens_estimated"] and e["cost_usd"] > 0 for e in entries)


def test_embedding_refused_at_cap_before_any_request():
    led = SpendLedger.load()
    led.path.write_text(json.dumps({"cap_inr": 0.0, "cap_usd": 0.0,
                                    "fx_usd_to_inr": 84.0, "entries": []}))
    hits = []

    def handler(req):
        hits.append(req)
        return _ok(req)

    with pytest.raises(SpendCapExceededError):
        _client(handler).embed(["some claim text"])
    assert hits == [], "no request may be sent once the ceiling is reached"


def test_shortlist_dry_run_path_is_ledgered(tmp_path, monkeypatch):
    """compute_shortlist with real embeddings (the path the shortlist
    'dry-run' takes) records its embedding spend."""
    from backend.app.corpus import multi_domain_reason as R
    from backend.app.models import Claim, PaperExtraction
    monkeypatch.setattr(R, "_reason_dir", lambda slug: tmp_path / slug)
    exts = [PaperExtraction.model_construct(paper_id=f"openalex:W{i}", claims=[
        Claim.model_construct(id=f"openalex:W{i}:c1", paper_id=f"openalex:W{i}",
                              text=f"claim number {i}", type="finding")])
        for i in range(3)]
    R.compute_shortlist(exts, slug="diet-and-mortality",
                        embed_client=_client(_ok, stage="embed_diet-and-mortality"))
    entries = json.loads(SpendLedger.load().path.read_text())["entries"]
    assert entries and entries[0]["stage"] == "embed_diet-and-mortality"


def test_default_ledger_path_is_never_the_real_one_under_test():
    assert default_ledger_path() != LEDGER_PATH
    assert SpendLedger().path != LEDGER_PATH
