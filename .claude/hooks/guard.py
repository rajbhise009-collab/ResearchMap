#!/usr/bin/env python3
"""PreToolUse guard for ResearchMap's standing rules (.claude/settings.json).

Reads the hook JSON on stdin and answers with a permission decision:

  deny  history rewrites and force pushes; deleting branches; any
        weekly-grow.yml dispatch that is not gates_only=true or a
        republish; writing the ledger or projection log by hand; editing
        the frozen review folders (docs/review/diet-contradictions*/)
  ask   paid-path commands (live extraction, batch submit/collect, matcher
        and confirmation batches, embeddings, live OpenAlex sweeps, a live
        weekly run); editing a policy doc (docs/**/*policy*.md: extending
        is fine, overturning needs the owner); other workflow dispatches;
        enabling/disabling workflows; gh auth
  (no output) everything else — the normal permission flow applies

Standard library only. `decide(event)` is importable for tests.
"""
from __future__ import annotations

import fnmatch
import json
import re
import shlex
import sys
from pathlib import PurePosixPath

LEDGER_FILES = ("data/spend_ledger.json", "data/spend_projections.jsonl")
FROZEN_GLOBS = ("docs/review/diet-contradictions*/**", "docs/review/diet-contradictions*")
POLICY_GLOBS = ("docs/*policy*.md", "docs/**/*policy*.md")

# python entry points that can spend money or API credits when run for real
PAID_TARGETS = (
    "run_weekly.py", "multi_domain_extract", "run_batch_corpus", "multi_domain_reason",
    "run_library_scorers", "library_corpus", "cites_both", "validation.v1", "validation/v1.py",
    "build_library", "weekly_candidates", "snowball", "multi_domain_snowball", "recover_abstracts",
    "time_split_refresh",
)
FREE_MARKERS = ("--dry-run", "GROW_MOCK=1", "--help", " -h ")

WRITE_OPS = re.compile(
    r"(?:^|[\s;&|(])(?:rm|mv|cp|tee|truncate|dd|install|ln)\s|sed\s+(?:-\S*\s+)*-i|"
    r"(?<![<>&0-9])>{1,2}\s*(?!/dev/null)[^\s&]|git\s+(?:checkout|restore|rm|mv)\b|open\([^)]*['\"][wa]|write_text|write_bytes")


def _out(decision: str, reason: str) -> dict:
    return {"hookSpecificOutput": {"hookEventName": "PreToolUse",
                                   "permissionDecision": decision,
                                   "permissionDecisionReason": reason}}


def _rel(path: str, cwd: str) -> str:
    p = PurePosixPath(path)
    try:
        return str(p.relative_to(PurePosixPath(cwd))) if p.is_absolute() else str(p)
    except ValueError:
        return str(p)


def _match(rel: str, globs) -> bool:
    return any(fnmatch.fnmatch(rel, g) for g in globs)


HEREDOC = re.compile(r"<<-?\s*(['\"]?)([A-Za-z_][\w]*)\1")


def _strip_data_heredocs(cmd: str) -> str:
    """A heredoc that is only DATA written into a file (`cat > f <<EOF`,
    `tee f <<EOF`) is text, not commands: drop its body so a test file that
    mentions the ledger is not mistaken for a ledger write. A heredoc fed to
    an interpreter (`python - <<EOF`, `bash <<EOF`) is code and stays."""
    lines, out, skip_until = cmd.split("\n"), [], None
    for ln in lines:
        if skip_until is not None:
            if ln.strip() == skip_until:
                skip_until = None
            continue
        out.append(ln)
        m = HEREDOC.search(ln)
        if m and re.search(r"(?:^|[\s;&|(])(?:cat|tee)\b", ln[:m.start()]):
            skip_until = m.group(2)
    return "\n".join(out)


def _segments(cmd: str) -> list[str]:
    return [s.strip() for s in re.split(r"\|\||&&|;|\n|\|", _strip_data_heredocs(cmd)) if s.strip()]


def _git_rules(seg: str) -> dict | None:
    if not re.search(r"(?:^|\s)git\s", " " + seg):
        return None
    if re.search(r"\bgit\s+(?:-\S+\s+\S+\s+)*push\b", seg):
        try:
            words = shlex.split(seg)
        except ValueError:
            words = seg.split()
        args = words[words.index("push") + 1:] if "push" in words else []
        if any(a in ("--force", "-f", "--force-with-lease", "--force-if-includes", "--mirror", "--prune")
               or a.startswith("--force-with-lease=") or (a.startswith("-") and not a.startswith("--")
                                                         and "f" in a[1:]) for a in args):
            return _out("deny", "Force pushes are never allowed (standing rule: no history rewrites).")
        if any(a in ("--delete", "-d") for a in args) or any(
                not a.startswith("-") and a.startswith(":") for a in args):
            return _out("deny", "Deleting a remote branch is never allowed (standing rule: never delete branches).")
        if any(not a.startswith("-") and a.startswith("+") for a in args):
            return _out("deny", "A '+refspec' push is a force push (standing rule: no history rewrites).")
    if re.search(r"\bgit\s+branch\b.*\s(?:-d|-D|--delete)\b", seg) or re.search(r"\bgit\s+update-ref\s+-d\b", seg):
        return _out("deny", "Deleting a branch is never allowed (standing rule).")
    if re.search(r"\bgit\s+(?:rebase|filter-branch|filter-repo|replace)\b", seg) or \
            re.search(r"\bgit\s+commit\b.*--amend\b", seg):
        return _out("deny", "History rewrites (rebase, amend, filter-branch/-repo, replace) are never allowed.")
    if re.search(r"\bgit\s+reset\b.*--hard\b", seg) or re.search(r"\bgit\s+clean\b.*-\S*f", seg):
        return _out("ask", "This discards local work (git reset --hard / git clean -f). Confirm it is intended.")
    return None


