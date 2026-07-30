"""Check whether structural-hole flatness is a fixed-k artifact.

Fixed k caps cluster pairs at k(k-1)/2 regardless of N, so flat yield would
be expected by construction. Re-run the N sweep with k growing as a
function of N (√N and N/10), UNCAPPED, and compare against fixed k=8.
Free — no API calls.
"""

from __future__ import annotations

import math
import statistics as st
import sys
from pathlib import Path

REPO_ROOT = Path("/Users/rajbhise/Downloads/claudecode/ResearchMap")
sys.path.insert(0, str(REPO_ROOT))

import numpy as np  # noqa: E402

from backend.app.reasoning import scorers as S  # noqa: E402
from backend.app.reasoning.corpus_view import load_reasoning_corpus  # noqa: E402
from backend.app.reasoning.scaling_study import subset  # noqa: E402

NS = [40, 60, 80, 100, 113]
DRAWS = 5
SCHEDULES = {
    "fixed k=8": lambda N: 8,
    "k=round(sqrt N)": lambda N: max(2, round(math.sqrt(N))),
    "k=round(N/10)": lambda N: max(2, round(N / 10)),
}


def main() -> int:
    rc = load_reasoning_corpus()
    ids = sorted(rc.papers)
    ft = [p for p in ids if rc.papers[p].input_source == "fulltext"]
    ab = [p for p in ids if rc.papers[p].input_source != "fulltext"]
    ft_ratio = len(ft) / len(ids)

    # precompute subsamples (same draws for every schedule -> comparable)
    draws_by_N = {}
    for N in NS:
        draws = 1 if N >= len(ids) else DRAWS
        n_ft = min(len(ft), round(N * ft_ratio))
        subs = []
        for d in range(draws):
            rng = np.random.default_rng(1000 * N + d)
            keep = (set(ids) if N >= len(ids)
                    else set(rng.choice(ft, n_ft, replace=False).tolist()
                             + rng.choice(ab, min(N - n_ft, len(ab)), replace=False).tolist()))
            subs.append(subset(rc, keep))
        draws_by_N[N] = subs

    print(f"{'schedule':22} " + " ".join(f"N={N:>3}" for N in NS))
    table = {}
    for name, kfn in SCHEDULES.items():
        row = []
        for N in NS:
            k = kfn(N)
            vals = [len(S.score_structural_holes(sub, n_clusters=k, top=None))
                    for sub in draws_by_N[N]]
            m = st.mean(vals); sd = st.pstdev(vals) if len(vals) > 1 else 0.0
            row.append((k, m, sd))
        table[name] = row
        print(f"{name:22} " + " ".join(f"{m:4.1f}(k{k})" for k, m, sd in row))

    # slope p per schedule (N=40 vs 113)
    print("\nlog-log slope p (N=40 -> 113):")
    for name, row in table.items():
        y0, y1 = row[0][1], row[-1][1]
        p = (math.log(max(y1, 1e-9)) - math.log(max(y0, 1e-9))) / (math.log(113) - math.log(40))
        pairs0 = row[0][0] * (row[0][0] - 1) / 2
        pairs1 = row[-1][0] * (row[-1][0] - 1) / 2
        print(f"  {name:22} yield {y0:.1f}->{y1:.1f} (p={p:+.2f}) | cluster-pairs {pairs0:.0f}->{pairs1:.0f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
