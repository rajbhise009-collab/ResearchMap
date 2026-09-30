"""Contradiction-audit reader — maps raw-flagged pairs to hand-audited
verdicts (genuine / artifact / duplicate) so the UI can show only the
genuine ones headline and separate the set-aside pairs with reasons.

The lookup key is (a_paper_id, b_paper_id, a_text[:60], b_text[:60])
rather than an index so a re-run of the contradiction pass with
different pair ordering doesn't invalidate the audit. Verdicts live in
`data/domains/<slug>/reasoning/contradiction_audit.json`.
"""

from __future__ import annotations

import json
from pathlib import Path

from backend.app.config import REPO_ROOT

_UNAUDITED_DEFAULT = {"verdict": "unaudited",
                       "reason": "No hand-audit recorded for this pair.",
                       "basis": None}


def _audit_path(slug: str) -> Path:
    return (REPO_ROOT / "data" / "domains" / slug / "reasoning"
            / "contradiction_audit.json")


def _norm(text: str, n: int = 60) -> str:
    return " ".join((text or "").split())[:n].strip()


def load_audit(slug: str) -> dict:
    p = _audit_path(slug)
    if not p.exists():
        return {"domain": slug, "verdicts": [], "basis": None}
    return json.loads(p.read_text())


def _key(a_pid: str, b_pid: str, a_text: str, b_text: str) -> tuple:
    """Canonical key. Unordered pair (sorted), plus first ~60 chars of
    each text so a rerun with reordered pairs still maps."""
    a, b = sorted([(a_pid, _norm(a_text)), (b_pid, _norm(b_text))])
    return (a[0], b[0], a[1], b[1])


def verdict_lookup(slug: str) -> dict[tuple, dict]:
    """Return a dict keyed by canonical pair-key → verdict record.
    Records include: verdict, reason, topic, basis, date."""
    audit = load_audit(slug)
    basis = audit.get("basis")
    date = audit.get("date")
    out: dict[tuple, dict] = {}
    for v in audit.get("verdicts", []):
        k = _key(v["a_paper_id"], v["b_paper_id"],
                 v.get("a_text_starts", ""), v.get("b_text_starts", ""))
        out[k] = {
            "verdict": v.get("verdict", "unaudited"),
            "reason": v.get("reason", ""),
            "topic": v.get("topic", ""),
            "basis": basis, "date": date,
        }
    return out


def attach_verdicts(slug: str, contradictions: list[dict]) -> list[dict]:
    """Given a list of raw-flagged contradiction records (with
    a_paper_id/b_paper_id/a_text/b_text) attach the verdict from the
    audit. Records without a match get 'unaudited'."""
    table = verdict_lookup(slug)
    out = []
    for c in contradictions:
        k = _key(c.get("a_paper_id", ""), c.get("b_paper_id", ""),
                  c.get("a_text", ""), c.get("b_text", ""))
        v = table.get(k, _UNAUDITED_DEFAULT.copy())
        merged = dict(c)
        merged["audit"] = v
        out.append(merged)
    return out


def audit_summary(slug: str, contradictions: list[dict]) -> dict:
    """Counts: raw_flagged, genuine, artifact, duplicate, unaudited."""
    from collections import Counter
    attached = attach_verdicts(slug, contradictions)
    counts = Counter(c["audit"]["verdict"] for c in attached)
    return {
        "raw_flagged": len(contradictions),
        "genuine": counts.get("genuine", 0),
        "artifact": counts.get("artifact", 0),
        "duplicate": counts.get("duplicate", 0),
        "unaudited": counts.get("unaudited", 0),
        "confirmed": counts.get("genuine", 0),  # headline number
    }


__all__ = ["load_audit", "verdict_lookup", "attach_verdicts",
            "audit_summary"]