def _gh_rules(seg: str) -> dict | None:
    if not re.search(r"(?:^|\s)gh\s", " " + seg):
        return None
    if re.search(r"\bgh\s+auth\b", seg):
        return _out("ask", "gh auth changes credentials; the owner decides (not set up yet).")
    if re.search(r"\bgh\s+workflow\s+(?:disable|enable)\b", seg):
        return _out("ask", "Enabling or disabling a workflow changes what runs unattended. Confirm.")
    if re.search(r"\bgh\s+api\b.*actions/workflows/[^\s]*/dispatches", seg):
        return _out("deny", "Dispatch workflows with `gh workflow run` so this guard can check the inputs.")
    m = re.search(r"\bgh\s+workflow\s+run\s+(\S+)", seg)
    if m:
        wf = m.group(1).strip("'\"")
        if wf in ("weekly-grow.yml", "Weekly grow", "378667080") or "weekly-grow" in wf:
            gates = re.search(r"gates_only=true\b", seg)
            repub = re.search(r"republish_branch=grow/\d{4}-\d{2}-\d{2}\b", seg)
            if re.search(r"gates_only=false\b", seg) or not (gates or repub):
                return _out("deny", "weekly-grow.yml may be dispatched only with -f gates_only=true or "
                                    "-f republish_branch=grow/<date> (zero spend). A live run is the owner's.")
            return None
        if "daily-health" in wf or wf == "Daily health":
            return None
        return _out("ask", f"Dispatching {wf}: only daily-health and zero-spend weekly-grow are pre-approved.")
    return None


def _paid_rules(seg: str, whole: str) -> dict | None:
    for m in re.finditer(r"(?:^|[\s;&|(])(?:\S*/)?python[0-9.]*\s+((?:-\S+\s+)*)(\S+)?(?:\s+(\S+))?", seg):
        # the first word after the flags is the script, or the module after -m
        target = m.group(2) or ""
        if "pytest" in target or not target or target == "-":
            continue
        if any(t in target for t in PAID_TARGETS) and not any(f in whole for f in FREE_MARKERS):
            return _out("ask", f"`{target}` can spend money or API credits when run for real. "
                               "Spend needs the owner's approval with a cost estimate first.")
    if re.search(r"\b(?:GEMINI_API_KEY|OPENALEX_API_KEY|ANTHROPIC_API_KEY)=\S", seg):
        return _out("ask", "This sets an API key inline: a live, possibly paid call. Confirm with a cost estimate.")
    if re.search(r"(?:generativelanguage\.googleapis\.com|api\.anthropic\.com)", seg) or \
            re.search(r"api\.openalex\.org\S*api_key", seg):
        return _out("ask", "Direct call to a paid or credit-metered API. Confirm with a cost estimate.")
    return None


def _path_rules_bash(seg: str, cwd: str) -> dict | None:
    if not WRITE_OPS.search(seg):
        return None
    if any(f in seg for f in ("spend_ledger.json", "spend_projections.jsonl")):
        return _out("deny", "The ledger and projection log are append-only and written only by code "
                            "(SpendLedger). Never edit, move, restore or delete them by hand.")
    for tok in re.findall(r"[\w./*-]*docs/review/diet-contradictions[\w./*-]*", seg):
        return _out("deny", f"{tok}: the diet-contradictions review folders are frozen.")
    for tok in re.findall(r"[\w./-]*docs/[\w./-]*policy[\w.-]*\.md", seg):
        return _out("ask", f"{tok} is a policy doc: extending is fine, overturning needs the owner (CLAUDE.md (d)).")
    return None


def _path_rules_edit(path: str, cwd: str) -> dict | None:
    rel = _rel(path, cwd)
    if rel in LEDGER_FILES:
        return _out("deny", "The ledger and projection log are append-only and written only by code "
                            "(SpendLedger). Never edit them by hand.")
    if _match(rel, FROZEN_GLOBS):
        return _out("deny", f"{rel}: the diet-contradictions review folders are frozen.")
    if _match(rel, POLICY_GLOBS):
        return _out("ask", f"{rel} is a policy doc: extending is fine, overturning needs the owner (CLAUDE.md (d)).")
    return None


def decide(event: dict) -> dict | None:
    tool = event.get("tool_name", "")
    ti = event.get("tool_input") or {}
    cwd = event.get("cwd") or ""
    if tool == "Bash":
        cmd = ti.get("command") or ""
        order = {"deny": 0, "ask": 1}
        found = []
        for seg in _segments(cmd):
            for rule in (_git_rules, _gh_rules):
                r = rule(seg)
                if r:
                    found.append(r)
            r = _paid_rules(seg, cmd) or _path_rules_bash(seg, cwd)
            if r:
                found.append(r)
        if found:
            return min(found, key=lambda r: order[r["hookSpecificOutput"]["permissionDecision"]])
        return None
    if tool in ("Edit", "Write", "MultiEdit", "NotebookEdit"):
        path = ti.get("file_path") or ti.get("notebook_path") or ""
        return _path_rules_edit(path, cwd) if path else None
    return None


def main() -> int:
    try:
        event = json.load(sys.stdin)
    except Exception:  # noqa: BLE001  (never block on a malformed event)
        return 0
    out = decide(event)
    if out:
        print(json.dumps(out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
