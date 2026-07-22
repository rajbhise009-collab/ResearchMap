"""Ingestion pipeline — the glue between LitSources and downstream code.

Provides one function, `run_ingestion`, that runs a search against one or
more `LitSource` implementations, deduplicates the union, and returns a
validated list of `Paper` objects.

Live vs. seed selection lives in `resolve_sources`, not here — that
function is the ONLY place that inspects config to pick backends.
"""

from __future__ import annotations

from collections.abc import Iterable

from backend.app.config import Settings, get_settings
from backend.app.ingestion.lit_source import LitSource, SeedLitSource
from backend.app.ingestion.normalizer import deduplicate
from backend.app.models import Paper


def resolve_sources(
    *,
    prefer: str = "auto",
    settings: Settings | None = None,
) -> list[LitSource]:
    """Pick which LitSources to use for this run.

    prefer:
      "seed" → always use the offline seed corpus.
      "live" → require OpenAlex; raises if not configured.
      "auto" → live when OPENALEX_MAILTO is set, else seed. Never mixes.
    """
    settings = settings or get_settings()

    def _seed() -> list[LitSource]:
        return [SeedLitSource(seed_dir=settings.seed_dir)]

    if prefer == "seed":
        return _seed()

    if prefer == "live":
        from backend.app.ingestion.openalex import OpenAlexClient
        from backend.app.ingestion.semantic_scholar import SemanticScholarClient
        sources: list[LitSource] = [OpenAlexClient()]
        try:
            sources.append(SemanticScholarClient())
        except Exception:  # noqa: BLE001
            pass
        return sources

    if prefer == "auto":
        if settings.can_use_openalex_live:
            return resolve_sources(prefer="live", settings=settings)
        return _seed()

    raise ValueError(f"Unknown prefer={prefer!r}; expected 'auto' | 'live' | 'seed'.")


def run_ingestion(
    query: str,
    *,
    limit: int = 50,
    sources: Iterable[LitSource] | None = None,
    prefer: str = "auto",
) -> list[Paper]:
    """Run a search across each source, then deduplicate the union.

    Any source that fails is skipped — a partial ingestion is more useful
    than none. Nothing here fabricates a paper: everything returned came
    from at least one source.
    """
    sources = list(sources) if sources is not None else resolve_sources(prefer=prefer)
    collected: list[Paper] = []
    for src in sources:
        try:
            for paper in src.search(query, limit=limit):
                collected.append(paper)
        except Exception as exc:  # noqa: BLE001
            print(f"[ingestion] source {src.name!r} failed: {exc}")
            continue
    return deduplicate(collected)


__all__ = ["resolve_sources", "run_ingestion"]
