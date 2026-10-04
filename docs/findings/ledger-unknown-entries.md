# Ledger "unknown" entries — what wrote them

**2026-10-04.** Free audit; no API calls. Numbers below are generated
from `data/ledger_audit.json` and `data/spend_ledger.json` by
`python -m backend.app.corpus.doc_numbers` (the audit itself is
`python -m backend.app.corpus.ledger_audit`).

**In one line:** the ledger's `unknown`-stage entries were written by a
unit test that drives the Gemini client through a fake network
connection. They were never billed calls. The 190 that can be proven so
are removed by one appended correction entry; the other 10 stay counted.

## What the entries look like

<!-- gen:unknown -->
- `unknown`-stage entries: **200**, ₹0.50 in total.
- All 200 carry the mock-test signature (5 prompt tokens, 3 output tokens, 0 thinking tokens).
- Proven mock (signature + burst of exactly 10 inside one second): **190** entries, ₹0.48, in 19 bursts.
- Not proven, so still counted: **10** entries (₹0.03).
- Ledger before correction: ₹921.27; after the appended correction: **₹920.79**.
<!-- /gen:unknown -->

Every one is recorded as model `gemini-3.6-flash`, `batch=false`.

## Where they came from

`backend/tests/extraction/test_llm_client.py` builds a `GeminiLLMClient`
with `api_key="fake"` and an `httpx.MockTransport`, so no request leaves
the machine. Its fake 200 response carries
`usageMetadata: {promptTokenCount: 5, candidatesTokenCount: 3}`. The
client records every 200 to the spend ledger, and no run context is set
in those tests, so the stage is the client's default, `unknown`.

Until iteration 4 the test suite had no ledger isolation, so every run of
that file wrote to the real `data/spend_ledger.json`. Measured in this
audit with a counting hook on `SpendLedger.record` (against a temporary
ledger): **one run of `test_llm_client.py` records exactly 10 entries,
all with stage `unknown`, model `gemini-3.6-flash`, 5 prompt tokens and 3
output tokens.** No real call made by this codebase has a prompt that
short; the smallest non-`unknown` entry in the ledger has 162 prompt
tokens.

## What counts as proven

An entry is treated as proven mock only if it has the exact signature
above AND sits in a burst of exactly 10 identical entries spanning under
one second. Ten real network round-trips to a reasoning model cannot
complete in under a second; the proven bursts each span 0.02–0.04 s.

One burst of 10 (ledger entries 554–563, 2026-09-29 14:51) has the same
signature but spans 1.7 s, so it does not meet the criterion set before
looking. It is very probably the same test run on a slower start, but it
is not proven, so it stays counted.

## The correction

One entry with stage `correction_mock_test_entries` was appended to the
ledger. Its cost is the negative of the 190 proven entries' cost, and it
lists their indices (`corrects_indices`) and points here. No existing
entry was edited or removed.

## What changed so it cannot recur

- `backend/tests/conftest.py` points `SPEND_LEDGER_PATH` and
  `SPEND_PROJECTIONS_PATH` at a temporary directory for every test, and
  the default `SpendLedger()` reads that variable.
- A session-wide guard fingerprints the real ledger and projection log
  before the test run and fails the run if either changed.

## Earlier descriptions

Earlier docs described these entries as "embedding calls via generate"
(`multi-domain.md`, first version) and as "tests + probes"
(`ledger-reconciliation-2026-10-02.md`). Neither is supported: embedding
calls go to a different endpoint and were not ledgered at all before
iteration 5, and no probe code path in this repository makes a 5-token
call. Both docs now point here.

## What remains unexplained

The ledger, after this correction, still records more than Google's
billing console showed when last checked (₹302, read 2026-10-02, per
`ledger-reconciliation-2026-10-02.md`). The ₹0.48 removed here explains
almost none of that gap. Console reporting lag is the remaining candidate;
it has not been tested. The project keeps budgeting against the ledger,
the higher of the two.
