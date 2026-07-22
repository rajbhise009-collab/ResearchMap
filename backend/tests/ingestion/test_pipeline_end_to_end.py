"""End-to-end offline pipeline — the phase-1 acceptance test."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from backend.app.ingestion.pipeline import resolve_sources, run_ingestion
from backend.app.models import Paper, Source

REPO_ROOT = Path(__file__).resolve().parents[3]


def test_resolve_sources_falls_back_to_seed_without_api_key():
    sources = resolve_sources(prefer="auto")
    assert len(sources) == 1
    assert sources[0].name == "seed"


def test_end_to_end_ingestion_over_seed_corpus():
    papers = run_ingestion(query="", limit=100, prefer="seed")
    assert 30 <= len(papers) <= 50
    assert all(isinstance(p, Paper) for p in papers)
    # Every returned paper validates against the Pydantic schema.
    for p in papers:
        Paper.model_validate(p.model_dump())
    # Every paper traces to a real seed source.
    assert all(p.source == Source.SEED.value for p in papers)


def test_end_to_end_ingestion_dedups_across_synthetic_duplicates():
    """Feed the same seed source twice and confirm dedup collapses everything."""
    from backend.app.ingestion.lit_source import SeedLitSource
    src = SeedLitSource()
    doubled = run_ingestion(query="", limit=200, sources=[src, src])
    once = run_ingestion(query="", limit=200, sources=[src])
    assert len(doubled) == len(once)


def test_cli_ingest_emits_valid_json():
    """Run the CLI as a subprocess and confirm its stdout is valid JSON
    matching the announced shape."""
    result = subprocess.run(
        [sys.executable, "-m", "backend.cli", "ingest",
         "--source", "seed", "--limit", "5"],
        capture_output=True, text=True, cwd=REPO_ROOT, timeout=60, check=True,
    )
    payload = json.loads(result.stdout)
    assert payload["source_preference"] == "seed"
    assert payload["count"] == len(payload["papers"])
    assert payload["count"] <= 5
    # Every emitted paper validates against Paper schema.
    for record in payload["papers"]:
        Paper.model_validate(record)
