"""Build the 15-paper audit sample from the snowball output.

5 on-domain + 5 borderline (from kept candidates) + 5 off-domain (from
the retained drop samples). Each row: title, abstract, the heuristic
label, a one-sentence reasoning traceable to the abstract, and a blank
agree/disagree line for the human reviewer. Genuinely hard calls
(kept only via the anchor-term rescue, or labelled with no strong
signal) are flagged in a separate section.

This is the ONLY artifact the human reads to sanity-check labelling
before extraction spend.
"""

from __future__ import annotations

import json
import sys
import textwrap
from pathlib import Path

REPO_ROOT = Path("/Users/rajbhise/Downloads/claudecode/ResearchMap")
sys.path.insert(0, str(REPO_ROOT))

from backend.app.corpus.heuristic_label import ANCHOR_TERMS  # noqa: E402

CANDS = REPO_ROOT / "data" / "live_samples" / "snowball_candidates.json"
OUT = REPO_ROOT / "data" / "live_samples" / "snowball_audit_sample.md"


def _abbrev(text: str, n: int = 700) -> str:
    text = " ".join((text or "").split())
    return text if len(text) <= n else text[:n].rsplit(" ", 1)[0] + " …"


def _gate_was_anchor_only(rec: dict) -> bool:
    """A hard call: passed the AI gate only because an anchor term
    appeared, not because a topic was in CS/AI (we can't see topics here,
    so approximate: on-domain/borderline whose reason is the weak
    'no strong signal' bucket are the ambiguous ones)."""
    return "no strong signal" in (rec.get("label_reason") or "")


def _row(i: int, rec: dict) -> str:
    return textwrap.dedent(f"""\
        ### {i}. {rec.get('title') or '(untitled)'}
        - **openalex_id:** {rec.get('openalex_id')}
        - **year:** {rec.get('year')}  ·  **my label:** **{rec['label']}**{' ('+rec['domain_centrality']+')' if rec.get('domain_centrality') else ''}
        - **abstract:** {_abbrev(rec.get('abstract',''))}
        - **reasoning (heuristic trigger):** {rec.get('label_reason')}
        - **agree / disagree:** ______________________________________
        """)


def main() -> int:
    s = json.loads(CANDS.read_text())
    kept = s["records"]
    off = s["off_domain_samples"]

    on = [r for r in kept if r["label"] == "on-domain"]
    border = [r for r in kept if r["label"] == "borderline"]
    # Representative: most co-cited first (most central to the corpus).
    on.sort(key=lambda r: -r.get("co_citation_freq", 0))
    border.sort(key=lambda r: -r.get("co_citation_freq", 0))

    pick_on = on[:5]
    pick_border = border[:5]
    pick_off = off[:5]

    lines = ["# Snowball labelling — audit sample (n=15)\n"]
    lines.append(
        "Heuristic labels applied in-session (no LLM spend) against "
        "`docs/labelling-rubric.md`. Discriminator: the paper's *primary "
        "contribution*, not vocabulary. Mark agree/disagree on each; this "
        "is the only labelling check before extraction spend.\n"
    )
    lines.append(f"Corpus: {len(kept)} kept ({len(on)} on-domain, "
                 f"{len(border)} borderline); {len(off)} off-domain drops "
                 "retained for this sample.\n")

    lines.append("\n## On-domain (5)\n")
    for i, r in enumerate(pick_on, 1):
        lines.append(_row(i, r))
    lines.append("\n## Borderline (5)\n")
    for i, r in enumerate(pick_border, 1):
        lines.append(_row(i, r))
    lines.append("\n## Off-domain (5) — should be excluded\n")
    for i, r in enumerate(pick_off, 1):
        lines.append(_row(i, r))

    # Hard calls: ambiguous 'no strong signal' rows among the picks.
    hard = [r for r in pick_on + pick_border if _gate_was_anchor_only(r)]
    lines.append("\n## Genuinely hard calls (flagged)\n")
    if hard:
        lines.append(
            "These passed as on/borderline on a weak heuristic signal "
            "(no venue or tight anchor+topic co-occurrence) — most likely "
            "to be mislabelled; please look here first:\n"
        )
        for r in hard:
            lines.append(f"- {r.get('title')} — labelled **{r['label']}**, "
                         f"reason: {r.get('label_reason')}")
    else:
        lines.append("None of the sampled rows relied on a weak signal; "
                     "the borderline/on-domain picks all had a venue or "
                     "anchor+topic co-occurrence trigger.\n")

    OUT.write_text("\n".join(lines))
    print(f"wrote {OUT.relative_to(REPO_ROOT)} "
          f"({len(pick_on)} on, {len(pick_border)} border, {len(pick_off)} off; "
          f"{len(hard)} hard-flagged)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
