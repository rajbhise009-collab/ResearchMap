# Labelling rubric — microplastics-health

Discriminator: contribution, not vocabulary. Adapted from
`docs/labelling-rubric.md` for microplastics and human health, where most
microplastics papers are about oceans, soils or wildlife.

## The three tiers

- **on-domain** (`domain_centrality = core`): the paper's contribution is
  ABOUT micro- or nanoplastics and HUMAN health or exposure: detection in
  human tissue, blood or placenta; human dietary or inhalation exposure
  estimates; toxicity in human cells or relevant models; risk assessment for
  people; and disputes over measurement and contamination.

- **borderline** (`domain_centrality = peripheral`, KEPT): animal toxicity with
  an explicit human-relevance argument; environmental occurrence in drinking
  water or food with an exposure estimate; reviews spanning ecosystems and
  people.

- **off-domain**: marine or soil ecology with no human question; polymer
  chemistry; waste management and recycling policy.

## How the code applies it

`backend/app/corpus/domains_2026_10.py` (MICROPLASTICS): a micro/nanoplastic
term AND a human-health or exposure term in the title or the same sentence.

## Check

Blind self-audit, 15 papers, at least 80 % in-or-out agreement, one fix
allowed. Result: `data/domains/microplastics-health/audit_result.json`.
