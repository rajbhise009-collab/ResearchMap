"""Domain-agnostic corpus builder for the multi-library expansion.

Each domain gets its own `DomainConfig` — anchor + topic + strong terms,
venue lists, field lists — and the pipeline runs the same four stages
without touching the LLM-calibration modules:

  1. snowball    seed from top-cited on-domain candidates → 2-hop
                 citation walk with per-seed cap + hop-2 cap + global
                 target. Bulk-fetches metadata for referenced ids.
  2. prelabel    heuristic classification (contribution not vocabulary,
                 no-signal→exclude); persists per-paper reasoning.
  3. fulltext    arXiv → Unpaywall → Europe PMC; flags abstract_only.
  4. audit       stratified 15-paper Markdown sample, hard cases flagged.

All four stages are FREE — OpenAlex uses `filter=` calls (1 credit each,
of the 10,000/day quota), arXiv / Unpaywall / Europe PMC are free.
Nothing here calls a paid LLM.

Per-domain data:
    data/domains/<slug>/snowball.json      raw fetched records + ledger
    data/domains/<slug>/prelabelled.json   labels + rationale + fulltext status
    data/domains/<slug>/audit_sample.md    15-paper Markdown sample

Usage:
    python -m backend.app.corpus.multi_domain --domain diet --stage all
    python -m backend.app.corpus.multi_domain --domain fairness --stage snowball
"""

from __future__ import annotations

import argparse
import json
import random
import re
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Optional

import httpx

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))

from backend.app.config import get_settings  # noqa: E402
from backend.app.ingestion.fulltext import (  # noqa: E402
    fetch_pdf_text,
    load_cached_fulltext,
    retrieve_fulltext,
    store_fulltext,
)
from backend.app.ingestion.normalizer import (  # noqa: E402
    _reconstruct_abstract,
    from_openalex,
)
from backend.app.ingestion.oa_fulltext import retrieve_oa_fulltext  # noqa: E402
from backend.app.ingestion.openalex import (  # noqa: E402
    OpenAlexClient,
)

# Email for Unpaywall's polite-pool request. Matches
# backend/app/corpus/recover_oa_fulltext.py — this is the same service
# and same use pattern Raj already authorised for the LLM-cal recovery,
# not a new destination for the address.
UNPAYWALL_EMAIL = "raj.bhise009@gmail.com"

DOMAINS_DIR = REPO_ROOT / "data" / "domains"


# --------------------------------------------------------------------------
# DomainConfig: everything the classifier + snowball needs to know that
# is different per domain. No global state; every function that discriminates
# takes a config.
# --------------------------------------------------------------------------


from backend.app.corpus.domain_config import DomainConfig  # noqa: E402  (re-exported)


# --------------------------------------------------------------------------
# The two new domains
# --------------------------------------------------------------------------


