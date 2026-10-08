"""Libraries chosen 2026-10-09 (docs/findings/domain-selection-2026-10-09.md).

Rubrics test CONTRIBUTION, not vocabulary, the same way Diet's does: a paper
is on-domain only when its contribution involves BOTH sides of the
question — the exposure/intervention (strong_topic_terms) AND the outcome it
is studied against (pair_terms) — in the title or in the same sentence of
the abstract. A paper that only mentions the topic in passing (a background
sentence, a list of risk factors, a different sense of the word) stays
borderline or off. Venue/field lists only rescue or veto at the edges.

Registered into corpus.multi_domain.DOMAINS at the end of that module.
"""

from __future__ import annotations

from backend.app.corpus.domain_config import DomainConfig

_NOT_HARD_SCIENCE = ("chemistry", "materials science", "physics and astronomy", "chemical engineering",
                     "energy", "earth and planetary sciences", "mathematics")

SOCIAL_MEDIA = DomainConfig(
    slug="social-media-teen-mental-health",
    name="Social media and adolescent mental health",
    seed_filter=(
        'title_and_abstract.search:("social media" OR "screen time" OR "smartphone use" OR "digital media use" '
        'OR "social networking") AND (adolescent OR adolescents OR teenagers OR youth) AND (depression OR anxiety '
        'OR "mental health" OR "well-being" OR wellbeing OR "self-harm"),type:article|preprint,publication_year:>2013'),
    anchor_terms=("social media", "screen time", "smartphone", "digital media", "social networking", "instagram",
                  "facebook", "online", "internet use"),
    topic_terms=("depression", "depressive", "anxiety", "mental health", "well-being", "wellbeing", "self-harm",
                 "suicidal", "loneliness", "psychological distress", "life satisfaction"),
    strong_topic_terms=("social media use", "screen time", "smartphone use", "digital media use",
                        "digital technology use", "social networking site", "problematic social media use",
                        "problematic smartphone use", "time spent on social media", "social media",
                        "technology use"),
    pair_terms=("depression", "depressive symptoms", "anxiety", "mental health", "well-being", "wellbeing",
                "self-harm", "suicidal", "psychological distress", "loneliness", "life satisfaction",
                "internalizing", "body image"),
    require_pair_in_title_or_sentence=True,
    venue_allowlist=("jama pediatrics", "pediatrics", "journal of adolescent health", "nature human behaviour",
                     "psychological science", "clinical psychological science", "journal of youth and adolescence",
                     "child development", "eclinicalmedicine", "lancet child", "journal of affective disorders",
                     "computers in human behavior", "cyberpsychology", "developmental psychology",
                     "journal of child psychology and psychiatry"),
    venue_denylist=("neural information processing", "icml", "iclr", "acm transactions on",
                    "ieee transactions on", "marketing"),
    field_allowlist=("psychology", "medicine", "social sciences", "neuroscience", "nursing", "health professions"),
    field_denylist=_NOT_HARD_SCIENCE + ("engineering",),
)

