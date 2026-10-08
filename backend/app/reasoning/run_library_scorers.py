"""Paid LLM stages for the multi-domain libraries' Phase-4 scorers.

  python -m backend.app.reasoning.run_library_scorers confirm --slug ml-fairness [--dry-run]
  python -m backend.app.reasoning.run_library_scorers fwmatch --slug diet-and-mortality [--dry-run]

confirm  — structural-hole leads (claim clustering, k = max(2, round(sqrt N)),
           the scaling study's correction) are LLM-confirmed with the SAME
           prompt and labels as LLM calibration
           (run_structural_confirm.PROMPT: substantive / trivial /
           not_addressing). At most 15 per library, highest score first.
fwmatch  — the two-stage future-work matcher: cosine shortlist (0.70, top 4
           later papers per item, as LLM calibration) then LLM classify with
           future_work_llm.PROMPT (addressed / partial / not_addressed).

Both are classification only. Batch API (50% price). Gate: projection x2
must fit the ledger's remaining ceiling (spend_gate.preflight, recorded).
Save-as-you-go: the batch id is saved on submit, so a restart re-collects
the same job instead of re-paying; results are billed to the ledger exactly
once (ledger_recorded flag) and written as soon as they return. After
collection, cost per call is compared with the projection; above 1.5x the
run reports OVERRUN and the caller stops later stages.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
import time
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))

from backend.app.config import get_settings  # noqa: E402
from backend.app.extraction import pricing  # noqa: E402
from backend.app.extraction.rate_limiter import estimate_tokens  # noqa: E402
from backend.app.extraction.spend_gate import (  # noqa: E402
    CLASSIFICATION_GATE_MULT, OVERRUN_FACTOR, preflight,
)
from backend.app.reasoning import scorers as S  # noqa: E402
from backend.app.reasoning.library_corpus import (  # noqa: E402
    addressals_path, load_library_corpus,
)
from backend.app.reasoning.run_structural_confirm import PROMPT as HOLE_PROMPT  # noqa: E402
from backend.app.relationships import future_work_llm as F  # noqa: E402
from backend.app.relationships.citation_graph import CitationEdge  # noqa: E402

DOMAINS = REPO_ROOT / "data" / "domains"
MAX_CONFIRM = 15
FX = 84.0


def n_clusters_for(n: int) -> int:
    return max(2, round(math.sqrt(n)))


def confirmations_path(slug: str) -> Path:
    return DOMAINS / slug / "reasoning" / "structural_hole_confirmations.json"


def _state(slug: str, stage: str) -> Path:
    return DOMAINS / slug / "reasoning" / f"{stage}_batch_state.json"


# ---- confirm -------------------------------------------------------------

def hole_leads(slug: str, rc=None) -> list[dict]:
    rc = rc or load_library_corpus(slug)
    opps = S.score_structural_holes(rc, n_clusters=n_clusters_for(len(rc.papers)), top=None)
    lim_by_id = {l.id: l for l, _p in rc.own_limitations}
    rows = []
    for o in opps[:MAX_CONFIRM]:
        a, b, lim_id = o.evidence_trail[0], o.evidence_trail[1], o.evidence_trail[2]
        method = o.title.split("'")[1] if "'" in o.title else "(method)"
        mclaims = [c.text for c in rc._loaded.extractions[a].claims if c.type == "method"][:3]
        lim = lim_by_id.get(lim_id)
        rows.append({"id": o.id, "a_pid": a, "b_pid": b,
                     "a_title": rc.papers[a].title or "?", "b_title": rc.papers[b].title or "?",
                     "method": method, "method_claims": " | ".join(mclaims),
                     "limitation": lim.text if lim else "?"})
    return rows


def hole_prompt(r: dict) -> str:
    return (HOLE_PROMPT.replace("<<A_TITLE>>", r["a_title"][:80])
            .replace("<<B_TITLE>>", r["b_title"][:80])
            .replace("<<METHOD>>", r["method"])
            .replace("<<METHOD_CLAIMS>>", r["method_claims"][:400])
            .replace("<<LIMITATION>>", r["limitation"][:300]))


def _parse_hole(raw: str) -> tuple[str, str]:
    try:
        d = json.loads(raw)
        v = str(d["verdict"]).strip().lower()
        reason = str(d.get("reason", "")).strip()
    except Exception:  # noqa: BLE001
        return "malformed", ""
    return (v if v in ("substantive", "trivial", "not_addressing") else "malformed"), reason


# ---- fwmatch -------------------------------------------------------------

def fw_candidates(slug: str, rc=None):
    rc = rc or load_library_corpus(slug)
    edges = [CitationEdge(from_paper_id=a, to_paper_id=b)
             for a, b in sorted(rc.citation_edges)]
    return rc, F.shortlist_candidates(rc._loaded, rc.fw_ids, rc.fw_vectors, rc.claim_ids,
                                      rc.claim_vectors, edges,
                                      shortlist_threshold=0.70, max_papers_per_fw=4)


# ---- shared batch driver ---------------------------------------------------

def _project(prompts: dict[str, str]) -> float:
    tin = sum(estimate_tokens(p) for p in prompts.values())
    tout = len(prompts) * pricing.OUT_TOKENS_PAIR
    return pricing.cost(tin, tout, batch=True) * FX


class BatchPending(RuntimeError):
    """The batch was submitted (state saved) but has not finished within the
    wait limit. Re-running the same stage resumes it; nothing is re-paid."""


def _run_batch(slug: str, stage: str, prompts: dict[str, str], *, client=None,
               poll_s: float = 20.0,
               wait_timeout_s: float = 26 * 3600) -> tuple[dict[str, str], dict]:
    """Submit (once) and collect; bill once; return raw results + money."""
    from backend.app.extraction.batch_client import record_batch_usage
    sp = _state(slug, stage)
    proj = _project(prompts)
    if client is None:
        from backend.app.extraction.batch_client import GeminiBatchClient
        client = GeminiBatchClient(model_name=get_settings().gemini_model)
    if sp.exists():
        st = json.loads(sp.read_text())
    else:
        preflight(stage=f"{stage}_{slug}", projected_inr=proj, n_calls=len(prompts),
                  multiplier=CLASSIFICATION_GATE_MULT)
        bid = client.submit(prompts, display_name=f"researchmap-{stage}-{slug}")
        st = {"batch_id": bid, "n": len(prompts), "projected_inr": proj,
              "ledger_recorded": False, "submitted_at": time.time()}
        sp.write_text(json.dumps(st, indent=2))
    job = client.wait(st["batch_id"], poll_interval_s=poll_s, timeout_s=wait_timeout_s)
    if not job.done:
        raise BatchPending(f"batch {st['batch_id']} still {job.state}; state kept in {sp.name}")
    if not job.succeeded:
        raise RuntimeError(f"batch {st['batch_id']} ended {job.state}")
    with_usage = client.results_with_usage(job)
    if not st.get("ledger_recorded"):
        st["recorded_inr"] = record_batch_usage(
            with_usage, stage=f"{stage}_{slug}", model=get_settings().gemini_model)
        st["ledger_recorded"] = True
        sp.write_text(json.dumps(st, indent=2))
    per_call = st["recorded_inr"] / max(1, len(with_usage))
    per_proj = st["projected_inr"] / max(1, st["n"])
    money = {"projected_inr": round(st["projected_inr"], 4), "actual_inr": round(st["recorded_inr"], 4),
             "calls": len(with_usage), "per_call_inr": round(per_call, 4),
             "overrun": per_call > per_proj * OVERRUN_FACTOR}
    return {k: v[0] for k, v in with_usage.items()}, money


def confirm(slug: str, *, dry_run: bool, client=None,
            wait_timeout_s: float = 26 * 3600) -> dict:
    rows = hole_leads(slug)
    out_p = confirmations_path(slug)
    done = json.loads(out_p.read_text()) if out_p.exists() else {}
    todo = [r for r in rows if r["id"] not in done]
    prompts = {r["id"]: hole_prompt(r) for r in todo}
    res = {"slug": slug, "leads": len(rows), "already_confirmed": len(rows) - len(todo),
           "to_confirm": len(todo), "projected_inr": round(_project(prompts), 4) if prompts else 0.0}
    if dry_run or not prompts:
        return res
    raw, money = _run_batch(slug, "hole_confirm", prompts, client=client,
                            wait_timeout_s=wait_timeout_s)
    by_id = {r["id"]: r for r in todo}
    from backend.app.reasoning.run_structural_confirm import _prompt_hash
    for oid, text in raw.items():
        v, reason = _parse_hole(text)
        r = by_id[oid]
        done[oid] = {"verdict": v, "reason": reason, "prompt_hash": _prompt_hash(),
                     "detector_model": f"gemini:{get_settings().gemini_model}",
                     "a_pid": r["a_pid"], "b_pid": r["b_pid"],
                     "method": r["method"], "limitation": r["limitation"]}
        out_p.write_text(json.dumps(done, indent=2))          # saved as each is read
    _state(slug, "hole_confirm").unlink(missing_ok=True)
    res.update(money)
    res["verdicts"] = dict(Counter(done[r["id"]]["verdict"] for r in rows if r["id"] in done))
    return res


def fwmatch(slug: str, *, dry_run: bool, client=None,
            wait_timeout_s: float = 26 * 3600) -> dict:
    rc, cands = fw_candidates(slug)
    ap = addressals_path(slug)
    done = {json.loads(l)["id"] for l in ap.read_text().splitlines() if l.strip()} if ap.exists() else set()
    fw_text = {fw.id: fw.text for fw, _m in rc.future_work}
    todo = [c for c in cands if f"fwa:{c.fw_id}__{c.to_paper_id}" not in done]
    prompts = {f"{c.fw_id}||{c.to_paper_id}": F.build_prompt(c, fw_text[c.fw_id]) for c in todo}
    res = {"slug": slug, "fw_items": len(rc.fw_ids), "candidate_pairs": len(cands),
           "already_classified": len(cands) - len(todo), "to_classify": len(todo),
           "projected_inr": round(_project(prompts), 4) if prompts else 0.0}
    if dry_run or not prompts:
        return res
    raw, money = _run_batch(slug, "fw_match", prompts, client=client,
                            wait_timeout_s=wait_timeout_s)
    by_key = {f"{c.fw_id}||{c.to_paper_id}": c for c in todo}
    counts = Counter()
    model = f"gemini:{get_settings().gemini_model}"
    with ap.open("a") as f:
        for key, text in raw.items():
            v = F.parse_verdict(text)
            if v is None:
                counts["malformed"] += 1
                continue
            label, just, elem = v
            counts[label] += 1
            a = F.to_addressal(by_key[key], label, just, elem, model_name=model, ph=F.prompt_hash())
            f.write(a.model_dump_json() + "\n")
            f.flush()
    _state(slug, "fw_match").unlink(missing_ok=True)
    from backend.app.reasoning.library_corpus import mark_fw_checked
    mark_fw_checked(slug, rc.fw_ids)    # every item this run looked at
    res.update(money)
    res["verdicts"] = dict(counts)
    return res


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("stage", choices=["confirm", "fwmatch"])
    ap.add_argument("--slug", required=True)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    fn = confirm if a.stage == "confirm" else fwmatch
    print(json.dumps(fn(a.slug, dry_run=a.dry_run), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
