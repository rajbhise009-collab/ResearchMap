"""Generates the committed offline seed corpus.

Domain: Transformer-based time-series forecasting.

The corpus is a FIXTURE: every paper is a `seed_sample: true` object with
a `seed:NNNN` ID and no DOI. Nothing here should be confused with a real
publication. The point is to exercise the full pipeline offline against a
domain-consistent, internally-contradictory body of "papers" that will
stress the extraction schema and, later, the reasoning engine.

Regenerate with:
    python -m backend.app.ingestion.seed_generator
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from backend.app.config import REPO_ROOT
from backend.app.models import (
    Claim,
    ClaimType,
    Evidence,
    FutureWork,
    Limitation,
    Methodology,
    Paper,
    PaperExtraction,
    Source,
)


# --- Domain vocabulary ----------------------------------------------------

DATASETS = ["ETTh1", "ETTh2", "ETTm1", "ETTm2", "Electricity", "Traffic", "Weather", "ILI", "Exchange"]

MODEL_FAMILIES = [
    ("Informer", "sparse-attention transformer with ProbSparse self-attention"),
    ("Autoformer", "decomposition transformer with auto-correlation"),
    ("FEDformer", "frequency-enhanced decomposition transformer"),
    ("PatchTST", "patch-based channel-independent transformer"),
    ("Crossformer", "cross-dimension transformer with hierarchical encoder"),
    ("iTransformer", "inverted transformer treating variates as tokens"),
    ("DLinear", "decomposition linear baseline"),
    ("NLinear", "normalization linear baseline"),
    ("TimesNet", "2D-convolutional periodicity-aware model"),
    ("N-BEATS", "residual MLP with basis expansion"),
]

HORIZONS = [96, 192, 336, 720]


@dataclass
class Author:
    surname: str
    first: str

    def format(self) -> str:
        return f"{self.first[0]}. {self.surname}"


AUTHORS = [
    Author("Nakamura", "H"),
    Author("Okafor", "C"),
    Author("Salinas", "M"),
    Author("Petrov", "D"),
    Author("Zhang", "L"),
    Author("Bhatt", "R"),
    Author("Iversen", "K"),
    Author("Rossi", "E"),
    Author("Karolyi", "F"),
    Author("Mensah", "A"),
    Author("Chen", "W"),
    Author("Fischer", "T"),
    Author("Ortega", "P"),
    Author("Dupont", "V"),
    Author("Yamada", "S"),
]

VENUES = ["NeurIPS (Seed Fixture)", "ICML (Seed Fixture)", "ICLR (Seed Fixture)",
          "KDD (Seed Fixture)", "AAAI (Seed Fixture)", "TMLR (Seed Fixture)"]


# --- Paper specifications -------------------------------------------------
# Each spec is one row of the fixture. Every field is chosen so downstream
# reasoning has genuine grist: overlapping methods, contradictory findings,
# common limitations, and future-work threads that later papers do/don't
# follow up on.


@dataclass
class PaperSpec:
    seq: int
    year: int
    model_idx: int  # index into MODEL_FAMILIES
    horizon: int
    datasets: list[str]
    finding: str  # short label used to select claim templates
    author_ixs: list[int]
    citations_in_count: int


# Curated fixture roster. 35 papers spanning 2019–2024, mixing model
# families and datasets so the extraction schema sees varied inputs.
PAPER_SPECS: list[PaperSpec] = [
    # --- Foundational proposals (each family's flagship "seed paper") ---
    PaperSpec(1,  2021, 0, 336, ["ETTh1", "ETTh2", "Electricity", "Weather"], "beats_baselines", [0, 4, 10],   612),
    PaperSpec(2,  2021, 1, 336, ["ETTh1", "ETTm1", "Traffic", "Electricity"], "beats_baselines", [1, 8, 5],   580),
    PaperSpec(3,  2022, 2, 336, ["ETTh1", "ETTh2", "ETTm2", "Weather"],       "beats_baselines", [3, 9, 12],  510),
    PaperSpec(4,  2023, 3, 336, ["ETTh1", "ETTh2", "ETTm1", "ETTm2", "Weather", "Electricity"], "beats_baselines", [2, 11, 7], 720),
    PaperSpec(5,  2023, 4, 336, ["ETTh1", "ETTh2", "Electricity", "Traffic"], "beats_baselines", [6, 13, 3],  340),
    PaperSpec(6,  2024, 5, 336, ["ETTh1", "ETTh2", "Traffic", "Weather"],     "beats_baselines", [4, 12, 14], 220),

    # --- The DLinear-style backlash: linear baselines match/beat transformers ---
    PaperSpec(7,  2022, 6, 336, ["ETTh1", "ETTh2", "ETTm1", "ETTm2", "Electricity", "Traffic", "Weather", "ILI"],
              "linear_beats_transformer", [8, 2, 11], 810),
    PaperSpec(8,  2023, 7, 720, ["ETTh1", "ETTm1", "Electricity"], "linear_beats_transformer", [10, 5, 0], 265),
    PaperSpec(9,  2023, 6, 96,  ["Exchange", "ILI", "Traffic"], "linear_beats_transformer_short", [1, 7, 13], 150),

    # --- Rebuttals / conditional wins: transformers regain the lead ---
    PaperSpec(10, 2023, 3, 336, ["ETTh1", "ETTh2", "ETTm1", "ETTm2"], "transformer_wins_with_patching", [3, 6, 9], 480),
    PaperSpec(11, 2023, 4, 336, ["ETTh1", "Electricity", "Traffic"], "transformer_wins_hierarchical", [12, 4, 8], 210),
    PaperSpec(12, 2024, 5, 336, ["ETTh1", "ETTh2", "ETTm1", "Weather", "Electricity", "Traffic"],
              "transformer_wins_variate_tokens", [4, 12, 0], 340),

    # --- Robustness / distribution shift papers ---
    PaperSpec(13, 2022, 0, 336, ["ETTh1", "ETTh2"], "distribution_shift_degrades", [7, 2, 14], 95),
    PaperSpec(14, 2023, 1, 336, ["Electricity", "Traffic"], "distribution_shift_degrades", [11, 6, 4], 130),
    PaperSpec(15, 2024, 6, 336, ["ETTh1", "Electricity"], "distribution_shift_degrades", [5, 8, 13], 40),

    # --- Long-horizon-specific studies ---
    PaperSpec(16, 2022, 2, 720, ["ETTh1", "ETTh2", "Weather"], "long_horizon_error_accumulates", [9, 3, 10], 175),
    PaperSpec(17, 2023, 3, 720, ["ETTh1", "ETTm1", "Electricity"], "long_horizon_patch_helps", [3, 6, 11], 200),
    PaperSpec(18, 2024, 4, 720, ["ETTh1", "Traffic"], "long_horizon_hierarchical_helps", [6, 14, 0], 55),

    # --- Data efficiency / few-shot ---
    PaperSpec(19, 2023, 3, 336, ["ETTh1"], "few_shot_patching_helps", [2, 12, 5], 145),
    PaperSpec(20, 2024, 5, 336, ["ETTh1", "ETTh2"], "few_shot_variate_helps", [4, 9, 1], 60),
    PaperSpec(21, 2024, 8, 336, ["ETTh1", "Weather"], "few_shot_periodicity_helps", [13, 7, 3], 45),

    # --- Multivariate vs univariate ablations ---
    PaperSpec(22, 2023, 3, 336, ["ETTh1", "ETTh2", "ETTm1", "ETTm2"], "channel_independent_helps", [3, 6, 4], 260),
    PaperSpec(23, 2023, 4, 336, ["Electricity", "Traffic"], "channel_dependent_helps", [12, 8, 10], 90),
    PaperSpec(24, 2024, 5, 336, ["ETTh1", "Weather", "Electricity"], "channel_dependent_helps", [4, 0, 14], 35),

    # --- Frequency / decomposition studies ---
    PaperSpec(25, 2022, 2, 336, ["ETTh1", "ETTh2", "ETTm2"], "frequency_helps_periodic", [9, 3, 7], 165),
    PaperSpec(26, 2023, 8, 336, ["ETTh1", "Weather"], "frequency_helps_periodic", [13, 11, 2], 100),
    PaperSpec(27, 2024, 2, 336, ["ETTh1", "ETTh2"], "frequency_helps_periodic", [9, 5, 8], 30),

    # --- Efficiency-focused (memory / FLOPs) ---
    PaperSpec(28, 2022, 0, 336, ["ETTh1", "Electricity"], "efficiency_sparse_wins", [0, 4, 11], 190),
    PaperSpec(29, 2023, 4, 336, ["ETTh1", "Traffic"], "efficiency_patch_wins", [6, 8, 3], 120),
    PaperSpec(30, 2024, 5, 336, ["Electricity", "Traffic", "Weather"], "efficiency_variate_wins", [4, 12, 1], 40),

    # --- Cross-domain transfer ---
    PaperSpec(31, 2023, 3, 336, ["ETTh1", "Weather", "Electricity"], "transfer_patching_generalises", [3, 6, 14], 85),
    PaperSpec(32, 2024, 5, 336, ["ETTh1", "Traffic", "Exchange"], "transfer_variate_generalises", [4, 12, 7], 25),
    PaperSpec(33, 2024, 8, 336, ["ETTh1", "Weather"], "transfer_periodicity_limited", [13, 10, 3], 15),

    # --- Negative results / null findings ---
    PaperSpec(34, 2024, 3, 336, ["Exchange", "ILI"], "no_improvement_on_low_snr", [6, 8, 5], 20),
    PaperSpec(35, 2024, 6, 336, ["Exchange"], "no_improvement_on_low_snr", [10, 2, 14], 12),
]


# --- Text generation ------------------------------------------------------


FINDING_CLAIMS: dict[str, tuple[ClaimType, str, str]] = {
    # key -> (claim type, claim text template, evidence template)
    "beats_baselines": (
        ClaimType.FINDING,
        "{model} outperforms prior transformer and RNN baselines on {ds_list} at horizon {H}.",
        "Reported MSE reduction of {pct}% versus the strongest prior transformer on {ds_primary} at horizon {H}.",
    ),
    "linear_beats_transformer": (
        ClaimType.FINDING,
        "A simple {model} baseline matches or exceeds contemporary transformer forecasters on {ds_list}.",
        "{model} achieved lower average MSE than five transformer baselines across {n_ds} datasets at horizon {H}.",
    ),
    "linear_beats_transformer_short": (
        ClaimType.FINDING,
        "Linear baselines close the gap with transformers on short-horizon forecasts over {ds_list}.",
        "At horizon 96, {model} was within 3% MSE of the best transformer on {n_ds} datasets.",
    ),
    "transformer_wins_with_patching": (
        ClaimType.FINDING,
        "Patch-based tokenisation restores transformer competitiveness over linear baselines on {ds_list}.",
        "{model} improves MSE by an average of {pct}% over DLinear across {n_ds} datasets.",
    ),
    "transformer_wins_hierarchical": (
        ClaimType.FINDING,
        "Hierarchical cross-dimension attention recovers a transformer lead on {ds_list}.",
        "{model} outperforms DLinear by {pct}% MSE on {ds_primary} at horizon {H}.",
    ),
    "transformer_wins_variate_tokens": (
        ClaimType.FINDING,
        "Treating variates as tokens produces consistent transformer wins on {ds_list}.",
        "{model} beats both PatchTST and DLinear on {n_ds} multivariate benchmarks.",
    ),
    "distribution_shift_degrades": (
        ClaimType.NEGATIVE,
        "Reported gains for {model} do not survive covariate shift between train and test splits on {ds_list}.",
        "Held-out year-splits reduce {model} advantage to within 1% MSE of the DLinear baseline.",
    ),
    "long_horizon_error_accumulates": (
        ClaimType.FINDING,
        "Error accumulation dominates {model} performance at horizon 720 on {ds_list}.",
        "MSE at horizon 720 is {pct}% higher than at horizon 336 for the same {model} configuration.",
    ),
    "long_horizon_patch_helps": (
        ClaimType.FINDING,
        "Patch tokenisation reduces long-horizon error accumulation for {model} on {ds_list}.",
        "{model} shows a {pct}% smaller MSE increase from horizon 336 to 720 than autoregressive transformer baselines.",
    ),
    "long_horizon_hierarchical_helps": (
        ClaimType.FINDING,
        "Hierarchical attention narrows the horizon-720 gap versus horizon-336 for {model} on {ds_list}.",
        "{model} MSE at horizon 720 is {pct}% below the closest transformer baseline on {ds_primary}.",
    ),
    "few_shot_patching_helps": (
        ClaimType.FINDING,
        "Patch-based transformers retain accuracy with 10% of the training data on {ds_list}.",
        "{model} MSE degrades by only {pct}% when trained on 10% of ETTh1, versus 24% for a vanilla transformer.",
    ),
    "few_shot_variate_helps": (
        ClaimType.FINDING,
        "Variate-token transformers generalise from 10% of training data on {ds_list}.",
        "{model} maintains within {pct}% of full-data MSE using 10% of ETTh1 and ETTh2.",
    ),
    "few_shot_periodicity_helps": (
        ClaimType.FINDING,
        "Periodicity-aware convolutional models are data-efficient on {ds_list}.",
        "{model} outperforms transformer baselines when trained on 5% of the data on {ds_primary}.",
    ),
    "channel_independent_helps": (
        ClaimType.FINDING,
        "Channel-independent modelling improves multivariate forecasting accuracy on {ds_list}.",
        "{model} outperforms channel-mixing transformers by {pct}% MSE on {n_ds} multivariate datasets.",
    ),
    "channel_dependent_helps": (
        ClaimType.FINDING,
        "Cross-channel dependencies are essential for accurate forecasts on high-correlation datasets like {ds_list}.",
        "{model} improves MSE by {pct}% over channel-independent PatchTST on {ds_primary}.",
    ),
    "frequency_helps_periodic": (
        ClaimType.FINDING,
        "Frequency-domain decomposition improves forecasting on strongly periodic signals in {ds_list}.",
        "{model} reduces MSE by {pct}% over time-domain baselines on {ds_primary}.",
    ),
    "efficiency_sparse_wins": (
        ClaimType.FINDING,
        "Sparse attention reduces the memory footprint of long-context forecasting on {ds_list}.",
        "{model} uses {pct}% less GPU memory than full-attention transformers at input length 1024.",
    ),
    "efficiency_patch_wins": (
        ClaimType.FINDING,
        "Patching cuts token count and delivers {pct}% faster training on {ds_list}.",
        "Per-epoch training time on {ds_primary} is {pct}% lower for {model} than for autoregressive transformer baselines.",
    ),
    "efficiency_variate_wins": (
        ClaimType.FINDING,
        "Variate-token attention scales sub-quadratically in the number of features on {ds_list}.",
        "{model} attention cost grows with the number of variates rather than the input length, saving {pct}% memory at length 1024.",
    ),
    "transfer_patching_generalises": (
        ClaimType.FINDING,
        "Pretrained patch-transformers transfer to unseen forecasting tasks on {ds_list}.",
        "Zero-shot MSE of {model} pretrained on ETTh1 is within {pct}% of a supervised model on {ds_primary}.",
    ),
    "transfer_variate_generalises": (
        ClaimType.FINDING,
        "Variate-token transformers show positive transfer across domains on {ds_list}.",
        "{model} pretrained on Electricity yields a {pct}% MSE reduction over random init when fine-tuned on {ds_primary}.",
    ),
    "transfer_periodicity_limited": (
        ClaimType.NEGATIVE,
        "Periodicity-aware convolutional models do not transfer across datasets with mismatched dominant frequencies on {ds_list}.",
        "Cross-dataset transfer from ETTh1 to {ds_primary} yields worse MSE than training from scratch for {model}.",
    ),
    "no_improvement_on_low_snr": (
        ClaimType.NEGATIVE,
        "No forecaster in the compared set shows a statistically significant improvement over a naive last-value predictor on {ds_list}.",
        "{model} MSE is within one standard deviation of persistence on the {ds_primary} benchmark.",
    ),
}

LIMITATIONS_POOL: list[tuple[str, str]] = [
    ("Evaluation is restricted to public benchmarks and may not reflect production settings.", "external-validity"),
    ("Reported gains use a single held-out split; results across seeds vary by more than the headline MSE difference.", "statistical-power"),
    ("Hyperparameters are tuned per-dataset, which advantages larger models that can absorb the added capacity.", "hyperparameter-sensitivity"),
    ("Distribution shift between train and test periods is not explicitly modelled.", "distribution-shift"),
    ("Computational cost is reported for a single input length; scaling behaviour is not measured.", "efficiency-measurement"),
    ("Missing-value handling is delegated to preprocessing and not stress-tested.", "missing-data"),
    ("Comparison omits linear baselines that recent work has shown to be competitive.", "baseline-omission"),
    ("Attention weights are not analysed, leaving the interpretability claims unverified.", "interpretability"),
    ("Confidence intervals or standard errors are not reported for the headline metric.", "statistical-reporting"),
    ("The training corpus is limited to a single domain, so cross-domain robustness is not established.", "cross-domain-generalisation"),
]

FUTURE_WORK_POOL: list[str] = [
    "Extending the evaluation to include DLinear and NLinear as baselines.",
    "Studying performance under explicit train/test distribution shift.",
    "Reporting per-seed variance and confidence intervals for the headline metric.",
    "Investigating whether patching interacts with frequency-domain decomposition.",
    "Applying the method to irregularly sampled clinical time series.",
    "Reducing memory usage at input length ≥ 2048 without accuracy loss.",
    "Analysing attention weights to test the interpretability hypothesis.",
    "Pretraining on a mixture of datasets to test transfer.",
    "Combining channel-independent tokenisation with variate-token attention.",
    "Evaluating robustness to missing values and label noise.",
]


def make_paper(spec: PaperSpec) -> tuple[Paper, PaperExtraction]:
    model_name, model_desc = MODEL_FAMILIES[spec.model_idx]
    pid = f"seed:{spec.seq:04d}"
    ds_list = ", ".join(spec.datasets[:3])
    ds_primary = spec.datasets[0]
    pct = 10 + (spec.seq % 25)

    claim_type, claim_tpl, evid_tpl = FINDING_CLAIMS[spec.finding]
    claim_text = claim_tpl.format(
        model=model_name, ds_list=ds_list, H=spec.horizon,
        n_ds=len(spec.datasets), ds_primary=ds_primary, pct=pct,
    )
    evidence_text = evid_tpl.format(
        model=model_name, ds_list=ds_list, H=spec.horizon,
        n_ds=len(spec.datasets), ds_primary=ds_primary, pct=pct,
    )

    # Two limitations and two future-work items, deterministic per paper.
    lim_a = LIMITATIONS_POOL[spec.seq % len(LIMITATIONS_POOL)]
    lim_b = LIMITATIONS_POOL[(spec.seq * 3 + 1) % len(LIMITATIONS_POOL)]
    fw_a = FUTURE_WORK_POOL[spec.seq % len(FUTURE_WORK_POOL)]
    fw_b = FUTURE_WORK_POOL[(spec.seq * 5 + 2) % len(FUTURE_WORK_POOL)]

    title = f"{model_name}: {claim_text.rstrip('.')[:120]}"
    abstract = (
        f"We study long-horizon multivariate forecasting using {model_name}, "
        f"a {model_desc}. On {ds_list}, at horizon {spec.horizon}, "
        f"{claim_text} {evidence_text} "
        f"We discuss two limitations: {lim_a[0]} {lim_b[0]} "
        f"Future work should address {fw_a.lower()} and {fw_b.lower()} "
        "[SEED-FIXTURE — not a real publication]."
    )

    authors = [AUTHORS[i].format() for i in spec.author_ixs]
    venue = VENUES[spec.seq % len(VENUES)]

    paper = Paper(
        id=pid,
        source=Source.SEED,
        source_id=str(spec.seq),
        doi=None,
        title=title,
        abstract=abstract,
        year=spec.year,
        authors=authors,
        venue=venue,
        citations_out=[],  # populated below after all papers exist
        citations_in_count=spec.citations_in_count,
        oa_fulltext_available=False,
        fulltext=None,
    )

    # Extraction bundle — authored ground-truth for downstream tests.
    claims = [
        Claim(id=f"{pid}:c1", paper_id=pid, text=claim_text,
              type=claim_type, confidence=0.75 if claim_type == ClaimType.NEGATIVE else 0.85),
        Claim(id=f"{pid}:c2", paper_id=pid,
              text=f"{model_name} is best characterised as {model_desc}.",
              type=ClaimType.METHOD, confidence=0.9),
    ]
    evidence = [
        Evidence(id=f"{pid}:e1", claim_id=f"{pid}:c1", description=evidence_text, strength=0.8),
    ]
    methods = [
        Methodology(id=f"{pid}:m1", paper_id=pid, name=model_name,
                    description=model_desc, datasets=list(spec.datasets),
                    conditions=[f"horizon={spec.horizon}", "input_length=336"]),
    ]
    limitations = [
        Limitation(id=f"{pid}:l1", paper_id=pid, text=lim_a[0], normalized_category=lim_a[1]),
        Limitation(id=f"{pid}:l2", paper_id=pid, text=lim_b[0], normalized_category=lim_b[1]),
    ]
    future_work = [
        FutureWork(id=f"{pid}:f1", paper_id=pid, text=fw_a),
        FutureWork(id=f"{pid}:f2", paper_id=pid, text=fw_b),
    ]

    extraction = PaperExtraction(
        paper_id=pid,
        claims=claims,
        evidence=evidence,
        methodologies=methods,
        limitations=limitations,
        future_work=future_work,
        extractor="seed-fixture",
    )
    return paper, extraction


def _wire_citations(papers: list[Paper]) -> None:
    """Give later papers citations to plausible predecessors so the
    citation graph has real edges to reason over. Deterministic."""
    by_seq = {int(p.source_id): p for p in papers}
    for seq, p in by_seq.items():
        # Cite the previous 3 lower-seq papers of any family.
        out = []
        for other_seq in range(max(1, seq - 6), seq):
            if other_seq in by_seq:
                out.append(by_seq[other_seq].id)
        p.citations_out = out[-3:]


def write_seed_corpus(seed_dir: Path | None = None) -> tuple[int, int]:
    seed_dir = seed_dir or (REPO_ROOT / "data" / "seed")
    papers_dir = seed_dir / "papers"
    extractions_dir = seed_dir / "extractions"
    papers_dir.mkdir(parents=True, exist_ok=True)
    extractions_dir.mkdir(parents=True, exist_ok=True)

    pairs = [make_paper(spec) for spec in PAPER_SPECS]
    papers = [p for p, _ in pairs]
    _wire_citations(papers)

    for paper, extraction in pairs:
        p_payload = json.loads(paper.model_dump_json())
        p_payload["seed_sample"] = True  # explicit marker
        with (papers_dir / f"{paper.id}.json").open("w", encoding="utf-8") as f:
            json.dump(p_payload, f, indent=2, ensure_ascii=False)
        e_payload = json.loads(extraction.model_dump_json())
        with (extractions_dir / f"{extraction.paper_id}.json").open("w", encoding="utf-8") as f:
            json.dump(e_payload, f, indent=2, ensure_ascii=False)

    return len(papers), sum(1 for _ in extractions_dir.glob("*.json"))


if __name__ == "__main__":
    n_papers, n_extractions = write_seed_corpus()
    print(f"Wrote {n_papers} seed papers and {n_extractions} extractions.")