NUDGES = DomainConfig(
    slug="nudge-effectiveness",
    name="Nudges and choice architecture",
    seed_filter=(
        'title_and_abstract.search:(nudge OR nudging OR nudges OR "choice architecture" OR "default effect" OR '
        '"default option" OR "behavioural insights" OR "behavioral insights") AND (effectiveness OR '
        '"meta-analysis" OR "field experiment" OR randomized OR randomised OR replication OR "publication bias" '
        'OR "effect size"),type:article|preprint,publication_year:>2009'),
    anchor_terms=("nudge", "nudges", "nudging", "choice architecture", "default", "behavioural insights",
                  "behavioral insights", "behavioral economics", "behavioural economics"),
    topic_terms=("effect", "effectiveness", "behavior change", "behaviour change", "field experiment",
                 "meta-analysis", "trial", "uptake", "compliance", "intervention"),
    # Fixed once after the first prelabel (2026-10-09): classic nudge evidence
    # (automatic 401(k) enrolment, Save More Tomorrow, "Do defaults save
    # lives?") never says "nudge", and generic method words as pair terms
    # ("meta-analysis", "effect size") let methods papers in as borderline.
    # Exposure now names the interventions; the pair names behaviour outcomes.
    strong_topic_terms=("nudge", "nudges", "nudging", "choice architecture", "default effect", "default option",
                        "default options", "automatic enrollment", "automatic enrolment", "opt-out", "opt out",
                        "active choice", "behavioural insights", "behavioral insights", "libertarian paternalism",
                        "social norms intervention", "social norm message", "descriptive norm", "normative message",
                        "commitment device", "save more tomorrow", "reminder letter", "text message reminder",
                        "reminders", "simplification", "behavioral intervention", "behavioural intervention"),
    pair_terms=("behavior change", "behaviour change", "savings", "retirement saving", "enrollment", "enrolment",
                "participation", "organ donation", "vaccination uptake", "energy consumption", "energy use",
                "food choice", "healthy eating", "tax compliance", "charitable giving", "uptake", "take-up",
                "compliance", "decision making", "decisions", "choices"),
    require_pair_in_title_or_sentence=True,
    venue_allowlist=("nature human behaviour", "proceedings of the national academy", "pnas",
                     "behavioural public policy", "journal of behavioral decision making", "management science",
                     "american economic review", "journal of economic psychology", "psychological science",
                     "judgment and decision making", "econometrica", "quarterly journal of economics"),
    venue_denylist=("journal of chemical physics", "physical review", "journal of computational chemistry",
                    "robotics", "ieee transactions on"),
    field_allowlist=("psychology", "economics, econometrics and finance", "social sciences",
                     "business, management and accounting", "decision sciences", "medicine"),
    field_denylist=_NOT_HARD_SCIENCE + ("engineering", "computer science"),
)

MINIMUM_WAGE = DomainConfig(
    slug="minimum-wage",
    name="Minimum wage and employment",
    seed_filter=(
        'title_and_abstract.search:("minimum wage" OR "minimum wages" OR "living wage" OR "wage floor") AND '
        '(employment OR "job loss" OR jobs OR "labor market" OR "labour market" OR hours OR earnings),'
        'type:article|preprint,publication_year:>1990'),
    # Fixed once after the blind audit (2026-10-09, in/out agreement 60%):
    # colloquial "living wage" and a passing "minimum wage" next to the bare
    # word "employment" let sociology and general labour papers in. Pair
    # terms are now the effects the field disputes.
    anchor_terms=("minimum wage", "minimum wages", "minimum-wage", "wage floor", "national living wage"),
    topic_terms=("employment", "jobs", "hours", "earnings", "labor market", "labour market", "disemployment",
                 "teen employment", "low-wage", "wage distribution"),
    strong_topic_terms=("minimum wage", "minimum wages", "minimum-wage", "wage floor", "national living wage"),
    pair_terms=("employment effect", "employment effects", "effect on employment", "effects on employment",
                "employment elasticity", "disemployment", "job loss", "job losses", "teen employment",
                "teenage employment", "youth employment", "labor demand", "labour demand", "hours worked",
                "wage distribution", "wage dispersion", "wage inequality", "spillover effects",
                "low-wage workers", "low-wage employment"),
    require_pair_in_title_or_sentence=True,
    venue_allowlist=("american economic review", "quarterly journal of economics", "journal of political economy",
                     "ilr review", "industrial and labor relations review", "journal of labor economics",
                     "review of economics and statistics", "economic journal", "labour economics",
                     "journal of human resources", "national bureau of economic research", "nber"),
    venue_denylist=("physical review", "chemistry"),
    field_allowlist=("economics, econometrics and finance", "social sciences",
                     "business, management and accounting"),
    field_denylist=_NOT_HARD_SCIENCE + ("engineering", "computer science"),
)

