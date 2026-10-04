"""duplicate_check reads files only; the diet audit's duplicate verdicts are
classified against the audit itself."""

from backend.app.corpus import duplicate_check as D


def test_every_diet_audit_duplicate_maps_to_a_non_duplicate_pair():
    rows = D.diet_audit_duplicates()
    assert rows, "the diet audit has duplicate verdicts"
    for r in rows:
        assert r["same_two_papers_as_pair"], r
        assert r["kind"].startswith("same two papers")


def test_candidates_flag_same_doi_and_near_titles():
    from backend.app.models import Paper
    mk = lambda i, t, doi, a: Paper.model_construct(  # noqa: E731
        id=f"openalex:W{i}", title=t, doi=doi, year=2019, authors=a)
    c = D._candidates([mk(1, "AI Fairness 360: a toolkit", "10.1/x", ["A Bee"]),
                       mk(2, "AI Fairness 360: A Toolkit!", "10.48550/arxiv.1", ["A Bee"]),
                       mk(3, "Unrelated title entirely", "10.1/x", [])])
    pairs = {(x["a"], x["b"]): x["reasons"] for x in c}
    assert "same normalized title" in pairs[("W1", "W2")]
    assert "same DOI" in pairs[("W1", "W3")]
