"""Personal-distress and advice handling for health-adjacent libraries
(lib/safety.ts, used by the search box). 15 queries per flagged library:
distress -> one calm message, no results, no library offer; advice -> results
lead with the research-not-advice note; research questions on the same
subjects -> answered normally. Libraries flagged later get the generic set."""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
FE = REPO / "frontend"
NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(NODE is None, reason="node not installed")

# (query, expected) — expected in {"distress", "advice", "research"}
SETS = {
    "diet-and-mortality": [
        ("i feel hopeless about my weight", "distress"), ("i'm so depressed i can't eat", "distress"),
        ("i can't cope anymore", "distress"), ("i want to die", "distress"),
        ("how to kill myself with pills", "distress"), ("i keep hurting myself", "distress"),
        ("should i stop eating red meat", "advice"), ("is coffee safe for me", "advice"),
        ("how much alcohol is ok per day", "advice"), ("is red meat bad for my heart", "advice"),
        ("recommended diet plan to lose weight", "advice"), ("should my kids drink juice", "advice"),
        ("red meat and stroke risk", "research"), ("alcohol and all-cause mortality", "research"),
        ("mediterranean diet trials", "research"),
    ],
    "social-media-teen-mental-health": [
        ("i'm depressed because of instagram", "distress"), ("i feel hopeless and alone", "distress"),
        ("i can't cope with school", "distress"), ("i think about self-harm every day", "distress"),
        ("i want to end my life", "distress"), ("my life is worthless", "distress"),
        ("should my teen have a smartphone", "advice"), ("is screen time bad for my kid", "advice"),
        ("how much screen time is ok for a 13 year old", "advice"),
        ("should i take my daughter's phone away", "advice"), ("is tiktok safe for kids", "advice"),
        ("should we ban social media for our son", "advice"),
        ("social media and adolescent depression", "research"),
        ("self-harm rates and social media use", "research"), ("suicide rates among adolescents", "research"),
    ],
}
GENERIC = [
    ("i can't cope", "distress"), ("i feel so hopeless", "distress"), ("i want to die", "distress"),
    ("i've been cutting myself", "distress"), ("i'm suicidal", "distress"), ("better off dead", "distress"),
    ("should i be worried", "advice"), ("is this safe for me", "advice"), ("should my child do this", "advice"),
    ("what is a safe amount", "advice"), ("is it bad for my health", "advice"), ("should we stop", "advice"),
    ("prevalence in adolescents", "research"), ("randomised trial results", "research"),
    ("systematic review and meta-analysis", "research"),
]
FLAGGED = [l["slug"] for l in json.loads((FE / "public" / "data" / "libraries.json").read_text())["libraries"]
           if l.get("health_adjacent")]


def _classify(queries: list[str]) -> list[tuple[bool, bool]]:
    script = (f"import * as M from {json.dumps((FE / 'lib' / 'safety.ts').as_uri())};"
              f"const qs = {json.dumps(queries)};"
              "console.log(JSON.stringify(qs.map((q) => [M.distress(q), M.adviceLike(q)])));")
    r = subprocess.run([NODE, "--experimental-strip-types", "--no-warnings", "--input-type=module", "-e", script],
                       capture_output=True, text=True, check=True)
    return [tuple(x) for x in json.loads(r.stdout)]


def test_flagged_libraries_are_covered():
    assert {"diet-and-mortality", "social-media-teen-mental-health"} <= set(FLAGGED)
    for s in FLAGGED:
        assert len(SETS.get(s, GENERIC)) == 15, s


@pytest.mark.parametrize("slug", FLAGGED)
def test_fifteen_queries_per_flagged_library(slug):
    cases = SETS.get(slug, GENERIC)
    got = _classify([q for q, _e in cases])
    for (q, want), (is_distress, is_advice) in zip(cases, got):
        if want == "distress":
            assert is_distress, (slug, q)
        elif want == "advice":
            assert is_advice and not is_distress, (slug, q)
        else:
            assert not is_distress, (slug, q)      # research is answered, never treated as distress


def test_distress_message_names_a_real_helpline_and_hides_everything_else():
    ask = (FE / "app" / "components" / "Ask.tsx").read_text()
    safety = (FE / "lib" / "safety.ts").read_text()
    assert 'HELPLINE_URL = "https://findahelpline.com"' in safety
    assert "{distressed && (" in ask
    assert '{!distressed && result?.verdict === "out_of_domain"' in ask      # no library offer
    assert "{!distressed && showResults && (" in ask                         # no research results
    assert "This is research literature, not medical or parenting advice." in ask