DIET_CONFIG = DomainConfig(
    slug="diet-and-mortality",
    name="Diet and all-cause mortality",
    # First-pass filter `"all-cause mortality" AND (diet OR "dietary pattern"
    # OR nutrition)` matched Global-Burden-of-Disease studies at the top —
    # those mention diet as one of many population risk factors, not as
    # their contribution, so the corpus filled with GBD consortium updates
    # instead of red-meat / saturated-fat / low-carb style diet-mortality
    # research. Tightened filter: require the mortality outcome AND a
    # named diet component or nameable regime — the classifier's own
    # STRONG_TOPIC_TERMS as an OpenAlex query.
    seed_filter=(
        'title_and_abstract.search:('
        '"dietary pattern" OR "mediterranean diet" OR "plant-based diet" OR '
        '"low-carbohydrate diet" OR "ketogenic diet" OR "vegetarian diet" OR '
        '"vegan diet" OR "red meat" OR "processed meat" OR "ultra-processed" OR '
        '"sugar-sweetened" OR "saturated fat" OR "trans fat" OR "whole grain" OR '
        '"dietary fibre" OR "dietary fiber" OR "sodium intake" OR "alcohol consumption") '
        'AND ("all-cause mortality" OR "cardiovascular mortality" OR '
        '"cancer mortality" OR "coronary heart disease" OR "type 2 diabetes"),'
        "type:article|preprint,publication_year:>2015"
    ),
    anchor_terms=(
        "diet", "dietary", "nutrition", "nutritional", "food intake",
    ),
    topic_terms=(
        "mortality", "death", "all-cause",
        "cardiovascular disease", "coronary heart disease",
        "stroke", "cancer incidence", "type 2 diabetes",
        "metabolic syndrome", "hypertension",
    ),
    # NAMED DIET EXPOSURES only — no outcome terms here. On-domain now
    # requires BOTH an exposure (strong_topic_terms) AND an outcome
    # (pair_terms). This removes the COVID-physical-activity false
    # positive (matches "all-cause mortality" but no diet exposure) and
    # the buckwheat food-chemistry false positive (matches "dietary
    # fibre" but no mortality/hard-outcome).
    strong_topic_terms=(
        "dietary pattern",
        "mediterranean diet", "dash diet", "plant-based diet",
        "vegetarian diet", "vegan diet",
        "ketogenic diet", "low-carbohydrate diet", "low-fat diet",
        "high-protein diet",
        "red meat", "processed meat", "ultra-processed food",
        "sugar-sweetened beverage", "sugar sweetened beverage",
        "trans fat", "saturated fat",
        "whole grain", "dietary fibre", "dietary fiber",
        "fibre intake", "fiber intake",
        "sodium intake", "alcohol consumption",
        "dietary intervention", "nutritional intervention",
        # Microbiome-diet-health strong terms — round-2 redraw to rescue
        # microbiome-diet papers to borderline. Requires a pair term for
        # on-domain (per the same-sentence-or-title rule), so a bare
        # microbiome paper without a diet or health outcome drops to
        # borderline, not core. Aligns with the rubric's "substantial
        # component" borderline definition for mechanistic diet-microbiome-
        # metabolism work.
        "gut microbiota", "gut microbiome", "microbiome",
    ),
    pair_terms=(
        "all-cause mortality", "cardiovascular mortality",
        "cancer mortality", "premature mortality",
        "cardiovascular disease", "coronary heart disease",
        "myocardial infarction", "ischemic heart disease",
        "stroke", "type 2 diabetes", "diabetes incidence",
        "hypertension", "cancer incidence", "colorectal cancer",
        "breast cancer", "metabolic syndrome",
        # Added round-2 redraw: obesity is a mortality-adjacent hard
        # outcome; needed as a pair term so gut-microbiome-obesity papers
        # (mechanistic diet literature) can qualify without arbitrarily
        # broadening the seed filter.
        "obesity",
    ),
    require_pair_in_title_or_sentence=True,
    venue_allowlist=(
        "american journal of clinical nutrition",
        "journal of nutrition",
        "nutrients",
        "european journal of clinical nutrition",
        "british journal of nutrition",
        "public health nutrition",
        "bmj", "british medical journal",
        "the lancet", "lancet public health", "lancet diabetes",
        "new england journal of medicine", "nejm",
        "jama", "jama internal medicine", "jama network open",
        "circulation", "european heart journal",
        "american journal of epidemiology",
        "international journal of epidemiology",
        "epidemiology",
        "diabetes care",
    ),
    venue_denylist=(
        # ML / physics / materials — clearly off
        "neural information processing systems", "neurips",
        "icml", "iclr", "acl", "emnlp",
        "chemistry of materials", "advanced materials",
        "journal of physical chemistry",
        "chemical reviews", "chemcomm",
        # Food chemistry / composition — not health outcomes
        "food chemistry",
        "journal of agricultural and food chemistry",
        "journal of food science",
        "lwt", "food science and technology",
        # Analytical / measurement — not epi
        "analytical chemistry",
        # Veterinary / animal science
        "veterinary",
        "animal science",
    ),
    field_allowlist=(
        "medicine",
        "nursing",
        "health professions",
        "biochemistry, genetics and molecular biology",
        "immunology and microbiology",
        "pharmacology, toxicology and pharmaceutics",
        "agricultural and biological sciences",
        # Nutrition falls under various OpenAlex fields; we're permissive
        # here and rely on venue + strong-term signals for precision.
        "environmental science",
    ),
    field_denylist=(
        "computer science",
        "chemistry",
        "materials science",
        "physics and astronomy",
        "earth and planetary sciences",
        "chemical engineering",
        "energy",
        "engineering",
        "mathematics",
    ),
)


FAIRNESS_CONFIG = DomainConfig(
    slug="ml-fairness",
    name="Algorithmic fairness in machine learning",
    seed_filter=(
        'title_and_abstract.search:("algorithmic fairness" OR '
        '"machine learning fairness" OR "fair classification"),'
        "type:article|preprint,publication_year:>2018"
    ),
    anchor_terms=(
        "classifier", "classification",
        "machine learning", "ml model", "algorithm",
        "supervised learning", "deep learning",
        "neural network", "learned model",
        "prediction", "predictive model",
        # Multi-word ML-adjacent anchors so a title like "AI-driven
        # healthcare" + "fairness" reaches the title-window rescue.
        # Bare "ai" (single token) removed — matches too many general-ML
        # papers and blew fairness core to 109/150; the multi-word forms
        # + "ai-driven" catch the intended case without the false-positive
        # storm.
        "artificial intelligence", "ai-driven",
    ),
    topic_terms=(
        "fairness", "fair", "unfair", "unfairness",
        "discrimination", "discriminatory",
        "disparate", "equity", "equality",
        "demographic bias", "gender bias", "racial bias",
        "protected attribute",
    ),
    strong_topic_terms=(
        "algorithmic fairness",
        "demographic parity",
        "equalized odds", "equal opportunity",
        "counterfactual fairness",
        "individual fairness", "group fairness", "subgroup fairness",
        "calibration fairness",
        "disparate impact", "disparate treatment", "disparate mistreatment",
        "fair classification", "fair regression", "fair clustering",
        "fair ranking", "fair representation",
        "fair representation learning",
        "fairness through unawareness",
        "predictive parity",
        "fairness constraint", "fairness metric", "fairness definition",
        "gender shades",
        # Risk-assessment / criminal-justice fairness terms — the audit
        # surfaced Berk et al. as missed because the abstract uses "risk
        # assessment" and "fairness" separately without any of the above
        # strong terms. Adding this rescue class.
        "risk assessment",
        "criminal justice risk",
        "recidivism prediction",
        "compas",
    ),
    venue_allowlist=(
        # Fairness-first venues
        "conference on fairness", "facct", "fat*",
        "ethics and information technology",
        "big data and society", "big data & society",
        "ai and society", "ai & society",
        # ML venues (rescue rule — need topic terms too)
        "neural information processing systems", "neurips",
        "international conference on machine learning", "icml",
        "international conference on learning representations", "iclr",
        "aaai conference on artificial intelligence", "aaai",
        "ijcai", "aistats",
        "journal of machine learning research", "jmlr",
        "transactions on machine learning research", "tmlr",
        # NLP venues for bias-in-NLP subthread
        "association for computational linguistics", "acl",
        "empirical methods in natural language processing", "emnlp",
        "naacl",
    ),
    venue_denylist=(
        "journal of chemical", "chemistry of materials",
        "advanced materials", "chemical reviews",
        "the lancet", "new england journal of medicine", "nejm",
        "bmj", "jama",
        "circulation",
        "geoscience", "geochemistry",
        "photonics",
        # Robotics venues — "bias" is usually sensor bias
        "international conference on robotics", "icra",
        "international conference on intelligent robots", "iros",
        # Signal processing — bias / bias-variance
        "ieee transactions on signal processing",
        # Psychology venues — "fairness judgments" here is procedural
        # justice / social psychology, not algorithmic fairness.
        "journal of personality and social psychology",
        "journal of personality",
        "personality and social psychology",
    ),
    field_allowlist=(
        "computer science",
        "social sciences",
        "arts and humanities",
    ),
    field_denylist=(
        "chemistry",
        "materials science",
        "physics and astronomy",
        "earth and planetary sciences",
        "chemical engineering",
        "energy",
        "medicine",   # unless a title-level rescue fires
        "agricultural and biological sciences",
    ),
)


