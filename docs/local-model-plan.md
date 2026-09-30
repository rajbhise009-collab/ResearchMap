# Local-model extraction — plan (no test run in this iteration)

**Machine measured 2026-09-30:** 8 GB RAM. `ollama` is installed
(`/usr/local/bin/ollama`) but **no models are pulled**. Per the run
brief I did not download models myself — sending a multi-GB pull
against a 5-hour session is a decision Raj should make interactively.
This document is the recipe so a follow-up run can execute the test
directly.

## RAM-appropriate model choices

On 8 GB total RAM, macOS reserves ~2 GB for the OS + WindowServer.
Usable headroom for a model is ~5-6 GB. Q4_K_M quantisation of a
small open model fits; anything ≥ 8B at Q4 tips into swap on this
machine.

| model | class | size on disk | why | verdict |
|:--|:--|--:|:--|:--|
| `llama3.2:3b-instruct-q4_K_M` | 3B instruct | ~2.0 GB | fits headroom with room for context tokens | **first choice for abstracts** |
| `phi3:3.8b-mini-4k-instruct-q4_K_M` | 3.8B instruct | ~2.3 GB | Microsoft's small model, decent JSON discipline | second choice |
| `qwen2.5:3b-instruct-q4_K_M` | 3B instruct | ~1.9 GB | usually good structured-output adherence | third choice |
| `llama3.1:8b-instruct-q4_K_M` | 8B instruct | ~4.9 GB | on the edge of 8 GB machines; swap risk | probably rules out for full text on this machine |

Full-text extraction is the risky test — a v1.1.0 prompt with a 10-15k-
token paper body plus the schema block puts context above 16k tokens.
8B at Q4 with 16k context ≈ 6-7 GB peak → this 8 GB machine will swap
heavily. Expect the abstract test to work and the full-text test to
either abort (per the run brief's swap-abort rule) or produce
truncated output.

## Install and pull

```bash
# Ollama itself is already installed. Start the local server first:
ollama serve   # runs in the background; new terminal tab

# Pull the abstract-first model (~2 GB, 3-5 min on a good connection):
ollama pull llama3.2:3b-instruct-q4_K_M

# (Optional) full-text-test model:
ollama pull llama3.1:8b-instruct-q4_K_M   # ~5 GB
```

## What the test would measure

Same 20 papers already extracted by Gemini (see
`data/domains/*/prelabelled.json` for input_source labels — pick 10
abstract-only, 10 full-text). Same v1.1.0 prompt
(`backend/app/extraction/prompts/v1.1.0/extract.md`). Same JSON schema
(`backend/app/models/schemas.py::PaperExtraction`).

Measured per paper:
1. **first-attempt JSON validity** — did the raw output parse without a
   retry?
2. **enum adherence** — the flash-lite failure mode was inventing
   values for `Claim.type` ("finding" | "method" | "theoretical" |
   "negative") and `Limitation.source_scope`
   ("own_work" | "prior_work"). Count invented enums.
3. **counts vs Gemini** — number of claims / limitations /
   future-work items per paper, side-by-side.
4. **`source_scope` agreement** — for shared limitations, do the two
   models agree on own_work vs prior_work?
5. **peak resident memory** (via `ps -o rss=` on the ollama process) —
   flag if > 6 GB.
6. **time per paper** — wall clock for abstract vs full-text.

## Safety rules

- Abort if swap grows > 500 MB during a single paper (macOS: watch
  `sysctl vm.swapusage` before/after).
- Abort if the machine becomes unresponsive to a heartbeat script.
- Local outputs land under `data/local-model-outputs/<model>/` —
  NEVER overwrite the cached Gemini extractions under
  `data/cache/extractions/`.
- Free — no billed calls. This test does not touch the SpendLedger.

## Deliverable

`docs/findings/local-model-feasibility.md` with a plain verdict:
- **viable for abstracts** / **viable for full text** / **not viable**.
- Numbers behind the verdict (JSON validity %, enum-invention rate,
  count-agreement with Gemini, peak RAM, seconds/paper).
- On an 8 GB machine expect: abstracts viable with a 3B model,
  full-text bounded or not viable; report exactly what the machine
  actually did.

Not run in this iteration — no model pulled, no test executed.
