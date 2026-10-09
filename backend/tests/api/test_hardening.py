"""Curious-visitor hardening (iteration 'final', Part 3). Source- and
data-level checks; browser checks live in tools/qa/hunt.py."""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
FE = REPO / "frontend"
NODE = shutil.which("node")
SRC = [p for p in (FE / "app").rglob("*.tsx")] + [p for p in (FE / "lib").rglob("*.ts")]


def _node(module: str, expr: str):
    script = (f"import * as M from {json.dumps((FE / 'lib' / module).as_uri())};"
              f"console.log(JSON.stringify({expr}));")
    r = subprocess.run([NODE, "--experimental-strip-types", "--no-warnings", "--input-type=module",
                        "-e", script], capture_output=True, text=True, check=True)
    return json.loads(r.stdout)


# ---- raw HTML, links, runtime network ------------------------------------

def test_only_the_static_theme_script_uses_raw_html():
    hits = [(p.name, l.strip()[:80]) for p in SRC for l in p.read_text().splitlines()
            if re.search(r"dangerouslySetInnerHTML|innerHTML\s*=|insertAdjacentHTML|document\.write", l)]
    assert hits == [("layout.tsx", "<script dangerouslySetInnerHTML={{ __html: themeScript }} />")], hits


def test_every_new_tab_link_has_noopener():
    for p in SRC:
        for l in p.read_text().splitlines():
            if 'target="_blank"' in l:
                assert "noopener" in l, (p.name, l.strip())


def test_no_runtime_call_to_paid_or_rate_limited_apis():
    """The site is static: no OpenAlex, Gemini, Semantic Scholar or other API
    host is ever contacted from the browser. /api/preflight exists only for
    the local app and is reached only in developer mode."""
    bad = []
    for p in SRC:
        t = p.read_text()
        for host in ("openalex.org/", "generativelanguage", "googleapis", "semanticscholar",
                     "api.anthropic", "unpaywall.org/", "europepmc.org/"):
            for m in re.finditer(rf"fetch\([^)]*{re.escape(host)}", t):
                bad.append((p.name, host))
        if re.search(r"fetch\(`?/api/preflight", t):
            assert p.name == "Ask.tsx" and "if (!dev ||" in t, p.name
    assert not bad, bad


# ---- quotes and claims ----------------------------------------------------

def test_open_questions_are_verbatim_quotes_with_their_paper():
    n = 0
    for f in (FE / "public" / "data").rglob("opportunity/*.json"):
        c = json.loads(f.read_text())
        if c.get("scorer") != "orphaned_future_work":
            continue
        n += 1
        fw = [e["text"] for e in c["evidence_trail"] if e["kind"] == "future_work"]
        core = c["consumer"]["headline"].rstrip("…").strip()
        assert fw and core[1:] in " ".join(fw[0].split()), f.name
        assert c.get("supporting_papers"), f.name
    assert n > 0


def test_no_claim_of_automatic_growth_until_it_runs():
    """Public copy may mention weekly growth only once the growth workflow
    has passed its end-to-end test (marker written by tools/grow/e2e_mock.py
    on a full pass), and must then say it from data, not promise it."""
    marker = REPO / "docs" / "releases" / "growth-e2e-passed.json"
    text = " ".join(p.read_text() for p in (FE / "app").rglob("*.tsx"))
    text += (FE / "public" / "data" / "language.json").read_text()
    denial = "do not update themselves"                 # the honest statement before growth
    claims = re.findall(r"(?i)\b(week(?:ly)?|every monday|updates? (?:it|them)sel(?:f|ves)|"
                        r"automatically (?:updated|refreshed))\b", text.replace(denial, ""))
    if not marker.exists():
        assert not claims, claims
    else:
        m = json.loads(marker.read_text())
        assert m["full"] and m["failed"] == 0, m
        assert "do not update themselves" not in text


# ---- query hygiene and safety rules (real TS modules) ---------------------

pytestmark = pytest.mark.skipif(NODE is None, reason="node not installed")


def test_clean_query_strips_and_caps():
    r = _node("query.ts", "["
              "M.cleanQuery('a\\u0000b\\u200bc\\u202ed  e '),"
              "M.cleanQuery('x'.repeat(10000)).length,"
              "M.echoQuery('y'.repeat(500)).length,"
              "M.cleanQuery('<script>alert(1)</script>')]")
    assert r[0] == "abcd e "
    assert r[1] == 200 and r[2] == 80
    assert r[3] == "<script>alert(1)</script>"   # kept as text; React escapes it


