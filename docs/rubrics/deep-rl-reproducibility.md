# Labelling rubric — deep-rl-reproducibility

Discriminator: contribution, not vocabulary. Adapted from
`docs/labelling-rubric.md` for deep reinforcement learning, where thousands
of papers apply deep RL to a task without asking how results are measured.

## The three tiers

- **on-domain** (`domain_centrality = core`): the paper's contribution is
  ABOUT how deep-RL results are evaluated, compared or reproduced: studies of
  variance across random seeds, hyperparameter and implementation
  sensitivity, statistical methods for comparing agents, benchmark design,
  failed or successful replications, and arguments about evaluation practice.

- **borderline** (`domain_centrality = peripheral`, KEPT): a deep-RL method or
  benchmark paper with a substantial evaluation or reproducibility section; a
  general ML reproducibility paper with deep-RL case studies.

- **off-domain**: deep RL applied to a task (robotics, games, finance, networking)
  with no evaluation question; RL theory without empirical comparison; the
  words "benchmark" or "reproducible" used in passing.

## How the code applies it

`backend/app/corpus/domains_2026_10.py` (DEEP_RL). On-domain only when a
deep-RL method term AND an evaluation/reproducibility term appear in the
title or in the same sentence of the abstract.

## Check

Blind self-audit, 15 papers, at least 80 % in-or-out agreement, one fix
allowed. Result: `data/domains/deep-rl-reproducibility/audit_result.json`.
