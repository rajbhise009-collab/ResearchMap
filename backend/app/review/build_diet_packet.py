"""Assemble the blind expert-review packet for the diet contradictions.

Output goes to docs/review/diet-contradictions/. 12 items:
  - 5 audit-genuine contradictions
  - 1 audit-artifact contradiction (regime-conflation)
  - 6 control pairs the classifier labelled `supports` or `none` on
    the same exposure/outcome topics
Shuffled with a fixed seed so the packet is reproducible; the neutral
IDs (`item-01` … `item-12`) reveal nothing about which pairs are
flagged vs controls.

Files produced:
  packet.md              — the reviewer's read
  packet.html            — printable version of the same
  response_form.csv      — one row per item, empty response columns
  answer_key.json        — DO NOT SHARE — reveals verdict per item
  recruitment-message.md — recruitment note with placeholders

Never sends anything anywhere. Run with:
    python -m backend.app.review.build_diet_packet
"""

from __future__ import annotations

import csv
import io
import json
import random
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))

from backend.app.api.contradiction_audit import (  # noqa: E402
    attach_verdicts, _norm,
)

DIET_REASONING = REPO_ROOT / "data" / "domains" / "diet-and-mortality" / "reasoning"
DIET_PRELABEL = REPO_ROOT / "data" / "domains" / "diet-and-mortality" / "prelabelled.json"
OUT_DIR = REPO_ROOT / "docs" / "review" / "diet-contradictions"

SEED = 20260930
N_CONTROLS = 6

RESPONSE_OPTIONS = [
    ("genuine",        "Genuine disagreement — comparable people, exposure, outcome"),
    ("conditions",     "Differ in conditions — not a real conflict"),
    ("consistent",     "Actually consistent"),
    ("cant_tell",      "Can't tell from what's shown"),
]


def _load_papers_index() -> dict[str, dict]:
    """paper_id → {title, year, doi, venue, abstract} from the prelabel."""
    d = json.loads(DIET_PRELABEL.read_text())
    return {f"openalex:{e['wid']}": e for e in d["entries"]}


def _first_para(abstract: str, limit: int = 300) -> str:
    """First ~300 chars of an abstract, clean."""
    if not abstract:
        return "(no abstract available)"
    txt = " ".join(abstract.split())
    if len(txt) <= limit:
        return txt
    cut = txt[:limit].rsplit(" ", 1)[0]
    return cut.rstrip(".,;:") + "…"


def build_items() -> list[dict]:
    """Return the 12-item list (5 genuine + 1 artifact + 6 controls),
    unshuffled — the caller shuffles."""
    papers = _load_papers_index()
    raw_contra = json.loads((DIET_REASONING / "contradictions.json").read_text())["items"]
    audited = attach_verdicts("diet-and-mortality", raw_contra)
    genuine = [c for c in audited if c["audit"]["verdict"] == "genuine"]
    artifact = [c for c in audited if c["audit"]["verdict"] == "artifact"]
    assert len(genuine) == 5, f"expected 5 genuine, got {len(genuine)}"
    assert len(artifact) == 1, f"expected 1 artifact, got {len(artifact)}"
    controls = _pick_controls(papers, target=N_CONTROLS)
    assert len(controls) == N_CONTROLS, (
        f"expected {N_CONTROLS} controls, got {len(controls)}"
    )
    items = []
    for c in genuine:
        items.append(_pair_to_item(c, papers, provenance="genuine"))
    for c in artifact:
        items.append(_pair_to_item(c, papers, provenance="artifact"))
    for c in controls:
        items.append(_pair_to_item(c, papers, provenance="control"))
    return items


# Same exposure/outcome vocabulary that seeded the diet snowball.
EXPOSURE_TERMS = (
    "red meat", "processed meat", "alcohol", "saturated fat", "trans fat",
    "sugar-sweetened", "mediterranean diet", "vegetarian", "vegan diet",
    "plant-based", "whole grain", "dietary pattern", "ketogenic",
    "low-carbohydrate", "high-protein", "dietary fibre", "dietary fiber",
    "sodium",
)
OUTCOME_TERMS = (
    "mortality", "cardiovascular", "coronary heart disease",
    "stroke", "type 2 diabetes", "cancer", "hypertension", "metabolic syndrome",
)


def _shares_exposure_and_outcome(a_text: str, b_text: str) -> bool:
    la, lb = (a_text or "").lower(), (b_text or "").lower()
    def _any(text, terms):
        return any(t in text for t in terms)
    return (
        _any(la, EXPOSURE_TERMS) and _any(lb, EXPOSURE_TERMS)
        and _any(la, OUTCOME_TERMS) and _any(lb, OUTCOME_TERMS)
    )


def _pick_controls(papers: dict[str, dict], *, target: int) -> list[dict]:
    """Pick control pairs from supports.json + nones.json where both
    claims share an exposure AND an outcome (same-topic pairs). Uses
    seeded random to be stable across runs."""
    pool: list[dict] = []
    for fname in ("supports.json", "nones.json"):
        p = DIET_REASONING / fname
        if not p.exists():
            continue
        d = json.loads(p.read_text())
        for it in d.get("items", []):
            if _shares_exposure_and_outcome(it.get("a_text", ""),
                                              it.get("b_text", "")):
                pool.append(it)
    rng = random.Random(SEED + 1)
    rng.shuffle(pool)
    return pool[:target]