DOMAINS: dict[str, DomainConfig] = {
    "diet": DIET_CONFIG,
    "fairness": FAIRNESS_CONFIG,
}

# Libraries chosen 2026-10-09 (built now or queued for the weekly workflow).
from backend.app.corpus.domains_2026_10 import ALL as _ALL_2026_10  # noqa: E402

DOMAINS.update(_ALL_2026_10)


# --------------------------------------------------------------------------
# Classifier (contribution, not vocabulary)
# --------------------------------------------------------------------------


_TOKEN_RE = re.compile(r"[a-z0-9]+(?:['-][a-z0-9]+)*")
# Sentence splitter: keeps things simple. Splits on period, exclamation,
# question or newline followed by whitespace. Not perfect (medical
# abbreviations, ellipses) but good enough for abstract text where the
# alternative is a heavyweight NLP dep.
_SENT_RE = re.compile(r"(?<=[.!?])\s+|\n+")


def _tokens(text: str) -> list[str]:
    return _TOKEN_RE.findall(text.lower())


def _sentences(text: str) -> list[str]:
    return [s.strip() for s in _SENT_RE.split(text or "") if s.strip()]


def _pair_in_same_sentence(text: str, left_terms: Iterable[str],
                             right_terms: Iterable[str]) -> Optional[tuple[str, str]]:
    """Return (left_hit, right_hit) if any sentence contains a term from
    both lists, else None. Lowercased substring match — same discipline
    as the co-occurrence check."""
    for s in _sentences(text):
        low = s.lower()
        l = next((t for t in left_terms if t in low), None)
        if not l:
            continue
        r = next((t for t in right_terms if t in low), None)
        if r:
            return (l, r)
    return None


def _spans_of(needle: str, tokens: list[str]) -> list[tuple[int, int]]:
    parts = needle.lower().split()
    if not parts:
        return []
    n = len(parts)
    out: list[tuple[int, int]] = []
    for i in range(len(tokens) - n + 1):
        if tokens[i:i + n] == parts:
            out.append((i, i + n))
    return out


def _co_occurs_within(text: str, a: Iterable[str], b: Iterable[str], window: int) -> bool:
    tokens = _tokens(text)
    a_spans = [s for t in a for s in _spans_of(t, tokens)]
    if not a_spans:
        return False
    b_spans = [s for t in b for s in _spans_of(t, tokens)]
    if not b_spans:
        return False
    for a0, a1 in a_spans:
        for b0, b1 in b_spans:
            if min(abs(a0 - b1), abs(b0 - a1)) <= window:
                return True
    return False


def _venue_of(record: dict) -> Optional[str]:
    hv = record.get("host_venue") or record.get("primary_location") or {}
    if isinstance(hv, dict):
        src = hv.get("source") if isinstance(hv.get("source"), dict) else {}
        return (src.get("display_name") if isinstance(src, dict) else None) or hv.get("display_name")
    return None


def _field_of(record: dict) -> Optional[str]:
    pt = record.get("primary_topic") or {}
    if isinstance(pt, dict):
        field = pt.get("field") or {}
        name = field.get("display_name") if isinstance(field, dict) else None
        return name.lower() if isinstance(name, str) else None
    return None


def _venue_hit(venue: Optional[str], hitlist: Iterable[str]) -> bool:
    if not venue:
        return False
    v = venue.lower()
    return any(t in v for t in hitlist)