EGO_DEPLETION = DomainConfig(
    slug="ego-depletion",
    name="Ego depletion and the strength model of self-control",
    seed_filter=(
        'title_and_abstract.search:("ego depletion" OR "ego-depletion" OR "self-control depletion" OR '
        '"strength model of self-control" OR "resource depletion" OR "willpower depletion"),'
        'type:article|preprint,publication_year:>1997'),
    anchor_terms=("self-control", "self control", "willpower", "self-regulation", "depletion"),
    # Fixed once after the blind audit (2026-10-09, in/out agreement 67%):
    # "self-control" as a pair term and "motivation"/"persistence" as topic
    # terms let trait self-control and general motivation papers in.
    # Topic and pair terms are now the depletion effect and its paradigm.
    topic_terms=("depletion", "depleted", "depleting", "strength model", "limited resource",
                 "sequential task", "sequential-task"),
    strong_topic_terms=("ego depletion", "ego-depletion", "depletion effect", "strength model",
                        "self-control depletion", "resource depletion", "limited resource", "depleted"),
    pair_terms=("stroop", "handgrip", "sequential task", "sequential-task", "second task", "subsequent task",
                "subsequent self-control", "glucose", "registered replication", "replication",
                "self-control failure", "self-control performance"),
    require_pair_in_title_or_sentence=True,
    venue_allowlist=("psychological science", "journal of personality and social psychology",
                     "perspectives on psychological science", "psychological bulletin",
                     "personality and social psychology", "journal of experimental social psychology",
                     "social psychological and personality science", "frontiers in psychology", "collabra",
                     "advances in methods and practices", "motivation science"),
    venue_denylist=("physical review", "ecology", "fisheries", "resource management"),
    field_allowlist=("psychology", "neuroscience", "social sciences", "medicine"),
    field_denylist=_NOT_HARD_SCIENCE + ("engineering", "computer science", "environmental science",
                                        "agricultural and biological sciences"),
)

GROWTH_MINDSET = DomainConfig(
    slug="growth-mindset",
    name="Growth-mindset interventions",
    seed_filter=(
        'title_and_abstract.search:("growth mindset" OR "mindset intervention" OR "fixed mindset" OR '
        '"implicit theories of intelligence" OR "implicit theories of ability"),'
        'type:article|preprint,publication_year:>1997'),
    # Fixed once after the blind audit (2026-10-09, in/out agreement 67%):
    # bare "mindset(s)" matched auditors' and entrepreneurs' mindsets, and the
    # generic pair term "intervention" let a passing mention count. Exposure
    # is now the implicit-theories vocabulary; pair terms are learning and
    # achievement outcomes; business/accounting is vetoed.
    anchor_terms=("growth mindset", "fixed mindset", "implicit theories", "implicit theory",
                  "beliefs about intelligence", "mindset intervention", "incremental theory", "entity theory",
                  "intelligence mindset"),
    topic_terms=("achievement", "academic", "grades", "performance", "students", "motivation",
                 "learning", "test scores"),
    strong_topic_terms=("growth mindset", "fixed mindset", "mindset intervention", "growth-mindset",
                        "implicit theories of intelligence", "implicit theory of intelligence",
                        "incremental theory", "entity theory", "beliefs about intelligence",
                        "malleability of intelligence", "intelligence mindset", "ability mindset"),
    pair_terms=("achievement", "academic achievement", "academic performance", "grades", "gpa",
                "test scores", "learning outcomes", "math", "mathematics", "course", "students",
                "school performance", "educational attainment"),
    require_pair_in_title_or_sentence=True,
    venue_allowlist=("nature", "psychological science", "child development", "journal of educational psychology",
                     "educational psychologist", "contemporary educational psychology",
                     "journal of personality and social psychology", "psychological bulletin", "aera open",
                     "learning and instruction", "perspectives on psychological science"),
    venue_denylist=("entrepreneurship", "marketing", "physical review"),
    field_allowlist=("psychology", "social sciences", "neuroscience", "medicine"),
    field_denylist=_NOT_HARD_SCIENCE + ("engineering", "computer science",
                                        "business, management and accounting"),
)