def _pair_to_item(pair: dict, papers: dict[str, dict], *,
                    provenance: str) -> dict:
    a_pid, b_pid = pair["a_paper_id"], pair["b_paper_id"]
    A, B = papers.get(a_pid, {}), papers.get(b_pid, {})
    return {
        "provenance": provenance,
        "a_paper_id": a_pid, "b_paper_id": b_pid,
        "a_text": pair.get("a_text", ""),
        "b_text": pair.get("b_text", ""),
        "a_meta": {
            "title": A.get("title"), "year": A.get("year"),
            "doi": A.get("doi"), "venue": A.get("venue"),
            "abstract_head": _first_para(A.get("abstract") or ""),
        },
        "b_meta": {
            "title": B.get("title"), "year": B.get("year"),
            "doi": B.get("doi"), "venue": B.get("venue"),
            "abstract_head": _first_para(B.get("abstract") or ""),
        },
        "audit_verdict": (pair.get("audit") or {}).get("verdict"),
        "audit_reason": (pair.get("audit") or {}).get("reason"),
    }


def _md_item(idx: int, it: dict) -> str:
    A, B = it["a_meta"], it["b_meta"]
    def _doi_line(m):
        return f" · doi:{m['doi']}" if m.get("doi") else ""
    def _year(m):
        return f" ({m.get('year')})" if m.get("year") else ""
    out = [
        f"## Item {idx:02d}",
        "",
        "**Claim A** (from the paper below): "
        f"“{it['a_text']}”",
        "",
        f"- *{A.get('title') or '(untitled)'}*"
        f"{_year(A)} — {A.get('venue') or '(no venue listed)'}"
        f"{_doi_line(A)}",
        f"- Abstract (first ~300 chars): {A.get('abstract_head')}",
        "",
        "**Claim B** (from the paper below): "
        f"“{it['b_text']}”",
        "",
        f"- *{B.get('title') or '(untitled)'}*"
        f"{_year(B)} — {B.get('venue') or '(no venue listed)'}"
        f"{_doi_line(B)}",
        f"- Abstract (first ~300 chars): {B.get('abstract_head')}",
        "",
        "**Do these findings genuinely conflict?** "
        "(comparable people, exposure, outcome)",
        "",
        *[f"- [ ] {label}" for _slug, label in RESPONSE_OPTIONS],
        "",
        "One-line reason (optional): ______________________________________",
        "",
        "---",
        "",
    ]
    return "\n".join(out)


def _md_packet(items: list[dict]) -> str:
    lines = [
        "# ResearchMap — diet-and-mortality contradiction review",
        "",
        "**Target time:** 30 minutes or less. **What we're asking:** for "
        "each of the 12 item pairs below, does the pair genuinely conflict "
        "(same kind of people, exposure, outcome, and comparable study "
        "design), or is the apparent conflict an artifact of different "
        "conditions?",
        "",
        "## What ResearchMap is",
        "",
        "ResearchMap is a prototype tool that reads a small collection of "
        "papers on one subject and flags pairs whose primary findings look "
        "like they disagree. It is not peer review, not clinical guidance, "
        "and not a settled resolution of anything — it is a discovery aid "
        "that shortlists candidate disagreements a human still has to check.",
        "",
        "The 12 items below are a mix of pairs the tool flagged as "
        "contradictions AND controls (pairs it marked as consistent or "
        "orthogonal on the same topics). They are shuffled — item order "
        "reveals nothing.",
        "",
        "## How to respond",
        "",
        "Fill the `response_form.csv` template with one row per item. Or "
        "reply inline in this markdown. Either way, please note whether "
        "you want acknowledgement by name in the write-up, or prefer to "
        "stay anonymous.",
        "",
        "---",
        "",
    ]
    for i, it in enumerate(items, 1):
        lines.append(_md_item(i, it))
    return "\n".join(lines)


