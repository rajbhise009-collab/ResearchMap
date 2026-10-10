"""Generated search phrases per library, from each library's OWN index.

Shared by the search tests (backend/tests/api/test_search_autogen.py) and the
smoke checks (tools/qa/smoke.py, which also runs in the daily health
workflow). Standard library only: the daily workflow installs nothing but
Playwright.

For each built library (frontend/public/data/libraries.json): its 15 most
distinctive two-word phrases taken from its own document titles (both words
in at most 15% of this library's documents and rarer in every other
library). REFUSE: 5 queries far from every library.
"""
from __future__ import annotations

import json
import math
import re
from pathlib import Path

from backend.app.api.search_index import STOPWORDS, _stem

DATA = Path(__file__).resolve().parents[3] / "frontend" / "public" / "data"
LIBS = json.loads((DATA / "libraries.json").read_text())["libraries"]
MAX_SHARE = 0.15
# Far from every library this project could hold (not "stock market": an
# economics or behavioural library may legitimately cover markets).
REFUSE = ["melanoma treatment", "volcano eruption forecasting", "camera calibration for stereo vision",
          "quantum computing error correction", "medieval castle architecture"]


def _idx(lib):
    d = DATA if lib["snapshot_path"] == "/data" else DATA / lib["snapshot_path"].removeprefix("/data/")
    return json.loads((d / "search-index.json").read_text())


INDEX = {l["slug"]: _idx(l) for l in LIBS}


def _df_share(idx: dict) -> dict[str, float]:
    n = idx["n_docs"]
    return {t: max(0.0, (n + 1) / math.exp(v) - 0.5) / n for t, v in idx["idf"].items() if "__" not in t}


def queries(slug: str) -> list[str]:
    idx = INDEX[slug]
    here = _df_share(idx)
    others = [_df_share(INDEX[s]) for s in INDEX if s != slug]
    # Distinctive AND specific: very common words (e.g. "models" in a
    # language-model library) are deliberately answered "borderline" by the
    # search gate, so they are not used as must-be-in-domain tests.
    score = {t: here[t] - max((o.get(t, 0.0) for o in others), default=0.0)
             for t in here if here[t] <= MAX_SHARE}
    # map stems back to a real word from document titles
    word_for: dict[str, str] = {}
    pair_score: dict[str, float] = {}
    for d in idx["docs"]:
        words = [w for w in re.findall(r"[a-z][a-z-]+", d["title"].lower()) if w not in STOPWORDS and len(w) > 3]
        for w in words:
            word_for.setdefault(_stem(w), w)
        for a, b in zip(words, words[1:]):
            sa, sb = score.get(_stem(a), -1), score.get(_stem(b), -1)
            if sa > 0 and sb > 0:
                pair_score[f"{a} {b}"] = max(pair_score.get(f"{a} {b}", 0), sa + sb)
    return [p for p, _s in sorted(pair_score.items(), key=lambda x: (-x[1], x[0]))][:15]
