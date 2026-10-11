"""The Claude Code hooks (.claude/hooks) and the pre-push hook (.githooks)
enforce the standing rules. Each rule is pinned here with real commands."""
from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
HOOKS = REPO / ".claude" / "hooks"
CWD = str(REPO)


def _load(name):
    spec = importlib.util.spec_from_file_location(name, HOOKS / f"{name}.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


guard = _load("guard")


def _bash(cmd):
    out = guard.decide({"tool_name": "Bash", "tool_input": {"command": cmd}, "cwd": CWD})
    return out["hookSpecificOutput"]["permissionDecision"] if out else None


def _edit(path, tool="Edit"):
    out = guard.decide({"tool_name": tool, "tool_input": {"file_path": path}, "cwd": CWD})
    return out["hookSpecificOutput"]["permissionDecision"] if out else None


LEDGER = "data/" + "spend_ledger.json"          # split so this file is not itself a "ledger write"


@pytest.mark.parametrize("cmd,want", [
    # history and branches
    ("git push --force origin main", "deny"),
    ("git push -f origin main", "deny"),
    ("git push --force-with-lease origin main", "deny"),
    ("git push origin +main", "deny"),
    ("git push origin --delete grow/2026-10-10", "deny"),
    ("git push origin :grow/2026-10-10", "deny"),
    ("git push --prune origin", "deny"),
    ("git branch -D grow/2026-10-10", "deny"),
    ("git branch -d old", "deny"),
    ("git rebase -i HEAD~3", "deny"),
    ("git commit --amend -m x", "deny"),
    ("git filter-repo --path data", "deny"),
    ("git reset --hard origin/main", "ask"),
    ("git push origin main", None),
    ("git push -u origin feature", None),
    ("cd x && git fetch -q origin && git push origin main 2>&1 | tail -1", None),
    # workflow dispatches
    ("gh workflow run weekly-grow.yml", "deny"),
    ("gh workflow run weekly-grow.yml -f gates_only=false", "deny"),
    ("gh workflow run weekly-grow.yml -f run_budget_inr=50", "deny"),
    ("gh workflow run weekly-grow.yml --ref main -f gates_only=true", None),
    ("gh workflow run weekly-grow.yml -f republish_branch=grow/2026-10-10", None),
    ("gh workflow run daily-health.yml", None),
    ("gh workflow run deploy-pages.yml", "ask"),
    ("gh workflow disable weekly-grow.yml", "ask"),
    ("gh api repos/o/r/actions/workflows/1/dispatches -f ref=main", "deny"),
    ("gh auth login", "ask"),
    ("gh run watch 123", None),
    # paid paths
    (".venv/bin/python tools/grow/run_weekly.py", "ask"),
    (".venv/bin/python tools/grow/run_weekly.py --dry-run", None),
    ("GROW_MOCK=1 .venv/bin/python tools/grow/run_weekly.py", None),
    (".venv/bin/python -m backend.app.corpus.multi_domain_extract --domain diet", "ask"),
    ("python -m backend.app.reasoning.run_library_scorers fwmatch --slug x", "ask"),
    ("python -m backend.app.reasoning.run_library_scorers fwmatch --slug x --dry-run", None),
    ("python -m backend.app.validation.v1 --run", "ask"),
    ("GEMINI_API_KEY=abc python x.py", "ask"),
    ("curl 'https://api.openalex.org/works?api_key=abc'", "ask"),
    (".venv/bin/python -m pytest backend/tests -q", None),
    (".venv/bin/python tools/grow/e2e_mock.py", None),
    ("grep -n run_weekly tools/grow/run_weekly.py", None),
    (".venv/bin/python -m backend.app.extraction.money", None),
    # ledger: append-only, written only by code
    (f"echo {{}} > {LEDGER}", "deny"),
    (f"sed -i '' s/1/2/ {LEDGER}", "deny"),
    (f"git checkout -- {LEDGER}", "deny"),
    ("rm data/spend_projections.jsonl", "deny"),
    (f"python - <<'EOF'\nopen('{LEDGER}', 'w').write('x')\nEOF", "deny"),     # code in a heredoc IS checked
    (f"cat > notes.md <<'EOF'\necho {{}} > {LEDGER}\nEOF", None),            # data in a heredoc is not
    (f"cat {LEDGER}", None),
    (f"git diff --quiet {LEDGER} && echo ok", None),
    (f"cat {LEDGER} > /dev/null", None),
    # frozen and policy docs
    ("rm -r docs/review/diet-contradictions-2026-09/", "deny"),
    ("sed -i '' s/a/b/ docs/merge-policy.md", "ask"),
    ("cat docs/merge-policy.md", None),
])
def test_guard_bash(cmd, want):
    assert _bash(cmd) == want, cmd


@pytest.mark.parametrize("path,want", [
    (LEDGER, "deny"),
    (f"{CWD}/data/spend_projections.jsonl", "deny"),
    ("docs/review/diet-contradictions-2026-09/answers.md", "deny"),
    ("docs/confidence-policy.md", "ask"),
    ("docs/merge-policy.md", "ask"),
    ("docs/findings/x-policy.md", "ask"),
    ("docs/OPERATIONS.md", None),
    ("backend/app/grow/core.py", None),
])
def test_guard_edits(path, want):
    for tool in ("Edit", "Write", "MultiEdit"):
        assert _edit(path, tool) == want, (path, tool)


def test_hooks_run_on_the_system_python():
    """The hooks run under `python3` from PATH (the system one, 3.9 on macOS)
    so they keep working even if the project venv breaks; a malformed event
    never blocks a tool call."""
    py = shutil.which("python3") or sys.executable
    for name in ("guard", "private_guard", "confidence_check", "stop_tests"):
        r = subprocess.run([py, "-c", f"import ast; ast.parse(open({str(HOOKS / (name + '.py'))!r}).read())"],
                           capture_output=True, text=True)
        assert r.returncode == 0, (name, r.stderr)
    ev = json.dumps({"tool_name": "Bash", "tool_input": {"command": "git push --force"}, "cwd": CWD})
    r = subprocess.run([py, str(HOOKS / "guard.py")], input=ev, capture_output=True, text=True)
    assert r.returncode == 0 and json.loads(r.stdout)["hookSpecificOutput"]["permissionDecision"] == "deny"
    r = subprocess.run([py, str(HOOKS / "guard.py")], input="not json", capture_output=True, text=True)
    assert r.returncode == 0 and r.stdout == ""


def test_private_guard_freezes_existing_files_allows_new(tmp_path):
    pg = _load("private_guard")
    home = tmp_path
    priv = home / "ResearchMap-private"
    (priv / "launch-qa").mkdir(parents=True)
    (priv / "launch-qa" / "old.json").write_text("{}")

    def dec(ev):
        return ((pg.decide(ev, home=str(home)) or {}).get("hookSpecificOutput") or {}).get("permissionDecision")
    assert dec({"tool_name": "Edit", "tool_input": {"file_path": str(priv / "launch-qa" / "old.json")}}) == "deny"
    assert dec({"tool_name": "Write", "tool_input": {"file_path": str(priv / "launch-qa" / "new.json")}}) is None
    assert dec({"tool_name": "Bash", "tool_input": {"command": f"rm {priv}/launch-qa/old.json"}}) == "deny"
    assert dec({"tool_name": "Bash",
                "tool_input": {"command": "echo x > ~/ResearchMap-private/launch-qa/old.json"}}) == "deny"
    assert dec({"tool_name": "Bash", "tool_input": {"command": "echo x > ~/ResearchMap-private/brand-new.md"}}) is None
    assert dec({"tool_name": "Bash", "tool_input": {"command": "cat ~/ResearchMap-private/launch-qa/old.json"}}) is None
    # quoted paths the shell expands are still writes ...
    assert dec({"tool_name": "Bash", "tool_input": {"command": f'rm "{priv}/launch-qa/old.json"'}}) == "deny"
    assert dec({"tool_name": "Bash",
                "tool_input": {"command": 'echo x > "$HOME/ResearchMap-private/launch-qa/old.json"'}}) == "deny"
    # ... but a commit message or echo that only MENTIONS the folder is not
    assert dec({"tool_name": "Bash", "tool_input": {
        "command": 'git commit -m "private_guard: ~/ResearchMap-private existing files frozen (rm blocked)"'}}) is None
    assert dec({"tool_name": "Bash", "tool_input": {"command": "echo 'see ~/ResearchMap-private/launch-qa' > note.md"}}) is None


def test_private_rule_is_local_only():
    shared = (REPO / ".claude" / "settings.json").read_text()
    assert "private_guard" not in shared
    local = REPO / ".claude" / "settings.local.json"
    if local.exists():
        assert "private_guard" in local.read_text()
        r = subprocess.run(["git", "check-ignore", "-q", ".claude/settings.local.json"], cwd=REPO)
        assert r.returncode == 0, "settings.local.json must not be committed"


def test_confidence_check_flags_claim_confidence_and_the_scoring_code_is_clean():
    cc = _load("confidence_check")
    assert cc.scan("score = c.confidence * 2") and cc.scan('w = d.get("confidence")')
    assert not cc.scan("rank = o.score * o.confidence") and not cc.scan('"""Claim.confidence is banned"""')
    hits = [(str(f), h) for d in cc.SCORING_DIRS for f in (REPO / d).rglob("*.py")
            for h in cc.scan(f.read_text())]
    assert hits == [], hits


def test_stop_hook_picks_suites_from_changed_paths():
    st = _load("stop_tests")
    assert "backend/tests/api/test_search_growth.py" in st.suites_for(["backend/app/api/search_index.py"])
    assert "@tsc" in st.suites_for(["frontend/lib/search.ts"])
    assert st.suites_for(["backend/app/grow/core.py"])[0] == "backend/tests/grow"
    assert st.suites_for(["backend/tests/grow/test_scope.py"]) == ["backend/tests/grow/test_scope.py"]
    assert st.suites_for(["backend/app/config.py", "backend/app/grow/core.py"])[0] == "backend/tests"
    assert st.suites_for(["docs/OPERATIONS.md", LEDGER]) == []
    assert st.suites_for(["frontend/public/data/site-facts.json"]) == []


def _repo(tmp_path):
    origin, work = tmp_path / "o.git", tmp_path / "w"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(origin)], check=True)
    subprocess.run(["git", "clone", "-q", str(origin), str(work)], check=True, capture_output=True)
    for k, v in (("user.name", "t"), ("user.email", "t@example.invalid")):
        subprocess.run(["git", "config", k, v], cwd=work, check=True)
    (work / "a.txt").write_text("1")
    subprocess.run(["git", "add", "-A"], cwd=work, check=True)
    subprocess.run(["git", "commit", "-qm", "a"], cwd=work, check=True)
    return work


def test_pre_push_refuses_deletes_and_non_fast_forward(tmp_path):
    work = _repo(tmp_path)
    sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=work, capture_output=True, text=True).stdout.strip()
    zero = "0" * 40
    hook = REPO / ".githooks" / "pre-push"
    env = {"PATH": "/usr/bin:/bin:/opt/homebrew/bin", "PY": sys.executable, "HOME": str(tmp_path)}
    r = subprocess.run(["bash", str(hook)], cwd=work, input=f"(delete) {zero} refs/heads/x {sha}\n",
                       capture_output=True, text=True, env=env)
    assert r.returncode == 1 and "never delete branches" in r.stderr
    (work / "a.txt").write_text("2")
    subprocess.run(["git", "commit", "-qam", "b"], cwd=work, check=True)
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=work, capture_output=True, text=True).stdout.strip()
    other = subprocess.run(["git", "commit-tree", f"{sha}^{{tree}}", "-m", "unrelated"], cwd=work,
                           capture_output=True, text=True).stdout.strip()
    r = subprocess.run(["bash", str(hook)], cwd=work, input=f"refs/heads/main {head} refs/heads/main {other}\n",
                       capture_output=True, text=True, env=env)
    assert r.returncode == 1 and "non-fast-forward" in r.stderr
