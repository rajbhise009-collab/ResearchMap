# Compound-splitter — fire rate is model-specific

## Fact

In the v1.0.0 live run (Gemini 3.6 Flash, 30 papers) the compound
claim splitter (`backend/app/extraction/parse.py`) fired **0 times**.

## This is a property of the model, NOT of the task

Gemini 3.6 Flash *pre-atomizes* compound sentences at generation
time — it follows prompt rule 1 ("one atomic claim per entry") and
emits "performance and calibration both improve with scale" as two
separate claims itself. So by the time the splitter runs, there is
nothing left to split.

The task itself is full of compound claims: the schema pressure-test
measured **58.9% of abstracts** contain a sentence carrying multiple
assertions. The model normalizes them away; the splitter would fire
on a raw compound if one reached it.

## Why the splitter stays

A different or cheaper model that does NOT self-atomize — one that
emits "we show X and demonstrate Y" as a single claim — needs the
splitter. It is a **safety net**, dormant on this model, not dead
code.

Known coverage gap: the splitter currently handles numeric
enumerations (`1) … 2) …`) and semicolon-joined clauses, but **not
bare "X and Y" conjunctions**. On Gemini 3.6 Flash this gap is
invisible because the model splits conjunctions itself. On a model
that doesn't, the gap would matter — see the follow-up below.

## Standing rule: re-measure on model change

**Any change to the extraction model requires re-measuring the
compound-splitter fire rate.** If it stays 0, the model self-atomizes
and the gap is moot. If it rises above 0, inspect whether the
splitter is catching the compounds correctly, and specifically test
bare-conjunction handling — that is the known gap and would need the
splitter extended (deferred until a model actually needs it; do not
build it speculatively).

The fire rate is reported in every live-run report
(`n_split_claims` per paper in `data/live_samples/extraction_run_*.json`).