def classify(record: dict, *, abstract: str, config: DomainConfig) -> tuple[str, str]:
    """Return (label, rationale).

    label ∈ {"on-domain", "off-domain", "borderline"}. Same three-tier
    contract as docs/labelling-rubric.md, adapted per domain.

    Order matches the LLM-calibration classifier's proven precedence:
    venue denylist → field denylist (with title-rescue) → title co-occurrence
    → venue allowlist → abstract co-occurrence → strong-term rescue →
    default-exclude.
    """
    venue = _venue_of(record)
    field = _field_of(record)
    title = record.get("title") or record.get("display_name") or ""
    text = " ".join(filter(None, [title, abstract or ""]))

    title_on_domain = _co_occurs_within(
        title, config.anchor_terms, config.topic_terms, window=config.title_co_window
    )

    if _venue_hit(venue, config.venue_denylist):
        return "off-domain", f"venue in denylist: {venue!r}"
    if field and any(f in field for f in config.field_denylist) and not title_on_domain:
        return "off-domain", f"primary field is off-domain: {field!r}"

    if title_on_domain:
        return "on-domain", "anchor + topic co-occur in title"
    # Strong-term rescue runs BEFORE the venue allowlist so a Lancet
    # paper that has no diet/fairness signal doesn't get promoted to
    # on-domain just for being in Lancet. Strong terms are the paper's
    # OWN vocabulary; venue is context.
    low = text.lower()
    strong = [t for t in config.strong_topic_terms if t in low]
    if strong:
        # If the domain requires paired terms (e.g. diet exposure + hard
        # outcome), a strong-term match alone is not enough. Both sides
        # must appear or the paper drops to borderline / off-domain.
        if config.pair_terms:
            pair = [t for t in config.pair_terms if t in low]
            if pair:
                # STRICTER RULE (Gate-2 followup): the strong term must
                # appear in the TITLE, or co-occur with a pair term in
                # the SAME SENTENCE of the abstract. This catches
                # background-mention false positives where both terms
                # appear in the abstract but in unrelated sentences.
                if config.require_pair_in_title_or_sentence:
                    title_low = (title or "").lower()
                    strong_in_title = next(
                        (t for t in config.strong_topic_terms if t in title_low),
                        None,
                    )
                    if strong_in_title:
                        return "on-domain", (
                            f"strong term in title: {strong_in_title!r} "
                            f"+ pair anywhere: {pair[0]!r}"
                        )
                    sent = _pair_in_same_sentence(
                        text, config.strong_topic_terms, config.pair_terms
                    )
                    if sent:
                        return "on-domain", (
                            f"same-sentence pair: {sent[0]!r} + {sent[1]!r}"
                        )
                    # Both present but in unrelated sentences → borderline.
                    return "borderline", (
                        f"strong+pair present but not in title or same "
                        f"sentence: {strong[0]!r} + {pair[0]!r}"
                    )
                return "on-domain", (
                    f"paired strong terms: {strong[0]!r} + {pair[0]!r}"
                )
            # Half-matches (strong exposure but no outcome, or vice-versa)
            # go to borderline — kept for peripheral evidence, not
            # promoted to core. Also caught by the outcome-only fallback
            # in the next branch.
            return "borderline", (
                f"strong term without required pair: {strong[0]!r}"
            )
        return "on-domain", f"strong in-domain term: {strong[0]!r}"
    # Domain with pair_terms: matching an outcome pair-term alone also
    # only earns borderline (e.g. "all-cause mortality" appearing in a
    # COVID physical-activity paper). Keeps it available for peripheral
    # evidence without falsely promoting to core.
    if config.pair_terms and any(t in low for t in config.pair_terms):
        return "borderline", "pair (outcome) term without required exposure"
    if _co_occurs_within(text, config.anchor_terms, config.topic_terms, config.co_window):
        return "on-domain", (
            f"anchor + topic co-occur within {config.co_window} tokens"
        )
    if _venue_hit(venue, config.venue_allowlist):
        # Venue allowlist now needs a STRONG term to promote — a plain
        # topic mention alone was letting Lancet global-burden papers
        # through as "on-domain" when they aren't diet-mortality
        # research. Without a strong term, the venue merely rescues
        # from off-domain: mark borderline — but only if the paper has
        # ANY domain vocabulary (anchor, topic, or pair term). A pure
        # methods paper published in an allowlisted venue with no domain
        # vocabulary at all (e.g. Higgins et al.'s I² statistic in BMJ)
        # is off-domain, not borderline.
        if any(t in low for t in
               config.anchor_terms + config.topic_terms + config.pair_terms):
            return "borderline", f"venue allowlist + some domain term: {venue!r}"
        return "off-domain", (
            f"venue allowlist but zero domain vocabulary: {venue!r}"
        )

    # A general topic mention alone (e.g. "fairness" in a 1993
    # organizational-psych paper, "equity" in a 1980 social-psych paper)
    # is NOT enough to earn borderline. Borderline requires at least
    # one anchor (a hint that this is ML / diet research at all) OR a
    # venue-allowlist hit (already handled above). Without either, the
    # paper is off-domain by the no-signal→exclude default.
    text_low = text.lower()
    if any(t in text_low for t in config.topic_terms) and \
            any(a in text_low for a in config.anchor_terms):
        return "borderline", "topic + anchor present but not near enough"

    return "off-domain", "no domain signal (default-exclude)"


# --------------------------------------------------------------------------
# Snowball
# --------------------------------------------------------------------------


def _snowball_path(config: DomainConfig) -> Path:
    return DOMAINS_DIR / config.slug / "snowball.json"


def _prelabel_path(config: DomainConfig) -> Path:
    return DOMAINS_DIR / config.slug / "prelabelled.json"


def _audit_path(config: DomainConfig) -> Path:
    return DOMAINS_DIR / config.slug / "audit_sample.md"


def _native_id(oid: str) -> str:
    return oid.rsplit("/", 1)[-1]


def _abstract_of(record: dict) -> str:
    return _reconstruct_abstract(record.get("abstract_inverted_index")) or ""


def _fetch_by_ids(client: OpenAlexClient, ids: list[str], batch: int = 50) -> list[dict]:
    """Bulk-fetch OpenAlex records for a list of W-ids using a single
    filter=ids.openalex:… call per batch. 1 credit per batch of up to 50."""
    out: list[dict] = []
    for i in range(0, len(ids), batch):
        chunk = ids[i:i + batch]
        filt = f"ids.openalex:{'|'.join(chunk)}"
        out.extend(client.raw_works(filter=filt, limit=batch, per_page=batch))
    return out


