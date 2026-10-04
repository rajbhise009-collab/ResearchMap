"""Content fingerprint of the frozen LLM-calibration library.

  python -m backend.app.corpus.llm_cal_fingerprint           # print
  python -m backend.app.corpus.llm_cal_fingerprint --write   # store in data/llm_cal_fingerprint.json

`44981e91c40dfe6d` is the library's frozen LABEL: the `manifest_hash`
field written when the manifest was first generated (2026-07-25), before
the OA-recovery and finalize steps changed its records. It identifies the
library; it is not a hash of the current contents and is never recomputed.

The FINGERPRINT is a true content hash: SHA-256 over the manifest's
records, each serialised as canonical JSON (sorted keys, no whitespace,
UTF-8), the serialised lines sorted, joined with "\\n". Any change to any
field of any record changes it. The test suite recomputes it whenever the
(gitignored) manifest file is present.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
MANIFEST = REPO_ROOT / "data" / "live_samples" / "expanded_corpus_manifest.json"
STORED = REPO_ROOT / "data" / "llm_cal_fingerprint.json"
LABEL = "44981e91c40dfe6d"


def canonical_lines(records: list[dict]) -> list[str]:
    return sorted(json.dumps(r, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
                  for r in records)


def fingerprint(records: list[dict]) -> str:
    return hashlib.sha256("\n".join(canonical_lines(records)).encode("utf-8")).hexdigest()


def compute(manifest: Path = MANIFEST) -> dict:
    m = json.loads(manifest.read_text())
    if m.get("manifest_hash") != LABEL:
        raise RuntimeError(f"manifest label is {m.get('manifest_hash')!r}, expected {LABEL!r}")
    return {
        "label": LABEL,
        "label_note": ("Frozen identifier written at manifest generation "
                       "(2026-07-25), before later steps changed the records. "
                       "A label, not a content hash."),
        "fingerprint_sha256": fingerprint(m["records"]),
        "n_records": len(m["records"]),
        "method": ("SHA-256 over the manifest records, each as canonical JSON "
                   "(sort_keys, separators=(',', ':'), ensure_ascii=False), "
                   "lines sorted, joined with '\\n', UTF-8"),
        "source": "data/live_samples/expanded_corpus_manifest.json (gitignored)",
        "script": "backend/app/corpus/llm_cal_fingerprint.py",
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args()
    r = compute()
    if a.write:
        STORED.write_text(json.dumps(r, indent=2) + "\n")
    print(json.dumps(r, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
