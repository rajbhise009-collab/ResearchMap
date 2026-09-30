"""Tests for the search-query scrubber. Unwired but tested — the
Vercel-Pro custom-events wiring would use this exact function."""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
FRONTEND = REPO / "frontend"

pytestmark = pytest.mark.skipif(
    not shutil.which("node") or not (FRONTEND / "node_modules" / "typescript").exists(),
    reason="needs node and the frontend's TypeScript compiler",
)

HARNESS = r"""
const { scrubQuery, shouldLog } = require("./analytics-scrub.js");

const cases = [
  // (label, input, expected: string | null)
  ["ordinary refused query", "how do I bake sourdough", "how do I bake sourdough"],
  ["email fragment dropped", "email me at raj@example.com about X", null],
  ["ambient @ dropped too", "@handle mentioned this", null],
  ["long digit run dropped (paper id-like)", "why W2109401990 vs the other", null],
  ["phone number dropped", "contact 9876543210 for details", null],
  ["short number kept", "aged 65 and above", "aged 65 and above"],
  ["truncated to 80", "a".repeat(200), "a".repeat(80)],
  ["empty dropped", "", null],
  ["whitespace dropped", "     ", null],
  ["non-string dropped", 12345, null],
];

const results = cases.map(([label, input, expected]) => {
  const got = scrubQuery(input);
  return { label, input, expected, got, pass: got === expected };
});

const shouldLogCases = [
  ["borderline", true], ["out_of_domain", true],
  ["in_domain", false], ["empty", false],
];
const logResults = shouldLogCases.map(([v, exp]) => ({
  verdict: v, expected: exp, got: shouldLog(v), pass: shouldLog(v) === exp,
}));

process.stdout.write(JSON.stringify({ results, logResults }));
"""


@pytest.fixture(scope="module")
def harness_out():
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp)
        tsc = FRONTEND / "node_modules" / ".bin" / "tsc"
        subprocess.run(
            [str(tsc), "lib/analytics-scrub.ts", "--outDir", str(out),
             "--module", "commonjs", "--target", "es2020",
             "--moduleResolution", "node", "--skipLibCheck"],
            cwd=FRONTEND, check=True, capture_output=True, timeout=120,
        )
        (out / "harness.js").write_text(HARNESS)
        proc = subprocess.run(
            ["node", "harness.js"], cwd=out, check=True,
            capture_output=True, text=True, timeout=30,
        )
        return json.loads(proc.stdout)


def test_scrubber_cases_all_pass(harness_out):
    for r in harness_out["results"]:
        assert r["pass"], (r["label"], r["input"], r["got"], r["expected"])


def test_only_borderline_and_ood_would_be_logged(harness_out):
    for r in harness_out["logResults"]:
        assert r["pass"], r