def snowball(config: DomainConfig, *, hop1_expand: int = 50) -> dict:
    """Two-hop citation walk with per-seed cap, hop-2 control, and a
    global target. Uses `filter=` calls only (1 credit each). All caps
    live on the DomainConfig; the numbers here are just execution.

    Order matches the LLM-calibration snowball:
      1. Fetch top-cited seed pool (config.seed_filter).
      2. Prelabel the pool; keep only on-domain as seeds (up to n_seeds).
      3. HOP 1 — for each seed:
           outbound: metadata for referenced_works (batch)
           inbound:  cites:<seed_id> filter (paginated to per_seed_cap)
         Prelabel; keep on-domain + borderline; enforce per-seed cap.
      4. HOP 2 — for the top-n_expand hop-1 keepers by co-citation
         frequency, repeat the walk with hop2_cap per node.
      5. Stop when global_target reached.

    All raw records + a run ledger written to snowball.json.
    """
    settings = get_settings()
    with OpenAlexClient() as client:
        seed_pool = list(client.raw_works(
            filter=config.seed_filter,
            sort="cited_by_count:desc",
            limit=200,
            per_page=100,
        ))
        # Prelabel to pick on-domain seeds only
        seeds: list[dict] = []
        seen_ids: set[str] = set()
        for rec in seed_pool:
            wid = _native_id(rec.get("id", ""))
            if not wid:
                continue
            label, _ = classify(rec, abstract=_abstract_of(rec), config=config)
            if label == "on-domain":
                seeds.append(rec)
                seen_ids.add(wid)
            if len(seeds) >= config.n_seeds:
                break

        candidates: list[dict] = list(seeds)  # start with the seeds
        rejected: dict[str, dict] = {}        # off-domain nodes we tested,
                                              # kept for the audit sample

        # HOP 1
        hop1_records: dict[str, dict] = {}
        per_seed_kept: Counter[str] = Counter()
        co_citation: Counter[str] = Counter()

        for seed in seeds:
            seed_wid = _native_id(seed.get("id", ""))

            # Outbound: fetch metadata for referenced_works, batched.
            outb_ids = [_native_id(r) for r in (seed.get("referenced_works") or [])
                        if r and _native_id(r) not in seen_ids]
            for rec in _fetch_by_ids(client, outb_ids[:100]):
                wid = _native_id(rec.get("id", ""))
                if not wid or wid in seen_ids or wid in rejected:
                    continue
                label, _ = classify(rec, abstract=_abstract_of(rec), config=config)
                if label == "off-domain":
                    rejected[wid] = rec
                    continue
                if per_seed_kept[seed_wid] >= config.per_seed_cap:
                    break
                hop1_records[wid] = rec
                seen_ids.add(wid)
                per_seed_kept[seed_wid] += 1
                co_citation[wid] += 1

            # Inbound: cites:<seed>, paginated. Ask for MORE than the cap
            # so we see rejects too (for the audit sample). The per-seed
            # cap on kept papers is still enforced below.
            for rec in client.raw_works(
                filter=f"cites:{seed_wid}",
                sort="cited_by_count:desc",
                limit=config.per_seed_cap * 2,
                per_page=50,
            ):
                wid = _native_id(rec.get("id", ""))
                if not wid or wid in seen_ids or wid in rejected:
                    continue
                label, _ = classify(rec, abstract=_abstract_of(rec), config=config)
                if label == "off-domain":
                    rejected[wid] = rec
                    continue
                if per_seed_kept[seed_wid] >= config.per_seed_cap:
                    continue  # keep scanning for more rejects
                hop1_records[wid] = rec
                seen_ids.add(wid)
                per_seed_kept[seed_wid] += 1
                co_citation[wid] += 1

            if len(seen_ids) >= config.global_target:
                break

        candidates.extend(hop1_records.values())

        # HOP 2 — only from top hop-1 keepers, and only enough to fill.
        if len(seen_ids) < config.global_target:
            hop1_by_frequency = sorted(hop1_records.values(),
                                       key=lambda r: -co_citation[_native_id(r.get("id", ""))])
            hop2_records: dict[str, dict] = {}
            for node in hop1_by_frequency[:config.hop2_expand_top_n]:
                node_wid = _native_id(node.get("id", ""))
                kept = 0
                outb_ids = [_native_id(r) for r in (node.get("referenced_works") or [])
                            if r and _native_id(r) not in seen_ids and
                            _native_id(r) not in rejected]
                for rec in _fetch_by_ids(client, outb_ids[:50]):
                    wid = _native_id(rec.get("id", ""))
                    if not wid or wid in seen_ids or wid in rejected:
                        continue
                    label, _ = classify(rec, abstract=_abstract_of(rec), config=config)
                    if label == "off-domain":
                        rejected[wid] = rec
                        continue
                    if kept >= config.hop2_cap:
                        break
                    hop2_records[wid] = rec
                    seen_ids.add(wid)
                    kept += 1
                    if len(seen_ids) >= config.global_target:
                        break
                if len(seen_ids) >= config.global_target:
                    break
            candidates.extend(hop2_records.values())

        ledger = client.credits.as_dict()

    out = {
        "config": {"slug": config.slug, "name": config.name,
                   "n_seeds": len(seeds), "global_target": config.global_target,
                   "per_seed_cap": config.per_seed_cap, "hop2_cap": config.hop2_cap},
        "n_candidates": len(candidates),
        "n_rejected_off_domain": len(rejected),
        "credit_ledger": ledger,
        "records": candidates,
        "rejected_records": list(rejected.values()),
    }
    p = _snowball_path(config)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(out))
    return {
        "slug": config.slug, "n_seeds": len(seeds),
        "n_candidates": len(candidates),
        "n_rejected_off_domain": len(rejected),
        "credits": ledger,
    }


