"""Second diet packet: items 1-12 are v1's verbatim, 13-14 are the two
doubted audit pairs, nothing in the v1 folder changes, the key lands only in
the given (temp) directory, and the packet leaks no answers."""

from __future__ import annotations

import hashlib
import json

from backend.app.review import build_diet_packet_v2 as V2


def _hashes():
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(V2.V1_DIR.iterdir()) if p.is_file()}


def _fake_v1_key(tmp_path):
    items = [{"item_id": f"item-{i:02d}", "provenance": "control", "audit_verdict": None,
              "audit_reason": None, "a_paper_id": f"openalex:X{i}",
              "b_paper_id": f"openalex:Y{i}"} for i in range(1, 13)]
    p = tmp_path / "v1_key.json"
    p.write_text(json.dumps({"items": items}))
    return p


def test_v2_packet_structure_and_v1_untouched(tmp_path):
    before = _hashes()
    out, key_dir = tmp_path / "out", tmp_path / "private"
    V2.build(out_dir=out, key_out_dir=key_dir, v1_key_path=_fake_v1_key(tmp_path))
    assert _hashes() == before, "the frozen v1 packet must not change"

    v1_blocks = V2.v1_item_blocks()
    v2_blocks = V2.v1_item_blocks((out / "packet.md").read_text())
    assert len(v2_blocks) == 14
    assert v2_blocks[:12] == v1_blocks, "items 1-12 must be v1's, byte for byte"

    rows = (out / "response_form.csv").read_text().splitlines()
    assert rows[-1].startswith("item-14") and len(rows) == 15

    key = json.loads((key_dir / V2.KEY_NAME).read_text())
    assert [k["item_id"] for k in key["items"]] == [f"item-{i:02d}" for i in range(1, 15)]
    assert {k["audit_pair"] for k in key["items"][12:]} == {1, 5}
    assert not (key_dir / "answer_key.json").exists(), "v1 key name is never written"


def test_packet_leaks_no_answers(tmp_path):
    out = tmp_path / "out"
    V2.build(out_dir=out, key_out_dir=tmp_path / "k", v1_key_path=_fake_v1_key(tmp_path))
    text = (out / "packet.md").read_text().lower() + (out / "packet.html").read_text().lower()
    for leak in ("genuine-doubted", "audit", "doubt", "openalex:", "control pair", "artifact pair"):
        assert leak not in text, leak


def test_committed_v2_packet_matches_builder_items():
    """The committed v2 packet's items 1-12 equal the frozen v1 packet's."""
    committed = (V2.OUT_DIR / "packet.md").read_text()
    assert V2.v1_item_blocks(committed)[:12] == V2.v1_item_blocks()
