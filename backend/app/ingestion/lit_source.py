"""LitSource — abstract interface for any literature provider.

OpenAlex, Semantic Scholar, arXiv, PubMed, Europe PMC and the offline
seed corpus all implement this. Business logic never imports a provider
SDK directly; it depends on this interface.

Each implementation is responsible for calling `normalize_paper` on its
raw records so the pipeline only sees validated `Paper` objects.
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from collections.abc import Iterator
from pathlib import Path

from backend.app.config import get_settings
from backend.app.models import Paper


class LitSource(ABC):
    """Uniform interface over every literature backend."""

    name: str = "abstract"

    @abstractmethod
    def search(self, query: str, *, limit: int) -> Iterator[Paper]:
        """Yield papers matching a free-text query, up to `limit`."""
        raise NotImplementedError

    @abstractmethod
    def get_by_id(self, paper_id: str) -> Paper | None:
        """Return a single paper by this source's native ID, or None."""
        raise NotImplementedError


class SeedLitSource(LitSource):
    """Serves the committed sample corpus in `data/seed/papers/`.

    The seed corpus is real JSON on disk shaped by `PaperExtraction` and
    `Paper`. Every file carries a `"seed_sample": true` marker so
    downstream consumers can distinguish fixture data from live records.
    """

    name = "seed"

    def __init__(self, seed_dir: Path | None = None) -> None:
        self._dir = (seed_dir or get_settings().seed_dir) / "papers"
        if not self._dir.exists():
            raise FileNotFoundError(
                f"Seed papers directory not found at {self._dir}. "
                "Commit the seed corpus before running the offline pipeline."
            )

    # --- LitSource API ---

    def search(self, query: str, *, limit: int) -> Iterator[Paper]:
        needle = query.lower().strip()
        yielded = 0
        for paper in self._iter_all_papers():
            haystack = " ".join(
                [paper.title.lower(), (paper.abstract or "").lower()]
            )
            if needle and needle not in haystack:
                continue
            yield paper
            yielded += 1
            if yielded >= limit:
                return

    def get_by_id(self, paper_id: str) -> Paper | None:
        path = self._dir / f"{paper_id}.json"
        if not path.exists():
            return None
        return self._load(path)

    # --- Helpers ---

    def all_papers(self) -> list[Paper]:
        return list(self._iter_all_papers())

    def _iter_all_papers(self) -> Iterator[Paper]:
        for path in sorted(self._dir.glob("*.json")):
            yield self._load(path)

    @staticmethod
    def _load(path: Path) -> Paper:
        with path.open("r", encoding="utf-8") as f:
            raw = json.load(f)
        raw.pop("seed_sample", None)
        return Paper.model_validate(raw)


__all__ = ["LitSource", "SeedLitSource"]
