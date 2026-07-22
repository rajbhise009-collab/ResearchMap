"""Version-pinned prompt loader tests."""

from __future__ import annotations

import hashlib

import pytest

from backend.app.extraction.prompt_versions import (
    available_versions,
    latest_version,
    load,
)


def test_at_least_one_version_exists():
    versions = available_versions()
    assert versions, "expected at least one prompt version directory"
    assert "v1.0.0" in versions


def test_load_returns_hash_matching_file_contents():
    pv = load("v1.0.0")
    computed = hashlib.sha256(pv.body.encode("utf-8")).hexdigest()
    assert pv.sha256_full == computed
    assert pv.hash == computed[:12]


def test_latest_returns_highest_semver():
    # With only v1.0.0 installed, latest returns v1.0.0.
    assert latest_version() == "v1.0.0"


def test_load_rejects_invalid_version_string():
    with pytest.raises(ValueError):
        load("latest")


def test_load_raises_when_version_directory_missing():
    with pytest.raises(FileNotFoundError):
        load("v9.9.9")


def test_render_substitutes_fields():
    pv = load("v1.0.0")
    rendered = pv.render(
        paper_id="openalex:W1",
        title="A Title",
        year=2024,
        venue="ACL",
        authors="A. Author, B. Bystander",
        abstract="This is the abstract.",
        fulltext_section="",
    )
    assert "openalex:W1" in rendered
    assert "A Title" in rendered
    assert "This is the abstract." in rendered
    assert "{paper_id}" not in rendered  # placeholder was consumed


def test_render_raises_when_field_missing():
    pv = load("v1.0.0")
    with pytest.raises(ValueError):
        pv.render(paper_id="X")  # missing other fields