# --------------------------------------------------------------------------
# Prelabel
# --------------------------------------------------------------------------


def prelabel(config: DomainConfig) -> dict:
    """Classify every snowball candidate; persist labels + rationale.

    Also assigns `domain_centrality`: on-domain -> core, borderline ->
    peripheral, off-domain -> dropped. Enforces the corrected rubric's
    default-exclude behaviour.
    """
    payload = json.loads(_snowball_path(config).read_text())
    entries: list[dict] = []
    counts = Counter()
    for rec in payload["records"]:
        wid = _native_id(rec.get("id", ""))
        if not wid:
            continue
        abstract = _abstract_of(rec)
        label, rationale = classify(rec, abstract=abstract, config=config)
        counts[label] += 1
        if label == "off-domain":
            continue
        entries.append({
            "wid": wid,
            "openalex_id": rec.get("id"),
            "title": rec.get("title") or rec.get("display_name"),
            "year": rec.get("publication_year"),
            "doi": rec.get("doi"),
            "venue": _venue_of(rec),
            "field": _field_of(rec),
            "cited_by_count": rec.get("cited_by_count"),
            "abstract": abstract,
            "label": label,
            "rationale": rationale,
            "domain_centrality": "core" if label == "on-domain" else "peripheral",
        })

    # Trim to target size: keep all cores first, then fill with peripherals
    # by cited_by desc — mirrors the LLM-calibration corpus's 109 core /
    # 91 peripheral split logic.
    entries.sort(key=lambda r: (r["domain_centrality"] != "core",
                                 -(r["cited_by_count"] or 0)))
    trimmed = entries[:100]

    out = {
        "slug": config.slug,
        "n_input": payload["n_candidates"],
        "n_pre_dedup": len(entries),
        "n_kept": len(trimmed),
        "counts_by_label": dict(counts),
        "counts_by_centrality": dict(Counter(r["domain_centrality"] for r in trimmed)),
        "entries": trimmed,
    }
    _prelabel_path(config).write_text(json.dumps(out))
    return {k: v for k, v in out.items() if k != "entries"}


# --------------------------------------------------------------------------
# Full-text retrieval
# --------------------------------------------------------------------------


def _paper_for_fulltext(entry: dict) -> "Paper":  # noqa: F821
    """Turn a prelabelled entry into the minimal Paper needed by the
    fulltext helpers. openalex.id is stored as the OpenAlex URL to make
    the DOI-based OA lookups work uniformly."""
    return from_openalex({
        "id": entry["openalex_id"],
        "doi": entry.get("doi"),
        "title": entry.get("title"),
        "publication_year": entry.get("year"),
        "type": "article",
        "cited_by_count": entry.get("cited_by_count"),
        "abstract_inverted_index": None,
    })


_ARXIV_ABS = re.compile(r"arxiv\.org/(?:abs|pdf)/([0-9]{4}\.[0-9]{4,6})")
_ARXIV_OLD = re.compile(r"arxiv\.org/(?:abs|pdf)/([a-z-]+/[0-9]{7})")


def _arxiv_id_from_openalex_record(rec: dict) -> Optional[str]:
    """Scan an OpenAlex work's locations for an arXiv URL and extract
    the arXiv id. Uses data already in the fetch — no extra API call.
    Handles both the modern `NNNN.NNNNN` and old `cs.LG/NNNNNNN` forms.
    """
    urls: list[str] = []
    for loc in (rec.get("locations") or []):
        for k in ("pdf_url", "landing_page_url"):
            u = (loc or {}).get(k)
            if u:
                urls.append(u)
        # `source.display_name` = "arXiv" is another signal, but the id
        # extraction needs a URL either way.
    for u in urls:
        m = _ARXIV_ABS.search(u) or _ARXIV_OLD.search(u)
        if m:
            return m.group(1)
    return None


def _arxiv_id_from_semantic_scholar(doi: str, *, client: httpx.Client) -> Optional[str]:
    """Semantic Scholar externalIds → ArXiv id. Free tier, unauthenticated.
    Returns None on any failure (rate limit, 404, network); the caller
    just falls through to the OA path."""
    if not doi:
        return None
    d = doi
    for pfx in ("https://doi.org/", "http://doi.org/", "doi:"):
        if d.startswith(pfx):
            d = d[len(pfx):]
    try:
        r = client.get(
            f"https://api.semanticscholar.org/graph/v1/paper/DOI:{d}",
            params={"fields": "externalIds"},
        )
        if r.status_code != 200:
            return None
        eids = (r.json().get("externalIds") or {})
        aid = eids.get("ArXiv") or eids.get("arXiv")
        if aid and (_ARXIV_ABS.search(f"arxiv.org/abs/{aid}") or
                    _ARXIV_OLD.search(f"arxiv.org/abs/{aid}")):
            return aid
        return aid or None
    except (httpx.HTTPError, ValueError):
        return None


