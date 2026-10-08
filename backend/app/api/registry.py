"""The library registry (data/library_registry.json): every library the
site knows, built or queued. The one place a library is declared."""

from __future__ import annotations

import json
from pathlib import Path

from backend.app.config import REPO_ROOT

PATH = REPO_ROOT / "data" / "library_registry.json"


def load() -> list[dict]:
    return json.loads(PATH.read_text())["libraries"]


def built() -> list[dict]:
    return [l for l in load() if l["status"] == "built"]


def queued() -> list[dict]:
    return [l for l in load() if l["status"] == "queued"]


def growable() -> list[str]:
    """Built libraries that the weekly workflow may grow."""
    return [l["slug"] for l in built() if not l["frozen"]]


def get(slug: str) -> dict:
    return next(l for l in load() if l["slug"] == slug)


def set_status(slug: str, status: str) -> None:
    d = json.loads(PATH.read_text())
    for l in d["libraries"]:
        if l["slug"] == slug:
            l["status"] = status
    PATH.write_text(json.dumps(d, indent=1) + "\n")
