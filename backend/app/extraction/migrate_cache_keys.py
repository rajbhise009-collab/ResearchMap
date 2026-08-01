"""One-time cache-key migration: 2-part -> 3-part (add input_source).

Early extractions were cached under `<model>__<prompthash>.json` before
`input_source` joined the cache key. The new lookup is
`<model>__<input_source>__<prompthash>.json`, so those old files are
orphaned (cache misses -> needless re-extraction, which burns scarce
daily quota).

Every 2-part file predates full-text extraction, so its input_source is
unambiguously "abstract". This copies each orphaned 2-part file to its
3-part `abstract` name when that target doesn't already exist. Copy,
not move, so nothing is lost if run twice; idempotent.
"""

from __future__ import annotations

import re
import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))

CACHE = REPO_ROOT / "data" / "cache" / "extractions"

# 2-part: <model>__<12-hex-prompthash>.json   (no input_source segment)
_TWO_PART = re.compile(r"^(?P<model>.+?)__(?P<hash>[0-9a-f]{12})\.json$")


def main() -> int:
    if not CACHE.exists():
        print("no cache dir; nothing to migrate")
        return 0
    migrated = skipped = 0
    for paper_dir in sorted(CACHE.iterdir()):
        if not paper_dir.is_dir():
            continue
        for f in paper_dir.glob("*.json"):
            m = _TWO_PART.match(f.name)
            if not m:
                continue  # already 3-part (has an input_source segment)
            target = paper_dir / f"{m['model']}__abstract__{m['hash']}.json"
            if target.exists():
                skipped += 1
                continue
            shutil.copy2(f, target)
            migrated += 1
    print(f"migrated {migrated} orphaned 2-part cache files -> 3-part abstract")
    print(f"skipped {skipped} (3-part already present)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