def _html_packet(md: str) -> str:
    """Very small MD→HTML: enough for a printable review page. We keep it
    hand-rolled to avoid pulling in a markdown library for one file."""
    def esc(s):
        return (s.replace("&", "&amp;").replace("<", "&lt;")
                 .replace(">", "&gt;"))
    body_lines = []
    in_list = False
    for ln in md.splitlines():
        if ln.startswith("## "):
            if in_list: body_lines.append("</ul>"); in_list = False
            body_lines.append(f"<h2>{esc(ln[3:])}</h2>")
        elif ln.startswith("# "):
            body_lines.append(f"<h1>{esc(ln[2:])}</h1>")
        elif ln.startswith("- [ ] "):
            if not in_list: body_lines.append("<ul class='choices'>"); in_list = True
            body_lines.append(f"<li>☐ {esc(ln[6:])}</li>")
        elif ln.startswith("- "):
            if not in_list: body_lines.append("<ul>"); in_list = True
            body_lines.append(f"<li>{esc(ln[2:])}</li>")
        elif ln == "---":
            if in_list: body_lines.append("</ul>"); in_list = False
            body_lines.append("<hr/>")
        elif ln.strip() == "":
            if in_list: body_lines.append("</ul>"); in_list = False
            body_lines.append("")
        else:
            if in_list: body_lines.append("</ul>"); in_list = False
            body_lines.append(f"<p>{esc(ln)}</p>")
    if in_list:
        body_lines.append("</ul>")
    body = "\n".join(body_lines)
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<title>ResearchMap — diet contradictions review</title>
<style>
  body {{ font: 15px/1.55 Charter, Georgia, serif; max-width: 720px;
           margin: 2em auto; padding: 0 1em; color: #22201d; }}
  h1 {{ font-size: 1.6rem; }} h2 {{ font-size: 1.15rem; margin-top: 2em; }}
  ul.choices {{ list-style: none; padding-left: 0; }}
  ul.choices li {{ margin: 0.2em 0; }}
  hr {{ margin: 2em 0; border: 0; border-top: 1px dashed #ccc; }}
  p {{ margin: 0.5em 0; }}
  @media print {{ h2 {{ page-break-before: auto; }} }}
</style></head>
<body>
{body}
</body></html>
"""


def _response_form_csv(items: list[dict]) -> str:
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\r\n")
    w.writerow(["item_id", "verdict",
                 "one_line_reason", "reviewer_name_or_blank_for_anon"])
    for i, _ in enumerate(items, 1):
        w.writerow([f"item-{i:02d}", "", "", ""])
    return buf.getvalue()


def _answer_key(items: list[dict]) -> dict:
    return {
        "DO_NOT_SHARE_WITH_REVIEWERS": True,
        "seed": SEED,
        "items": [
            {
                "item_id": f"item-{i:02d}",
                "provenance": it["provenance"],
                "audit_verdict": it["audit_verdict"],
                "audit_reason": it["audit_reason"],
                "a_paper_id": it["a_paper_id"],
                "b_paper_id": it["b_paper_id"],
            }
            for i, it in enumerate(items, 1)
        ],
    }


def _recruitment_message() -> str:
    return (
        "Subject: 30-minute blind review of AI-flagged research disagreements\n\n"
        "Hi [FIRST_NAME],\n\n"
        "I've been building a prototype tool that reads a collection of "
        "papers on one subject and flags pairs whose primary findings "
        "look like they disagree. It's not peer review, not clinical "
        "guidance — it's a discovery aid whose output still needs a "
        "human to check.\n\n"
        "I have 12 flagged pairs from a small library on diet and "
        "mortality (the classic red-meat / alcohol / saturated-fat "
        "arguments). Six are pairs the tool flagged as contradictions; "
        "six are controls the tool marked as consistent or orthogonal on "
        "the same topics. You wouldn't be told which is which.\n\n"
        "The ask: for each pair, tell me whether the two findings "
        "genuinely conflict (comparable people, exposure, outcome, and "
        "study design) or whether the apparent conflict is an artifact "
        "of different conditions. Target time is 30 minutes or less; "
        "the packet is one printable page per pair, and there's a small "
        "CSV response form.\n\n"
        "If you'd like to see the packet, reply and I'll send it as an "
        "attachment. You can respond by name or anonymously — please "
        "say which you prefer.\n\n"
        "[YOUR_NAME]\n"
        "[YOUR_AFFILIATION]\n"
    )


def build_packet(out_dir: Path = OUT_DIR) -> dict:
    items = build_items()
    rng = random.Random(SEED)
    rng.shuffle(items)
    out_dir.mkdir(parents=True, exist_ok=True)
    md = _md_packet(items)
    (out_dir / "packet.md").write_text(md)
    (out_dir / "packet.html").write_text(_html_packet(md))
    (out_dir / "response_form.csv").write_text(_response_form_csv(items))
    key_dir = out_dir / "_answer_key_DO_NOT_SHARE"
    key_dir.mkdir(exist_ok=True)
    (key_dir / "answer_key.json").write_text(
        json.dumps(_answer_key(items), indent=2)
    )
    (key_dir / "README.md").write_text(
        "# DO NOT SHARE — answer key for the diet review packet\n\n"
        "This directory contains the mapping from item IDs to the audit's\n"
        "own verdicts. Sharing it with a reviewer defeats the blind "
        "review.\n\n"
        "The packet.md / packet.html / response_form.csv one directory up\n"
        "are safe to send.\n"
    )
    (out_dir / "recruitment-message.md").write_text(_recruitment_message())
    return {
        "n_items": len(items),
        "n_genuine": sum(1 for i in items if i["provenance"] == "genuine"),
        "n_artifact": sum(1 for i in items if i["provenance"] == "artifact"),
        "n_control": sum(1 for i in items if i["provenance"] == "control"),
        "seed": SEED,
        "out_dir": str(out_dir.relative_to(REPO_ROOT)),
    }


def main() -> int:
    r = build_packet()
    print(json.dumps(r, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
