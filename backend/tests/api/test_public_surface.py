"""What the deployed site may serve.

Everything under frontend/public is copied into the static build
(frontend/out), and everything in frontend/out is served to anyone. This
test fails if build-time-only material reaches either: raw corpora and
scope files, the spend ledger and money config, pending batch files,
prompts, rubrics, review packets and answer keys, docs/review,
docs/proposals, source maps, or fields that only describe the pipeline.

Public by design (what the browser needs): the HTML pages, _next/static
(the compiled site, no source maps), icons and share images, robots.txt,
sitemap.xml, the web manifest, prefetch.js, and the per-library data files
the pages fetch (libraries, opportunities, opportunity/*, papers,
paper/*, stats, findings, language, search-index, site-facts,
validation, meta). See docs/public-surface.md.

frontend/out is checked when it exists (the publish gates build before
running the tests); frontend/public is always checked.
"""
from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
ROOTS = [p for p in (REPO / "frontend" / "public", REPO / "frontend" / "out") if p.is_dir()]

# a path segment that never belongs in the deployed site
FORBIDDEN_DIRS = {"docs", "review", "proposals", "rubrics", "domains", "cache", "grow", "config", "backend",
                  "tools", "scratch", "seed", "prompts", "_answer_key_DO_NOT_SHARE", ".git"}
# file names (lower case) that are build-time-only data
FORBIDDEN_NAMES = {"relationships.json", "money.json", "growth.json", "library_registry.json",
                   "queued_builds.json", "pending.json", "prelabelled.json", "spend_ledger.json",
                   "answer_key.json", "answer_key_v2.json", ".env", "claude.md", "progress.md"}
FORBIDDEN_PREFIXES = ("spend_ledger", "records", "scope", "rubric", "prompt", "answer_key", "packet", ".env")
FORBIDDEN_SUFFIXES = (".map", ".jsonl", ".npy", ".py", ".md", ".csv", ".ipynb", ".log")
# JSON keys that describe the pipeline or the money, never the content
FORBIDDEN_KEYS = (b'"prompt_hash"', b'"detector_model"', b'"account_total_inr"', b'"console_spent_inr"',
                  b'"proj_cost_inr"', b'"api_key"', b'"cap_inr"')
# tracked build-time-only sources: no deployed file may be a byte copy of one
PRIVATE_SOURCES = ("config/", "data/domains/", "data/grow/", "data/spend_ledger", "docs/review/",
                   "docs/proposals/", "docs/rubrics/", "backend/app/extraction/", "backend/app/review/")


def _deployed() -> list[tuple[Path, Path]]:
    return [(root, p) for root in ROOTS for p in root.rglob("*") if p.is_file()]


def test_there_is_something_to_check():
    assert ROOTS and _deployed()


def test_no_build_time_only_file_is_deployed():
    bad = []
    for root, p in _deployed():
        rel = p.relative_to(root)
        name = p.name.lower()
        if (set(rel.parts[:-1]) & FORBIDDEN_DIRS or name in FORBIDDEN_NAMES
                or name.startswith(FORBIDDEN_PREFIXES) or name.endswith(FORBIDDEN_SUFFIXES)):
            bad.append(f"{root.name}/{rel}")
    assert not bad, f"build-time-only files in the deployed site: {bad[:20]}"


def test_no_source_maps_and_no_map_comments():
    out = REPO / "frontend" / "out" / "_next"
    if not out.is_dir():
        pytest.skip("no build output (frontend/out); the publish gates build first")
    hits = [str(p.relative_to(out)) for p in out.rglob("*.js") if b"sourceMappingURL" in p.read_bytes()]
    assert not hits, hits[:10]


def test_deployed_json_carries_no_pipeline_or_money_fields():
    bad = []
    for root, p in _deployed():
        if p.suffix != ".json":
            continue
        raw = p.read_bytes()
        bad += [f"{root.name}/{p.relative_to(root)}: {k.decode()}" for k in FORBIDDEN_KEYS if k in raw]
    assert not bad, bad[:20]


def test_no_deployed_file_is_a_copy_of_a_private_source():
    tracked = subprocess.run(["git", "ls-files", "-z", "--", *PRIVATE_SOURCES], cwd=REPO, capture_output=True,
                             check=True).stdout.split(b"\0")
    private = {}
    for rel in filter(None, tracked):
        f = REPO / rel.decode()
        if f.is_file() and f.stat().st_size > 64:          # tiny files (e.g. "{}") match by accident
            private[hashlib.sha256(f.read_bytes()).hexdigest()] = rel.decode()
    assert private, "no private sources found to compare against"
    copies = []
    for root, p in _deployed():
        h = hashlib.sha256(p.read_bytes()).hexdigest()
        if h in private:
            copies.append(f"{root.name}/{p.relative_to(root)} == {private[h]}")
    assert not copies, copies[:20]


def test_the_rules_catch_what_they_should():
    """The checks above are only as good as their lists: each family of
    build-time-only file is caught by name or path."""
    for rel in ("data/library/x/relationships.json", "docs/review/packet.md", "data/spend_ledger.json",
                "_next/static/chunks/a.js.map", "data/domains/x/prelabelled.json", "config/money.json",
                "data/grow/queued_builds.json", "x/pending.json", "prompts/extract.txt", "rubrics/a.md",
                "docs/proposals/p.md", "scope.json", "records.slim.json", "x/answer_key.json"):
        parts = Path(rel).parts
        name = parts[-1].lower()
        assert (set(parts[:-1]) & FORBIDDEN_DIRS or name in FORBIDDEN_NAMES or name.startswith(FORBIDDEN_PREFIXES)
                or name.endswith(FORBIDDEN_SUFFIXES)), rel
    for rel in ("data/library/x/opportunities.json", "data/library/x/paper/W1.json", "og/default.png",
                "_next/static/chunks/a.js", "index.html", "robots.txt", "sitemap.xml", "prefetch.js"):
        parts = Path(rel).parts
        name = parts[-1].lower()
        assert not (set(parts[:-1]) & FORBIDDEN_DIRS or name in FORBIDDEN_NAMES
                    or name.startswith(FORBIDDEN_PREFIXES) or name.endswith(FORBIDDEN_SUFFIXES)), rel
