"""Pass 5 (title similarity) — conservative: merges a retitled journal
version of a preprint, refuses look-alike titles that are different works."""

from __future__ import annotations

import json
from pathlib import Path

from backend.app.ingestion.normalizer import (
    deduplicate, title_similarity_candidates, title_similarity_check,
)
from backend.app.models import Paper

ABS = ("Fairness is an increasingly important concern as machine learning models "
       "are used to support decision making in high-stakes applications such as "
       "mortgage lending, hiring, and prison sentencing. This paper introduces a "
       "new open source Python toolkit for algorithmic fairness.")


def _p(i, title, year, authors, doi=None, abstract=ABS, venue=None, cites=0):
    return Paper(id=f"openalex:W{i}", source="openalex", source_id=f"W{i}", doi=doi,
                 title=title, abstract=abstract, year=year, authors=authors,
                 venue=venue, citations_in_count=cites)


PREPRINT = _p(2, "AI Fairness 360: An Extensible Toolkit for Detecting, Understanding, and "
                 "Mitigating Unwanted Algorithmic Bias", 2018, ["Rachel K. E. Bellamy", "Kuntal Dey"],
              doi="10.48550/arxiv.1810.01943", venue="arXiv", cites=267)
JOURNAL = _p(1, "AI Fairness 360: An extensible toolkit for detecting and mitigating "
                "algorithmic bias", 2019, ["R. K. E. Bellamy", "K. Dey"],
             doi="10.1147/jrd.2019.2942287", venue="IBM J. Res. Dev.", cites=887)


def test_retitled_journal_version_merges_into_journal_survivor():
    assert title_similarity_check(PREPRINT, JOURNAL)["merge"]
    out = deduplicate([PREPRINT, JOURNAL])
    assert len(out) == 1 and out[0].id == "openalex:W1"
    assert out[0].merged_from == ["openalex:W2"]


def test_same_title_family_different_papers_not_merged():
    """Same group, near-identical titles, different studies (a review and an
    empirical paper): the abstracts differ, so no merge."""
    review = _p(3, "Mitigating Bias and Hallucinations in LLMs through Prompt Engineering "
                   "and Knowledge-Grounded Approaches in Healthcare Domain: A Systematic "
                   "Literature Review", 2025, ["Ishadya Withanaarachchi"],
                abstract="This systematic literature review examines peer-reviewed studies "
                         "published between 2021 and 2025; thirty-four studies were synthesized.")
    study = _p(4, "Mitigating Bias and Hallucinations in LLMs Through Prompt Engineering and "
                  "Knowledge-Grounded Approaches in Healthcare Domain", 2026,
               ["Ishadya Withanaarachchi"],
               abstract="This study proposes an integrated mitigation framework evaluated on "
                        "MedQuAD subsets with parallel RAG and MCP pipelines.")
    r = title_similarity_check(review, study)
    assert not r["merge"] and r["blocked_by"] == "abstract_jaccard"
    assert len(deduplicate([review, study])) == 2


def test_annual_editions_blocked_by_numbers_even_with_identical_abstracts():
    a = _p(5, "5. Facilitating Positive Health Behaviors and Well-being to Improve Health "
              "Outcomes: Standards of Care in Diabetes—2023", 2022, ["Nuha A. ElSayed"])
    b = _p(6, "5. Facilitating Positive Health Behaviors and Well-being to Improve Health "
              "Outcomes: Standards of Care in Diabetes—2025", 2024, ["Nuha A. ElSayed"])
    r = title_similarity_check(a, b)
    assert not r["merge"] and r["blocked_by"] == "numeric_tokens"


def test_different_first_author_or_missing_abstract_never_merges():
    other = PREPRINT.model_copy(update={"authors": ["Someone Else"]})
    assert title_similarity_check(other, JOURNAL)["blocked_by"] == "first_author"
    bare = PREPRINT.model_copy(update={"abstract": None})
    assert title_similarity_check(bare, JOURNAL)["blocked_by"] == "abstracts_present"


def test_report_only_never_merges_and_pass_can_be_disabled():
    c = title_similarity_candidates([PREPRINT, JOURNAL])
    assert len(c) == 1 and c[0]["merge"]
    assert len(deduplicate([PREPRINT, JOURNAL], title_similarity=False)) == 2


def test_published_corpora_have_no_pending_pass5_merge():
    """The report-only run over the three published libraries finds nothing
    left to merge (the one hit, AI Fairness 360, was merged)."""
    repo = Path(__file__).resolve().parents[3]
    d = json.loads((repo / "data" / "duplicate_check_v2.json").read_text())
    for name in ("llm-calibration", "diet-and-mortality", "ml-fairness"):
        assert d["corpora"][name]["would_merge"] == 0, name
