"""On-disk cache for PaperExtraction results.

Keyed by (paper_id, prompt_hash) so re-running with a different prompt
version doesn't accidentally serve stale extractions. The cache lives
under `data/cache/extractions/` and is git-ignored — regenerable from
the raw dumps + prompts.

The store is content-addressed JSON: one file per (paper_id,
prompt_hash), atomic write via `.tmp` + rename so a crash mid-write
never leaves half-written JSON.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

from backend.app.config import REPO_ROOT
from backend.app.models import PaperExtraction


_UNSAFE = re.compile(r"[^A-Za-z0-9_.-]+")


def _safe(component: str) -> str:
    """Turn arbitrary paper IDs into filesystem-safe strings."""
    return _UNSAFE.sub("_", component)


class ExtractionCache:
    """Disk cache. All I/O is synchronous; the objects are small.

    Key is (paper_id, model, input_source, prompt_hash). Every element is
    part of what produced the output, so all four are in the key:
      - MODEL: re-running on a different model would otherwise serve the
        old model's extractions.
      - INPUT_SOURCE ("abstract" | "fulltext"): the same paper + model +
        prompt produces DIFFERENT extractions from the abstract vs. the
        full text. Without this in the key the controlled abstract-vs-
        fulltext comparison would collide — the second run would either
        hit the first's cache or overwrite it.
      - PROMPT_HASH: a prompt change is a different extraction.
    """

    def __init__(self, root: Path | None = None) -> None:
        self.root = root or (REPO_ROOT / "data" / "cache" / "extractions")

    def _key_path(
        self, paper_id: str, model: str, input_source: str, prompt_hash: str
    ) -> Path:
        return (
            self.root / _safe(paper_id)
            / f"{_safe(model)}__{_safe(input_source)}__{_safe(prompt_hash)}.json"
        )

    def get(
        self, paper_id: str, model: str, input_source: str, prompt_hash: str
    ) -> PaperExtraction | None:
        path = self._key_path(paper_id, model, input_source, prompt_hash)
        if not path.exists():
            return None
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            return PaperExtraction.model_validate(raw)
        except Exception:
            # A stale/corrupt cache entry is a MISS — not a fatal
            # error. It will be overwritten on the next put().
            return None

    def put(
        self, paper_id: str, model: str, input_source: str, prompt_hash: str,
        extraction: PaperExtraction,
    ) -> None:
        path = self._key_path(paper_id, model, input_source, prompt_hash)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(extraction.model_dump_json(indent=2), encoding="utf-8")
        os.replace(tmp, path)  # atomic on POSIX


__all__ = ["ExtractionCache"]
