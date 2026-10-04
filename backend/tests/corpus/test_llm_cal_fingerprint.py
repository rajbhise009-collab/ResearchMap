"""The LLM-cal library keeps its frozen label and its content fingerprint.
The label is checked always; the fingerprint is recomputed whenever the
gitignored manifest is present (it is absent in a keyless clone/CI)."""

from __future__ import annotations

import json

import pytest

from backend.app.corpus import llm_cal_fingerprint as F


def test_stored_label_and_fingerprint_shape():
    d = json.loads(F.STORED.read_text())
    assert d["label"] == "44981e91c40dfe6d"
    assert len(d["fingerprint_sha256"]) == 64 and d["n_records"] == 113


@pytest.mark.skipif(not F.MANIFEST.exists(), reason="LLM-cal manifest not present (gitignored)")
def test_fingerprint_matches_manifest_contents():
    stored = json.loads(F.STORED.read_text())
    assert F.compute()["fingerprint_sha256"] == stored["fingerprint_sha256"]


def test_fingerprint_is_order_independent_and_content_sensitive():
    recs = [{"paper_id": "a", "x": 1}, {"paper_id": "b", "x": 2}]
    assert F.fingerprint(recs) == F.fingerprint(list(reversed(recs)))
    assert F.fingerprint(recs) != F.fingerprint([{"paper_id": "a", "x": 1}, {"paper_id": "b", "x": 3}])


def test_label_and_fingerprint_shipped_side_by_side():
    from backend.app.api import data
    s = data.stats()
    assert s["manifest_hash"] == "44981e91c40dfe6d"
    assert s["content_fingerprint_sha256"] == json.loads(F.STORED.read_text())["fingerprint_sha256"]