DEEP_RL = DomainConfig(
    slug="deep-rl-reproducibility",
    name="Deep reinforcement learning: evaluation and reproducibility",
    seed_filter=(
        'title_and_abstract.search:("deep reinforcement learning" OR "deep RL") AND (reproducibility OR '
        'reproducible OR benchmark OR "evaluation protocol" OR "statistical significance" OR "random seeds" OR '
        'hyperparameter OR "continuous control"),type:article|preprint,publication_year:>2015'),
    anchor_terms=("reinforcement learning", "deep rl", "policy gradient", "q-learning", "actor-critic"),
    # Fixed once after the blind audit (2026-10-09, in/out agreement 53%):
    # "generalization"/"evaluation" in a title and the ML-venue rescue let RL
    # method papers in. Topic and pair terms are now evaluation and
    # reproducibility practice only; no venue rescue.
    topic_terms=("reproducibility", "reproducible", "benchmarking", "benchmark suite", "evaluation protocol",
                 "statistical significance", "random seeds", "reliable evaluation", "hyperparameter sensitivity",
                 "implementation details"),
    strong_topic_terms=("deep reinforcement learning", "deep rl", "proximal policy optimization",
                        "soft actor-critic", "deep q-network", "policy optimization", "continuous control",
                        "mujoco", "atari"),
    pair_terms=("reproducibility", "reproducible", "random seeds", "statistical significance",
                "evaluation protocol", "evaluation methodology", "variance across runs", "hyperparameter sensitivity",
                "implementation details", "confidence intervals", "reliable evaluation", "replication"),
    require_pair_in_title_or_sentence=True,
    venue_allowlist=(),
    venue_denylist=("physical review", "chemistry"),
    field_allowlist=("computer science", "engineering", "mathematics"),
    field_denylist=("chemistry", "materials science", "physics and astronomy", "medicine", "earth and planetary sciences"),
)

MICROPLASTICS = DomainConfig(
    slug="microplastics-health",
    name="Microplastics and human health",
    seed_filter=(
        'title_and_abstract.search:(microplastic OR microplastics OR nanoplastic OR nanoplastics) AND ("human health" '
        'OR "human exposure" OR toxicity OR "health risk" OR "risk assessment" OR placenta OR blood),'
        'type:article|preprint,publication_year:>2014'),
    anchor_terms=("microplastic", "microplastics", "nanoplastic", "nanoplastics", "plastic particles"),
    # Fixed once after the blind audit (2026-10-09, in/out agreement 60%):
    # "toxicity", "oxidative stress" and "inflammation" let fish and zebrafish
    # toxicity in as core. Topic and pair terms are now human exposure and
    # human health only.
    topic_terms=("human health", "human exposure", "humans", "health risk", "drinking water", "seafood",
                 "placenta", "human blood", "human body", "food"),
    strong_topic_terms=("microplastic", "microplastics", "nanoplastic", "nanoplastics", "micro- and nanoplastics",
                        "plastic particles"),
    pair_terms=("human health", "human exposure", "human health risk", "human risk assessment", "human cells",
                "human tissue", "human tissues", "human blood", "human placenta", "human body", "human intake",
                "dietary exposure", "inhalation exposure", "drinking water", "table salt", "seafood consumption",
                "food consumption", "exposure to humans", "detected in human"),
    require_pair_in_title_or_sentence=True,
    venue_allowlist=("environmental science & technology", "environment international", "science of the total environment",
                     "journal of hazardous materials", "environmental health perspectives", "nature", "science"),
    venue_denylist=("physical review",),
    field_allowlist=("environmental science", "medicine", "pharmacology, toxicology and pharmaceutics",
                     "biochemistry, genetics and molecular biology", "chemistry"),
    field_denylist=("physics and astronomy", "mathematics", "computer science", "economics, econometrics and finance"),
)

ALL = {"social-media": SOCIAL_MEDIA, "nudges": NUDGES, "minwage": MINIMUM_WAGE,
       "ego": EGO_DEPLETION, "mindset": GROWTH_MINDSET, "deeprl": DEEP_RL,
       "microplastics": MICROPLASTICS}

# Health or social domains carry a plain "not advice" note, as Diet does.
NOT_ADVICE = {
    "social-media-teen-mental-health": (
        "Research-literature analysis, not medical, parenting or mental-health advice. If you or a young "
        "person you know is struggling, talk to a doctor or a local support service."),
    "nudge-effectiveness": "Research-literature analysis, not policy or professional advice.",
    "minimum-wage": "Research-literature analysis, not economic, policy or employment advice.",
    "ego-depletion": None,
    "growth-mindset": "Research-literature analysis, not educational or parenting advice.",
    "deep-rl-reproducibility": None,
    "microplastics-health": ("Research-literature analysis, not medical or exposure advice. Take health "
                             "concerns to a clinician."),
}
