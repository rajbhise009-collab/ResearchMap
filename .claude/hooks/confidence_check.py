#!/usr/bin/env python3
"""PostToolUse check (.claude/settings.json): after an edit to the scoring
code (backend/app/reasoning, ranking, relationships), flag any read of a
`confidence` value that is not an Opportunity's own.

CLAUDE.md: Claim.confidence is an LLM self-assessment and MUST NOT feed any
score (docs/confidence-policy.md). Opportunities carry their own, code-made
`confidence` (o.confidence, opp.confidence, confidence=...), which is fine.

On a hit it returns decision "block" with the lines, so the edit is
reviewed at once. `scan(text)` is importable for tests and CI.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

SCORING_DIRS = ("backend/app/reasoning/", "backend/app/ranking/", "backend/app/relationships/")
# receivers that are Opportunities (code-made confidence): allowed
OPPORTUNITY = {"o", "opp", "op", "opportunity", "t[1]", "best", "card"}
ATTR = re.compile(r"([A-Za-z_][\w]*(?:\[[^\]]*\])?)\.confidence\b")
KEY = re.compile(r"""(?:\[\s*['"]confidence['"]\s*\]|\.get\(\s*['"]confidence['"]|getattr\([^)]*['"]confidence['"])""")


def _code_lines(text: str) -> dict[int, str]:
    """Each line with its strings and comments blanked out by the tokenizer
    (so docstrings that explain the rule never trip it), spacing intact. A
    string that is exactly "confidence" used as a key (["confidence"],
    .get("confidence"), getattr(x, "confidence")) is kept, so dict reads are
    still caught."""
    import io
    import tokenize
    lines = [list(ln) for ln in text.splitlines()]
    try:
        toks = list(tokenize.generate_tokens(io.StringIO(text).readline))
    except (tokenize.TokenError, IndentationError, SyntaxError):
        return {n: ln.split("#", 1)[0] for n, ln in enumerate(text.splitlines(), 1)}
    for i, t in enumerate(toks):
        if t.type not in (tokenize.STRING, tokenize.COMMENT):
            continue
        prev = toks[i - 1].string if i else ""
        if t.type == tokenize.STRING and t.string.strip("'\"") == "confidence" and prev in ("[", "(", ","):
            continue
        (r0, c0), (r1, c1) = t.start, t.end
        for r in range(r0, r1 + 1):
            if r - 1 >= len(lines):
                break
            a = c0 if r == r0 else 0
            b = c1 if r == r1 else len(lines[r - 1])
            for c in range(a, min(b, len(lines[r - 1]))):
                lines[r - 1][c] = " "
    return {n: "".join(ln) for n, ln in enumerate(lines, 1) if "".join(ln).strip()}


def scan(text: str) -> list[tuple[int, str]]:
    lines = text.splitlines()
    hits = []
    for n, code in sorted(_code_lines(text).items()):
        bad = [m.group(1) for m in ATTR.finditer(code) if m.group(1) not in OPPORTUNITY]
        if bad or KEY.search(code):
            hits.append((n, lines[n - 1].strip() if n <= len(lines) else code))
    return hits


def main() -> int:
    try:
        event = json.load(sys.stdin)
    except Exception:  # noqa: BLE001
        return 0
    ti = event.get("tool_input") or {}
    path = ti.get("file_path") or ""
    cwd = event.get("cwd") or ""
    rel = path[len(cwd) + 1:] if cwd and path.startswith(cwd + "/") else path
    if not (rel.endswith(".py") and rel.startswith(SCORING_DIRS)):
        return 0
    try:
        hits = scan(Path(path).read_text())
    except OSError:
        return 0
    if hits:
        lines = "\n".join(f"  {rel}:{n}: {t}" for n, t in hits[:10])
        print(json.dumps({"decision": "block", "reason":
            "This scoring file reads a `confidence` that is not an Opportunity's own. Claim.confidence is an "
            "LLM self-assessment and must never feed a score (CLAUDE.md, docs/confidence-policy.md). "
            "Remove it, or rename the receiver if it really is an Opportunity:\n" + lines}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
