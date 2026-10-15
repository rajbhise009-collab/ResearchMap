"""The site's production address, from frontend/site.config.json (the same
file the frontend build uses), overridable with NEXT_PUBLIC_SITE_URL.
Standard library only (the daily health workflow installs nothing else)."""
from __future__ import annotations

import json
import os
from pathlib import Path

_CFG = Path(__file__).resolve().parents[1] / "frontend" / "site.config.json"


def _cfg() -> dict:
    try:
        return json.loads(_CFG.read_text())
    except (OSError, ValueError):
        return {}


def site_url() -> str:
    return (os.environ.get("NEXT_PUBLIC_SITE_URL") or _cfg().get("siteUrl")
            or "https://researchmap-one.vercel.app").rstrip("/")


def vercel_host() -> str:
    """The old *.vercel.app host for the live check; GROW_VERCEL_HOST="" (set
    but empty) means: skip that check (local and offline runs)."""
    if "GROW_VERCEL_HOST" in os.environ:
        return os.environ["GROW_VERCEL_HOST"]
    return _cfg().get("vercelHost") or "researchmap-one.vercel.app"