def retrieve_fulltext_one(e: dict, rec: dict, *, client: httpx.Client,
                          email: Optional[str] = None) -> Optional[str]:
    """Full text for one entry, stored in the shared cache. Returns the
    source tag, or None when only the abstract is available. Free."""
    email = email or UNPAYWALL_EMAIL
    paper = _paper_for_fulltext(e)
    if load_cached_fulltext(paper.id):
        return "cache"
    # DOI-based arXiv id via OpenAlex locations (no API call)
    aid = _arxiv_id_from_openalex_record(rec)
    src_tag = "arxiv-openalex"
    if not aid and e.get("doi"):
        aid = _arxiv_id_from_semantic_scholar(e["doi"], client=client)
        src_tag = "arxiv-s2"
    if aid:
        text = fetch_pdf_text(aid, client=client)
        if text and len(text) >= 3000:
            store_fulltext(paper.id, text)
            return src_tag
    # Fall back to existing arXiv-title-search + OA path
    r1 = retrieve_fulltext(paper, client=client, use_cache=False)
    if not r1.abstract_only:
        return "arxiv-title"
    if e.get("doi"):
        r2 = retrieve_oa_fulltext(paper, email=email, client=client, use_cache=False)
        if not r2.abstract_only:
            return r2.source or "unpaywall"
    return None


def retrieve_fulltext_all(config: DomainConfig, *, email: Optional[str] = None,
                            sample: Optional[int] = None) -> dict:
    """Attempt DOI-based arXiv id → arXiv PDF → Unpaywall → Europe PMC
    for every kept entry. Writes back input_source and abstract_only per
    entry. Free.

    DOI → arXiv id resolution (Raj's Gate-2 requirement):
      1. From OpenAlex `locations` (already fetched — no extra API call)
      2. From Semantic Scholar `externalIds.ArXiv` (one free call each)
      3. No fuzzy title matching — the existing exact-match rule stays.
    Then falls back to `retrieve_oa_fulltext` for non-arXiv papers.
    """
    email = email or UNPAYWALL_EMAIL

    payload = json.loads(_prelabel_path(config).read_text())
    entries = payload["entries"]
    target = entries[:sample] if sample else entries

    # Raw records for arXiv-locations lookup
    raw = json.loads(_snowball_path(config).read_text())
    by_wid = {_native_id(r.get("id", "")): r for r in raw["records"]}

    stats = Counter()
    print(f"[fulltext] {config.slug}: {len(target)} papers — progress every 10.",
          flush=True)
    with httpx.Client(timeout=25.0, follow_redirects=True,
                       headers={"User-Agent": "ResearchMap/0.2 multi-domain"}) as client:
        for i, e in enumerate(target, 1):
            source = None
            try:
                source = retrieve_fulltext_one(e, by_wid.get(e["wid"], {}),
                                               client=client, email=email)
            except Exception as ex:
                # Never let a per-paper failure kill the batch, but do log
                # it so the run report shows how many rows we lost this way.
                stats["exception"] += 1
                print(f"  [{i}] {e['wid']} EXC: {type(ex).__name__}: {ex}",
                      flush=True)
            if source:
                e["input_source"] = "fulltext"
                e["fulltext_source"] = source
                e["abstract_only"] = False
                stats[f"fulltext_{source}"] += 1
            else:
                e["input_source"] = "abstract_only"
                e["abstract_only"] = True
                e["fulltext_source"] = None
                stats["abstract_only"] += 1
            if i % 10 == 0 or i == len(target):
                got = sum(v for k, v in stats.items()
                          if k.startswith("fulltext_"))
                print(f"  [{i}/{len(target)}] fulltext so far: {got} "
                      f"({got/i*100:.0f}%)", flush=True)

    _prelabel_path(config).write_text(json.dumps(payload))
    total_ft = sum(v for k, v in stats.items() if k.startswith("fulltext_"))
    return {
        "slug": config.slug,
        "n_probed": len(target),
        "fulltext_share": total_ft / len(target),
        "by_source": dict(stats),
    }


# --------------------------------------------------------------------------
# Audit sample (15 papers, hard cases flagged)
# --------------------------------------------------------------------------


HARD_MARKERS = {
    "diet-and-mortality": {
        # each: (name, substrings that flag the paper as a hard case)
        "food-chemistry co-mention": ("antioxidant", "polyphenol",
                                       "flavonoid", "extract"),
        "no-outcome / dietary-intake only": ("dietary intake", "food frequency",
                                              "consumption pattern"),
        "animal / cell / mouse study": ("mouse", "mice", "rat ", "murine",
                                         "in vitro", "cell culture"),
        "supplement not diet": ("supplementation", "supplement ", "capsule",
                                 "tablet"),
        "meta-analysis contradiction target": ("meta-analysis", "systematic review",
                                                "meta-regression"),
    },
    "ml-fairness": {
        "statistical bias not group fairness": ("bias-variance",
                                                 "estimator bias",
                                                 "sampling bias",
                                                 "selection bias"),
        "inductive / architectural bias": ("inductive bias",
                                           "architectural bias"),
        "reward / rl bias": ("reward shaping", "exploration bias"),
        "medical-ml with fairness section": ("clinical", "medical imaging",
                                              "hospital"),
        "explanation not fairness": ("interpretability", "explainable",
                                      "shap ", "lime "),
        "impossibility / incompatibility": ("impossibility",
                                             "incompatibility",
                                             "trade-off",
                                             "trade off"),
    },
}


def _hard_flags(entry: dict, config: DomainConfig) -> list[str]:
    text = f"{entry.get('title','')} {entry.get('abstract','')}".lower()
    markers = HARD_MARKERS.get(config.slug, {})
    hits = []
    for name, terms in markers.items():
        if any(t in text for t in terms):
            hits.append(name)
    return hits


