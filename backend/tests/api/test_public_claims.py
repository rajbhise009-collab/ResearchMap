"""Public text must not present an untested explanation as a finding.

Scans everything a reader of the site can see that carries prose: the
findings docs as exported (`data.findings()`), every shipped findings.json,
and the language packs and stats files under frontend/public/data. Fails on
phrases that stated the ML-fairness (or LLM-calibration) zero as explained,
and on any mention of the "definitional" explanation outside a section that
labels it a hypothesis."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from backend.app.api import data

REPO = Path(__file__).resolve().parents[3]
PUBLIC = REPO / "frontend" / "public" / "data"

DENYLIST = [
    "domain-shaped",
    "not a scorer failure",
    "a real finding",
    "subsequent papers don't disagree",
    "subsequent papers don’t disagree",
    "0/54",
    "bounded above",
    "is the *correct* answer",
    "correct result for a coherent field",
    "papers here disagree about which incompatibility",
    "because the field is coherent",
]
HEDGES = ("hypothes", "not established", "untested", "not tested")


def _strings(obj):
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for v in obj.values():
            yield from _strings(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _strings(v)


def _public_texts() -> list[tuple[str, str]]:
    out = [(f"findings:{f['slug']}", f["markdown"]) for f in data.findings()]
    for p in sorted(PUBLIC.rglob("*.json")):
        if p.name in ("findings.json", "language.json", "stats.json", "libraries.json"):
            out.append((str(p.relative_to(REPO)),
                        "\n".join(_strings(json.loads(p.read_text())))))
    return out


@pytest.mark.parametrize("name,text", _public_texts(), ids=lambda x: x if isinstance(x, str) and len(x) < 90 else "")
def test_no_denylisted_claim(name, text):
    low = text.lower()
    hits = [d for d in DENYLIST if d.lower() in low]
    assert not hits, f"{name}: {hits}"


def _sections(md: str) -> list[str]:
    return re.split(r"^#{1,6} ", md, flags=re.M)


@pytest.mark.parametrize("finding", data.findings(), ids=lambda f: f["slug"])
def test_definitional_only_inside_hypothesis_sections(finding):
    for sec in _sections(finding["markdown"]):
        if "definitional" in sec.lower():
            assert any(h in sec.lower() for h in HEDGES), (
                f"{finding['slug']}: 'definitional' outside a hypothesis-labelled "
                f"section: {sec[:160]!r}")


def test_shipped_findings_match_docs():
    """The shipped findings.json files are the current docs (regenerated)."""
    want = {f["slug"]: f["markdown"] for f in data.findings()}
    for p in sorted(PUBLIC.rglob("findings.json")):
        got = {f["slug"]: f["markdown"] for f in json.loads(p.read_text())["items"]}
        assert got == want, f"{p.relative_to(REPO)} is stale — re-export snapshots"


def test_no_generator_markers_in_public_findings():
    assert all("<!-- gen:" not in f["markdown"] for f in data.findings())


def test_spend_figures_never_rendered_in_ui():
    """spend_to_date_usd lives in stats.json for the record; no component
    may display it."""
    ui = REPO / "frontend"
    offenders = [str(p.relative_to(REPO)) for p in ui.rglob("*.tsx")
                 if "node_modules" not in p.parts and ".next" not in p.parts
                 and "spend_to_date_usd" in p.read_text()]
    assert offenders == []


def test_no_costs_or_contact_emails_in_shipped_data():
    """Public data files carry no per-library spend figures and no email
    addresses (author contacts are redacted from abstracts)."""
    import re
    email = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
    bad = []
    for p in PUBLIC.rglob("*.json"):
        t = p.read_text()
        if "spend_to_date_usd" in t or "spend_note" in t or email.search(t):
            bad.append(str(p.relative_to(REPO)))
    assert not bad, bad[:5]
