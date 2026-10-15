"""The end-to-end marker (docs/releases/growth-e2e-passed.json) is bound to
the tree that was tested: tools/grow/e2e_mock.tree_without_marker leaves the
marker out of the tree hash, so a squash that keeps the content verifies and
any other change does not."""
from __future__ import annotations

import importlib.util
import json
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]


def _e2e():
    spec = importlib.util.spec_from_file_location("e2e_mock", REPO / "tools" / "grow" / "e2e_mock.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _git(repo, *a):
    return subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid", *a], cwd=repo,
                          check=True, capture_output=True, text=True).stdout.strip()


def _repo(tmp_path):
    r = tmp_path / "r"
    r.mkdir()
    _git(r, "init", "-q", "-b", "main")
    (r / "code.py").write_text("x = 1\n")
    _git(r, "add", "-A")
    _git(r, "commit", "-q", "-m", "tested")
    return r


def _mark(e2e, r, tested, failed=0):
    p = r / e2e.MARKER_REL
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"full": True, "failed": failed, "passed": 3,
                             "tested_tree": e2e.tree_without_marker(tested, r)}))


def test_a_squash_with_the_same_content_verifies(tmp_path):
    e2e, r = _e2e(), _repo(tmp_path)
    tested = _git(r, "rev-parse", "HEAD")
    _mark(e2e, r, tested)
    _git(r, "add", "-A")
    _git(r, "commit", "-q", "-m", "marker")
    ok, why = e2e.verify_marker("HEAD", r)
    assert ok, why
    # a different commit (another message, another parent) with the same files
    _git(r, "checkout", "-q", "--orphan", "squash")
    _git(r, "commit", "-q", "-m", "squashed")
    assert _git(r, "rev-parse", "HEAD") != tested
    assert e2e.verify_marker("HEAD", r)[0]


def test_any_other_change_does_not_verify(tmp_path):
    e2e, r = _e2e(), _repo(tmp_path)
    _mark(e2e, r, _git(r, "rev-parse", "HEAD"))
    (r / "code.py").write_text("x = 2\n")                 # not the content tested
    _git(r, "add", "-A")
    _git(r, "commit", "-q", "-m", "marker plus an untested change")
    ok, why = e2e.verify_marker("HEAD", r)
    assert not ok and "not the content tested" in why


def test_a_failed_or_missing_marker_does_not_verify(tmp_path):
    e2e, r = _e2e(), _repo(tmp_path)
    assert not e2e.verify_marker("HEAD", r)[0]           # no marker at all
    _mark(e2e, r, _git(r, "rev-parse", "HEAD"), failed=1)
    _git(r, "add", "-A")
    _git(r, "commit", "-q", "-m", "failed marker")
    ok, why = e2e.verify_marker("HEAD", r)
    assert not ok and "not a full pass" in why


def test_the_tree_hash_ignores_only_the_marker(tmp_path):
    e2e, r = _e2e(), _repo(tmp_path)
    before = e2e.tree_without_marker("HEAD", r)
    _mark(e2e, r, "HEAD")
    _git(r, "add", "-A")
    _git(r, "commit", "-q", "-m", "marker")
    assert e2e.tree_without_marker("HEAD", r) == before
    (r / "other.txt").write_text("y")
    _git(r, "add", "-A")
    _git(r, "commit", "-q", "-m", "other")
    assert e2e.tree_without_marker("HEAD", r) != before