def build_audit_sample(config: DomainConfig, *, n: int = 15,
                        seed: int = 42) -> dict:
    """Stratified 15-paper sample: ~7 on-domain (5 easy + 2 hard),
    ~5 borderline (3 easy + 2 hard), ~3 off-domain kept from the
    snowball's raw output (all hard).

    Written as human-readable Markdown at data/domains/<slug>/audit_sample.md.
    """
    payload = json.loads(_prelabel_path(config).read_text())
    kept = payload["entries"]
    # Off-domain rejects live in the snowball's rejected list — the walk
    # filters them out of the corpus but keeps them for exactly this
    # purpose. Re-run classify() on each so the audit shows the rationale.
    raw = json.loads(_snowball_path(config).read_text())
    off_domain = []
    for rec in raw.get("rejected_records", []):
        wid = _native_id(rec.get("id", ""))
        abstract = _abstract_of(rec)
        label, rationale = classify(rec, abstract=abstract, config=config)
        off_domain.append({
            "wid": wid,
            "openalex_id": rec.get("id"),
            "title": rec.get("title") or rec.get("display_name"),
            "year": rec.get("publication_year"),
            "venue": _venue_of(rec),
            "field": _field_of(rec),
            "cited_by_count": rec.get("cited_by_count"),
            "abstract": abstract,
            "label": label,
            "rationale": rationale,
        })

    rng = random.Random(seed)
    cores = [e for e in kept if e["domain_centrality"] == "core"]
    peri = [e for e in kept if e["domain_centrality"] == "peripheral"]

    def pick(pool: list[dict], want_easy: int, want_hard: int) -> list[dict]:
        easy = [e for e in pool if not _hard_flags(e, config)]
        hard = [e for e in pool if _hard_flags(e, config)]
        rng.shuffle(easy); rng.shuffle(hard)
        chosen = easy[:want_easy] + hard[:want_hard]
        # If not enough hard, pad from easy — don't fabricate hardness.
        if len(chosen) < want_easy + want_hard:
            need = want_easy + want_hard - len(chosen)
            chosen.extend([e for e in easy[want_easy:] if e not in chosen][:need])
        return chosen

    sample = []
    sample += pick(cores, 5, 2)
    sample += pick(peri, 3, 2)
    rng.shuffle(off_domain)
    sample += off_domain[:3]

    # Write the markdown
    lines = [
        f"# Audit sample — {config.name}",
        "",
        f"15-paper stratified sample from the {config.slug} snowball, drawn "
        f"deterministically (`seed={seed}`). Read each line, then write "
        "`agree` or `disagree` in the third-to-last column. Any paper with "
        "`hard: [...]` is one the rubric might get wrong for a specific "
        "reason — those are the borders worth checking.",
        "",
        "Discriminator, restated: **contribution, not vocabulary**. See "
        f"`docs/rubrics/{config.slug}.md`.",
        "",
    ]
    for i, e in enumerate(sample, 1):
        hard = _hard_flags(e, config)
        hard_note = f" — **hard**: {', '.join(hard)}" if hard else ""
        lines += [
            f"## {i}. `{e.get('wid','?')}` — {e.get('title') or '(untitled)'}",
            "",
            f"- **Year**: {e.get('year')} · **Venue**: {e.get('venue')} · "
            f"**Cited**: {e.get('cited_by_count')}",
            f"- **Label (heuristic)**: `{e['label']}` "
            f"(`{e.get('domain_centrality') or '—'}`){hard_note}",
            f"- **Rationale**: {e['rationale']}",
            "",
            f"> {(e.get('abstract') or '(no abstract)')[:500].replace(chr(10),' ')}",
            "",
            "- **Reviewer**: agree / disagree — ",
            "- **Note (if disagree)**: ",
            "",
        ]

    md = "\n".join(lines)
    _audit_path(config).write_text(md)

    return {
        "slug": config.slug,
        "n_sample": len(sample),
        "core_in_sample": sum(1 for e in sample if e.get("domain_centrality") == "core"),
        "peripheral_in_sample": sum(1 for e in sample if e.get("domain_centrality") == "peripheral"),
        "off_in_sample": sum(1 for e in sample if e["label"] == "off-domain"),
        "hard_flagged": sum(1 for e in sample if _hard_flags(e, config)),
        "path": str(_audit_path(config).relative_to(REPO_ROOT)),
    }


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def _stage(fn, *args, **kwargs) -> dict:
    print(f"→ {fn.__name__}", flush=True)
    result = fn(*args, **kwargs)
    print(f"  {json.dumps(result, default=str)}")
    return result


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--domain", choices=sorted(DOMAINS), required=True,
                   help="which domain to run")
    p.add_argument("--stage", choices=["snowball", "prelabel", "fulltext",
                                        "audit", "all"], default="all")
    p.add_argument("--fulltext-sample", type=int, default=None,
                   help="only probe this many top-cited papers (Gate-2 projection)")
    args = p.parse_args()
    config = DOMAINS[args.domain]

    if args.stage in ("snowball", "all"):
        _stage(snowball, config)
    if args.stage in ("prelabel", "all"):
        _stage(prelabel, config)
    if args.stage in ("fulltext", "all"):
        _stage(retrieve_fulltext_all, config, sample=args.fulltext_sample)
    if args.stage in ("audit", "all"):
        _stage(build_audit_sample, config)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