ADVICE = ["should I eat red meat", "is alcohol safe", "how much alcohol is healthy",
          "should we stop eating eggs", "is red meat bad for me", "how many drinks per day is ok",
          "can i eat processed meat", "what is a safe amount of sodium", "is coffee good for my heart",
          "recommended diet plan to lose weight"]


def test_advice_queries_are_recognised():
    r = _node("safety.ts", "[" + ",".join(f"M.adviceLike({json.dumps(q)})" for q in ADVICE) + "]")
    assert all(r), list(zip(ADVICE, r))


def test_research_queries_are_not_advice():
    qs = ["alcohol and stroke", "red meat mortality", "sodium reduction trials", "fairness metrics"]
    r = _node("safety.ts", "[" + ",".join(f"M.adviceLike({json.dumps(q)})" for q in qs) + "]")
    assert not any(r), list(zip(qs, r))


def test_panel_blocklist():
    blocked = ["how to kill myself", "porn videos", "Jane Doe", "suicide methods"]
    allowed = ["quantum computing", "soil microbiome", "melanoma treatment"]
    r = _node("safety.ts", "[" + ",".join(f"M.panelBlocked({json.dumps(q)})" for q in blocked + allowed) + "]")
    assert r[:len(blocked)] == [True] * len(blocked), r
    assert r[len(blocked):] == [False] * len(allowed), r


def test_prototype_words_do_not_break_search():
    """Words that are Object.prototype keys must be ordinary unknown words."""
    idx = (FE / "public" / "data" / "library" / "diet-and-mortality" / "search-index.json").as_uri()
    script = (f"import {{ search }} from {json.dumps((FE / 'lib' / 'search.ts').as_uri())};"
              f"import fs from 'fs'; import {{ fileURLToPath }} from 'url';"
              f"const idx = JSON.parse(fs.readFileSync(fileURLToPath({json.dumps(idx)}), 'utf8'));"
              "const out = ['constructor', '__proto__', 'toString valueOf', \"{{constructor.constructor('x')()}}\","
              " 'hasOwnProperty'].map((q) => search(idx, q, 24, {prefixLast: true}).verdict);"
              "out.push(search(idx, 'alcohol', 24, {prefixLast: true}).verdict);"
              "console.log(JSON.stringify(out));")
    r = subprocess.run([NODE, "--experimental-strip-types", "--no-warnings", "--input-type=module",
                        "-e", script], capture_output=True, text=True, check=True)
    v = json.loads(r.stdout)
    assert v[-1] == "in_domain" and all(x in ("out_of_domain", "typing", "empty", "borderline") for x in v[:-1]), v


def test_health_adjacent_flag_is_declared_and_shipped():
    reg = json.loads((REPO / "data" / "library_registry.json").read_text())["libraries"]
    for l in reg:
        assert isinstance(l.get("health_adjacent"), bool), l["slug"]
        if l["health_adjacent"]:
            assert l.get("not_advice_note"), l["slug"]     # flagged libraries carry the note
    shipped = {l["slug"]: l for l in json.loads((FE / "public" / "data" / "libraries.json").read_text())["libraries"]}
    for l in reg:
        if l["slug"] in shipped:                           # built libraries inherit the flag
            assert shipped[l["slug"]]["health_adjacent"] == l["health_adjacent"], l["slug"]
    assert shipped["diet-and-mortality"]["health_adjacent"] and shipped["social-media-teen-mental-health"]["health_adjacent"]


def test_no_full_text_is_shipped_or_committed():
    """Standing rule: full text of papers is never published or committed.
    Public paper files carry no full-text field and no string anywhere near
    full-paper length; data/cache/fulltext is never tracked by git."""
    longest = 0
    for f in (FE / "public" / "data").rglob("paper/*.json"):
        d = json.loads(f.read_text())
        assert "fulltext" not in d and "full_text_body" not in d, f.name
        stack = [d]
        while stack:
            x = stack.pop()
            if isinstance(x, dict):
                stack.extend(x.values())
            elif isinstance(x, list):
                stack.extend(x)
            elif isinstance(x, str):
                longest = max(longest, len(x))
    assert longest < 15_000, f"a shipped string is {longest} characters long (full text?)"
    from backend.app.api.language import ABSTRACT_MAX, ABSTRACT_SHORTENED
    for f in (FE / "public" / "data").rglob("paper/*.json"):
        a = json.loads(f.read_text()).get("abstract") or ""
        assert len(a) <= ABSTRACT_MAX + len(ABSTRACT_SHORTENED), (f.name, len(a))
    tracked = subprocess.run(["git", "ls-files", "data/cache/fulltext"], cwd=REPO, capture_output=True,
                             text=True).stdout.strip()
    assert tracked == "", tracked[:200]
