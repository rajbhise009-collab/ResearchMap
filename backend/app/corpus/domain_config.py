"""DomainConfig: one library's rubric and snowball settings."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DomainConfig:
    slug: str
    name: str
    # OpenAlex filter string used to pull the seed pool (same shape as
    # backend/app/coherence/fetch.py DOMAINS). Top-cited N are picked as
    # seeds after prelabelling.
    seed_filter: str
    # Heuristic classifier vocabulary.
    anchor_terms: tuple[str, ...]
    topic_terms: tuple[str, ...]
    strong_topic_terms: tuple[str, ...]
    # When non-empty, a strong-term match promotes to on-domain ONLY when
    # at least one `pair_terms` string is ALSO present in the text — the
    # "both sides required" discipline for domains where either half of
    # a strong term is common outside the domain (e.g. diet-and-mortality,
    # where "dietary pattern" alone matches a nutritional survey and
    # "all-cause mortality" alone matches a COVID physical-activity study,
    # but neither is diet-mortality research). Empty tuple = strong-term
    # rule stays a single-side test.
    pair_terms: tuple[str, ...] = ()
    # Additionally require the strong term to appear in the TITLE, OR to
    # co-occur with a pair_term in the SAME SENTENCE of the abstract.
    # This targets background-mention false positives (COVID paper: both
    # terms present but in unrelated sentences). Only meaningful with
    # pair_terms; ignored otherwise.
    require_pair_in_title_or_sentence: bool = False
    # Venue substrings (lowercase). Allowlist admits + rescues; denylist
    # is decisive off-domain unless a title-level rescue fires.
    venue_allowlist: tuple[str, ...] = ()
    venue_denylist: tuple[str, ...] = ()
    # OpenAlex primary_topic.field.display_name substrings (lowercase).
    field_allowlist: tuple[str, ...] = ()
    field_denylist: tuple[str, ...] = ()
    # Snowball caps. Small enough for a 100-paper target.
    global_target: int = 150      # pre-dedup pool; trim to 100 after prelabel
    per_seed_cap: int = 20
    hop2_cap: int = 15
    hop2_expand_top_n: int = 20
    n_seeds: int = 30
    # Token windows for the anchor-topic co-occurrence checks.
    co_window: int = 30
    title_co_window: int = 12
