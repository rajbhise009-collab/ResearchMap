"""Python and the browser must agree, exactly.

Search is implemented twice — once in Python (backend/app/api/search_index.py,
which builds the index and serves /api/search) and once in TypeScript
(frontend/lib/search.ts, which runs in the reader's browser over the static
export). If the two tokenizers drift by even one suffix rule, the shipped
index stops matching queries and the honest out-of-domain gate starts firing
on questions the library can actually answer.

Comments promising the two are in lockstep are worth nothing on their own, so
this compiles the TypeScript and compares real output.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

from backend.app.api import data, export, language, search_index as S

REPO = Path(__file__).resolve().parents[3]
FRONTEND = REPO / "frontend"

pytestmark = pytest.mark.skipif(
    not shutil.which("node") or not (FRONTEND / "node_modules" / "typescript").exists(),
    reason="needs node and the frontend's TypeScript compiler",
)

TOKEN_FIXTURES = [
    "Detecting hallucinations",
    "MODEL calibration!!",
    "the and for with",
    "uncertainties",
    "running",
    "safely",
    "AI",
    "a x 42 llm",
    "Does the AI know when it does not know",
]

QUERY_FIXTURES = [
    "why does ChatGPT make things up",
    "when should a chatbot refuse to answer",
    "detecting hallucinations",
    "treatment options for early stage melanoma",
    "how do I bake sourdough bread",
    "image recognition accuracy",
    "legal contract review with AI",
    "how do I do that",
    "quantum computing error correction",
    "does the AI know when it does not know",
]

HARNESS = """
const fs = require("fs");
const { search, tokenize } = require("./search.js");
const index = JSON.parse(fs.readFileSync(process.argv[2], "utf8"));
const stop = new Set(index.stopwords);
const out = { tokens: {}, verdicts: {} };
for (const t of JSON.parse(process.argv[3])) out.tokens[t] = tokenize(t, stop, index.synonyms);
for (const q of JSON.parse(process.argv[4])) {
  const r = search(index, q, 5);
  out.verdicts[q] = { verdict: r.verdict, coverage: +r.coverage.toFixed(4),
    best: +r.best.toFixed(5), breadth: +r.breadth.toFixed(4), n: r.n_matched,
    top: r.hits.map(h => h.ref) };
}
console.log(JSON.stringify(out));
"""


@pytest.fixture(scope="module")
def index():
    cards = []
    for c in data.cards():
        card = {**c.model_dump(), "slug": export.slug(c.id)}
        card["consumer"] = language.consumer_card(card)
        cards.append(card)
    details = []
    for p in data.paper_summaries():
        d = data.paper_detail(p["paper_id"])
        d["wid"] = p["paper_id"].split(":")[-1]
        details.append(d)
    return S.build_index(cards, details)


@pytest.fixture(scope="module")
def ts_output(index):
    """Compile frontend/lib/search.ts and run it over the same index."""
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp)
        tsc = FRONTEND / "node_modules" / ".bin" / "tsc"
        subprocess.run(
            [str(tsc), "lib/search.ts", "lib/types.ts", "--outDir", str(out),
             "--module", "commonjs", "--target", "es2020",
             "--moduleResolution", "node", "--skipLibCheck"],
            cwd=FRONTEND, check=True, capture_output=True, timeout=180,
        )
        (out / "harness.js").write_text(HARNESS)
        idx_path = out / "index.json"
        idx_path.write_text(json.dumps(index))
        proc = subprocess.run(
            ["node", "harness.js", str(idx_path),
             json.dumps(TOKEN_FIXTURES), json.dumps(QUERY_FIXTURES)],
            cwd=out, check=True, capture_output=True, text=True, timeout=120,
        )
        return json.loads(proc.stdout)


@pytest.mark.parametrize("text", TOKEN_FIXTURES)
def test_tokenizers_agree(ts_output, text):
    assert S.tokenize(text) == ts_output["tokens"][text], text


@pytest.mark.parametrize("q", QUERY_FIXTURES)
def test_verdict_and_ranking_agree(index, ts_output, q):
    r = S.search(index, q, 5)
    mine = {
        "verdict": r["verdict"],
        "coverage": round(r["coverage"], 4),
        "best": round(r["best"], 5),
        "breadth": round(r["breadth"], 4),
        "n": r["n_matched"],
        "top": [h["ref"] for h in r["hits"]],
    }
    assert mine == ts_output["verdicts"][q], q


def test_the_gate_agrees_on_the_case_it_exists_for(index, ts_output):
    """The out-of-domain refusal is the product promise; if the two sides
    disagree here, the browser would show weak matches the API refuses."""
    q = "treatment options for early stage melanoma"
    assert S.search(index, q)["verdict"] == "out_of_domain"
    assert ts_output["verdicts"][q]["verdict"] == "out_of_domain"
