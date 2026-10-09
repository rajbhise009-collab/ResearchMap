"""Protocol v1 (docs/findings/validation-protocol-v1.md): the run is
leak-free, deterministic from its caches, and its thresholds are the
2026-10-09 amendment's. Free: uses data/validation/v1/ caches only."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from backend.app.validation import v1

RESULT = v1.DIR / "result.json"
pytestmark = pytest.mark.skipif(not RESULT.exists(), reason="protocol v1 has not been run")


def test_no_citing_paper_dated_at_or_before_the_freeze():
    files = list((v1.DIR / "openalex").glob("citing_*.json"))
    assert files
    for f in files:
        Y = int(f.stem.rsplit("_", 1)[1])
        for c in json.loads(f.read_text()):
            assert c["date"] and int(c["date"][:4]) > Y, (f.name, c["id"], c["date"])
            assert int(c["date"][:4]) <= Y + v1.PROTOCOL["window_years"], (f.name, c["id"])


def test_parameters_are_the_pre_registered_ones():
    p = v1.PROTOCOL
    assert p["commit"] == "1bcdb4b"
    assert (p["tau_draws"], p["tau_percentile"], p["seed"]) == (20, 95, 20261009)   # amendment 2026-10-09
    assert (p["perm_draws"], p["boot"], p["ks"], p["caliper"]) == (10_000, 2_000, (5, 10, 20), 0.5)
    assert (p["abstract_chars"], p["cap_options"], p["budget_inr"], p["pad"]) == (600, (20, 15, 10, 8, 5), 20.0, 1.5)
    assert json.loads(RESULT.read_text())["protocol"]["commit"] == "1bcdb4b"


def test_tau_follows_the_amendment():
    """Recompute one library's tau straight from the amendment's text: for
    each open question with m usable citing abstracts, 20 seeded draws of m
    abstracts from the library's papers OLDER than its source paper, max
    cosine per draw, 95th percentile over all draws."""
    r = json.loads(RESULT.read_text())
    items, corpora = v1.pool()
    cache = v1._emb_cache()
    rng = np.random.default_rng(v1.PROTOCOL["seed"])
    for s in v1.LIBS:                       # same order as the run (shared RNG stream)
        abs_ = v1._library_abstracts(s)
        rc = corpora[s]
        fwv = {f: rc.fw_vectors[i] / np.linalg.norm(rc.fw_vectors[i]) for i, f in enumerate(rc.fw_ids)}
        draws = []
        for it in [x for x in items if x["library"] == s]:
            m = len(v1.usable_citing(it["source_wid"], it["freeze_year"], r["cap_used"]))
            older = [t for (y, t) in abs_.values() if y < it["source_year"]]
            if m == 0 or not older:
                continue
            ov = np.stack([v1._vec(cache, t) for t in older])
            for _ in range(20):
                pick = rng.choice(len(older), size=m, replace=len(older) < m)
                draws.append(float((ov[pick] @ fwv[it["fw_id"]]).max()))
        want = round(float(np.percentile(draws, 95)), 4) if draws else None
        assert r["tau"][s] == want, (s, r["tau"][s], want)


def test_rerun_from_caches_is_identical_and_free(tmp_path):
    before = json.loads(RESULT.read_text())
    from backend.app.extraction.spend_ledger import SpendLedger
    spent0 = SpendLedger.load().snapshot()["cumulative_inr"]
    again = v1.run()          # every fetch and embedding is cached: no API call
    assert SpendLedger.load().snapshot()["cumulative_inr"] == spent0
    for k in ("tau", "N", "addressed", "results", "verdict", "cap_used"):
        assert json.loads(json.dumps(again[k], default=str)) == before[k], k


def test_site_never_claims_validated_unless_supported():
    """Unless the pre-registered verdict is 'supported', every 'validated' a
    reader can see is negated ('not validated', 'not yet validated', ...)."""
    import re
    verdict = json.loads(RESULT.read_text())["verdict"]
    out = Path(__file__).resolve().parents[3] / "frontend" / "out"
    if verdict == "supported" or not out.exists():
        pytest.skip("supported, or no build")
    bad = []
    for f in out.rglob("*.html"):
        rel = f.relative_to(out).as_posix()
        if rel.startswith(("gap/", "paper/")):
            continue        # researchers' own words (e.g. "validated measures"), not claims about this tool
        text = re.sub(r"<[^>]+>", " ", f.read_text())
        for m in re.finditer(r"(?i)\bvalidated\b", text):
            before = text[max(0, m.start() - 40):m.start()].lower()
            negated = re.search(r"\b(not|n't|never|no)\b[\w\s-]{0,25}$", before)
            conditional = re.search(r"\b(until|unless|if|can be|to be|must be|could be)\b[\w\s-]{0,15}$", before)
            quoted = re.search(r"(&quot;|\\\"|\"|“)$", before)
            if not (negated or conditional or quoted):
                bad.append((f.relative_to(out).as_posix(), text[max(0, m.start() - 60):m.end() + 20]))
    assert not bad, bad[:5]
