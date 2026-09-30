"""Frontend export tests — LaTeX/BibTeX escaping, CSV round-trip,
collision-safe cite keys, no undefined/null leaks. Compiles
frontend/lib/exports.ts and runs a Node harness."""

from __future__ import annotations

import csv
import io
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
const {
  escapeLatex, citeKey, dedupeCiteKeys, paperToBibtex, papersToBibtex,
  csvCell, toCsv,
} = require("./exports.js");

const NASTY = [
  // Colons, math, non-ASCII, missing fields
  { paper_id: "openalex:W1", wid: "W1",
    title: "50 %: the LaTeX & Bib_TeX ~test — colon: math $x^2$",
    year: 2024, doi: "10.1234/abcd", venue: "JMLR",
    authors: ["Éloïse Müller", "Zoë O'Neill"] },
  // Same first-author family + year — should trigger dedupe suffix
  { paper_id: "openalex:W2", wid: "W2", title: "Second by Müller",
    year: 2024, doi: null, venue: null, authors: ["Éloïse Müller"] },
  // Missing everything except id
  { paper_id: "openalex:W3", wid: "W3", title: null, year: null,
    doi: null, venue: null, authors: null },
  // Undefined-shaped values
  { paper_id: "openalex:W4", wid: "W4",
    title: "Ok", year: "undefined", doi: "null", venue: "" },
];

const csvRows = NASTY.map((p) => [
  p.paper_id, p.title ?? "", p.year ?? "", p.doi ?? "",
  "one-line, with \"quotes\" and, commas", "genuine",
]);
const csv = toCsv(
  ["paper_id", "title", "year", "doi", "short_text", "verdict"], csvRows,
);
const bib = papersToBibtex(NASTY);
const keys = dedupeCiteKeys(NASTY);

const escaped = escapeLatex("100 % & { } _ $x^2$ ~foo #hash \\bar");

process.stdout.write(JSON.stringify({
  bib, csv, keys, escaped,
  singleBib: paperToBibtex(NASTY[0], "sample2024"),
}));
"""


@pytest.fixture(scope="module")
def harness_out():
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp)
        tsc = FRONTEND / "node_modules" / ".bin" / "tsc"
        subprocess.run(
            [str(tsc), "lib/exports.ts", "--outDir", str(out),
             "--module", "commonjs", "--target", "es2020",
             "--moduleResolution", "node", "--skipLibCheck"],
            cwd=FRONTEND, check=True, capture_output=True, timeout=180,
        )
        (out / "harness.js").write_text(HARNESS)
        proc = subprocess.run(
            ["node", "harness.js"], cwd=out, check=True,
            capture_output=True, text=True, timeout=60,
        )
        return json.loads(proc.stdout)


def test_latex_escapes_the_dangerous_characters(harness_out):
    e = harness_out["escaped"]
    assert "\\%" in e
    assert "\\&" in e
    assert "\\{" in e and "\\}" in e
    assert "\\_" in e
    assert "\\$" in e
    assert "\\#" in e
    assert "\\textasciitilde{}" in e
    assert "\\textasciicircum{}" in e
    assert "\\textbackslash{}" in e


def test_bibtex_never_emits_undefined_or_null_strings(harness_out):
    bib = harness_out["bib"]
    assert "undefined" not in bib.lower()
    assert "= {null}" not in bib
    # And single-entry
    assert "undefined" not in harness_out["singleBib"].lower()


def test_bibtex_escapes_nasty_title(harness_out):
    bib = harness_out["bib"]
    # LaTeX-hostile characters must be escaped inside the title
    assert "\\%" in bib and "\\&" in bib
    assert "\\_" in bib
    assert "\\$" in bib
    # Non-ASCII passes through unescaped
    assert "Éloïse Müller" in bib


def test_cite_keys_collision_safe(harness_out):
    keys = harness_out["keys"]
    # First two both mueller/2024 → second gets an 'a' suffix
    assert keys[0] == "mueller2024"
    assert keys[1] == "mueller2024a"
    # Missing year still yields a safe key
    for k in keys:
        assert "undefined" not in k.lower()
        assert "null" not in k.lower()
        assert "NaN" not in k


def test_csv_round_trips_via_parser(harness_out):
    csv_text = harness_out["csv"]
    reader = csv.reader(io.StringIO(csv_text))
    rows = list(reader)
    header = rows[0]
    body = rows[1:]
    assert header == ["paper_id", "title", "year", "doi", "short_text", "verdict"]
    # Nasty title with colons + math + non-ASCII preserved exactly
    assert body[0][1] == "50 %: the LaTeX & Bib_TeX ~test — colon: math $x^2$"
    # Quotes/commas in short_text survived
    assert body[0][4] == 'one-line, with "quotes" and, commas'
    # No literal "undefined"/"null" leaks
    for row in body:
        for cell in row:
            assert cell not in ("undefined", "null")


def test_csv_line_ending_is_rfc4180(harness_out):
    csv_text = harness_out["csv"]
    # RFC 4180 says CRLF between records.
    assert "\r\n" in csv_text
