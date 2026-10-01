"""Weekly refresh — find new OpenAlex works worth looking at.

Per library this module runs two kinds of free OpenAlex queries:

1. **cites-both of a confirmed-genuine contradiction pair**: works
   published in the last ~10 days that cite BOTH papers in a pair.
   A later paper discussing both sides is the single clearest signal
   that the question is alive.

2. **cites of a paper behind an orphaned future-work item**: works
   published in the last ~10 days that cite the paper whose
   "what should be studied next" is still unaddressed. New citations
   are the plausible place for someone to have picked it up.

The output is a list of candidate works per library — never a corpus
addition, never auto-published. The GitHub Actions workflow turns the
list into a single Issue per run and stops.

Honesty rules:
- "Flagged" NEVER means "confirmed". The issue body states this.
- The 4-pass dedupe is applied against the library AND among
  candidates so one work does not appear twice.
- Only free OpenAlex is used. One credit per query. No LLM.
- The daily publication-date filter is cheap and well-supported on the
  free tier; we use `from_publication_date` and `to_publication_date`.

Verified against the live free OpenAlex 2026-10-01: `cites:W_A,cites:W_B`
is AND (one credit); `from_publication_date=YYYY-MM-DD` plus a `cites:`
is one credit per combined filter. The daily-quota hit (10k requests
per day on free tier) is way beyond this workflow's needs.
"""

from __future__ import annotations

import datetime
import json
import os
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Iterable, Protocol

import httpx

OA_BASE = "https://api.openalex.org"
DEFAULT_LOOKBACK_DAYS = 10


# ----- data classes --------------------------------------------------------


@dataclass
class Candidate:
    """One flagged work. Not a corpus addition — a lead for the next
    human/pipeline step. `reason` records WHY it was flagged so the
    issue body can show it."""
    wid: str
    title: str
    year: int | None
    doi: str | None
    oa_url: str | None
    reason: str
    # Which library this candidate was found for.
    library: str


@dataclass
class RunResult:
    date: str
    libraries: dict[str, list[Candidate]] = field(default_factory=dict)
    credits_used: int = 0
    errors: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "date": self.date,
            "credits_used": self.credits_used,
            "errors": self.errors,
            "libraries": {k: [asdict(c) for c in v]
                           for k, v in self.libraries.items()},
        }

    def all_candidates(self) -> list[Candidate]:
        return [c for cs in self.libraries.values() for c in cs]


# ----- OpenAlex access -----------------------------------------------------


class OpenAlexClient(Protocol):
    def get(self, path: str, params: dict) -> dict: ...


class LiveOpenAlexClient:
    """Thin wrapper for the live service. Raises on missing API key
    (the free tier has required `?api_key=…` since 2026-02-13).
    Returns the JSON body for `/works?...`.
    """

    def __init__(self, api_key: str, client: httpx.Client | None = None):
        if not api_key:
            raise RuntimeError(
                "OPENALEX_API_KEY is required (OpenAlex retired the "
                "polite-pool mailto on 2026-02-13; unauthenticated "
                "requests return 409).")
        self._key = api_key
        self._client = client or httpx.Client(timeout=30.0)
        self.requests_made = 0

    def get(self, path: str, params: dict) -> dict:
        self.requests_made += 1
        p = dict(params)
        p["api_key"] = self._key
        r = self._client.get(f"{OA_BASE}{path}", params=p)
        r.raise_for_status()
        return r.json()


# ----- the two query shapes ------------------------------------------------


def _wid(pid: str) -> str:
    return (pid or "").rsplit("/", 1)[-1].rsplit(":", 1)[-1]


def _window(ref_date: datetime.date, lookback_days: int) -> tuple[str, str]:
    """Returns (from_date, to_date) as YYYY-MM-DD. OpenAlex's
    `publication_date` filter is inclusive on both ends."""
    start = ref_date - datetime.timedelta(days=lookback_days)
    return start.isoformat(), ref_date.isoformat()


def _flatten_work(w: dict) -> tuple[str, str, int | None, str | None, str | None]:
    """OpenAlex work → (wid, title, year, doi, oa_url)."""
    wid = _wid(w.get("id", ""))
    title = w.get("display_name") or ""
    year = w.get("publication_year")
    doi = (w.get("doi") or "").removeprefix("https://doi.org/") or None
    oa_url = (((w.get("primary_location") or {}).get("source") or {})
                .get("homepage_url"))
    return wid, title, year, doi, oa_url


def query_cites_both_recent(
    client: OpenAlexClient, a_id: str, b_id: str, *,
    ref_date: datetime.date, lookback_days: int = DEFAULT_LOOKBACK_DAYS,
    top_n: int = 10,
) -> list[dict]:
    """Works citing both sides AND published in the last ~N days."""
    a_wid, b_wid = _wid(a_id), _wid(b_id)
    fd, td = _window(ref_date, lookback_days)
    params = {
        "filter": f"cites:{a_wid},cites:{b_wid},"
                   f"from_publication_date:{fd},to_publication_date:{td}",
        "per-page": str(top_n + 2),
        "sort": "cited_by_count:desc",
        "select": ("id,doi,display_name,publication_year,primary_location,"
                    "cited_by_count"),
    }
    body = client.get("/works", params)
    out = []
    for w in body.get("results") or []:
        wid = _wid(w.get("id", ""))
        if wid in (a_wid, b_wid):
            continue
        out.append(w)
    return out[:top_n]


def query_cites_recent(
    client: OpenAlexClient, source_id: str, *,
    ref_date: datetime.date, lookback_days: int = DEFAULT_LOOKBACK_DAYS,
    top_n: int = 10,
) -> list[dict]:
    """Works citing `source_id` AND published in the last ~N days."""
    swid = _wid(source_id)
    fd, td = _window(ref_date, lookback_days)
    params = {
        "filter": f"cites:{swid},"
                   f"from_publication_date:{fd},to_publication_date:{td}",
        "per-page": str(top_n + 2),
        "sort": "cited_by_count:desc",
        "select": ("id,doi,display_name,publication_year,primary_location,"
                    "cited_by_count"),
    }
    body = client.get("/works", params)
    return [w for w in (body.get("results") or [])
             if _wid(w.get("id", "")) != swid][:top_n]


# ----- dedupe --------------------------------------------------------------


def _normalise_title_key(title: str) -> str:
    import re
    t = (title or "").lower()
    t = re.sub(r"[^a-z0-9 ]+", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def _dedupe_candidates(cands: list[Candidate]) -> list[Candidate]:
    """4-pass dedupe amongst candidates: (1) same wid, (2) same DOI,
    (3) same normalised title + same year, (4) same normalised title
    (any year — for arxiv/published pairs)."""
    seen_wid: set[str] = set()
    seen_doi: set[str] = set()
    seen_ty: set[tuple[str, int | None]] = set()
    seen_t: set[str] = set()
    out: list[Candidate] = []
    for c in cands:
        if c.wid in seen_wid:
            continue
        if c.doi and c.doi in seen_doi:
            continue
        t = _normalise_title_key(c.title)
        if (t, c.year) in seen_ty:
            continue
        if t and t in seen_t:
            # Same title regardless of year — handles arxiv/published
            # sibling case. Only applied for titles ≥ 25 chars so we
            # don't collapse a handful of distinct one-word papers.
            if len(t) >= 25:
                continue
        seen_wid.add(c.wid)
        if c.doi:
            seen_doi.add(c.doi)
        seen_ty.add((t, c.year))
        if t:
            seen_t.add(t)
        out.append(c)
    return out


def _library_known_set(papers_json: Path) -> tuple[set[str], set[str], set[str]]:
    """Returns (wid_set, doi_set, title_keys) for the library."""
    wids, dois, titles = set(), set(), set()
    if not papers_json.exists():
        return wids, dois, titles
    data = json.loads(papers_json.read_text())
    for p in data.get("items", []):
        if p.get("wid"):
            wids.add(_wid(p["wid"]))
        if p.get("doi"):
            dois.add(p["doi"].removeprefix("https://doi.org/"))
        if p.get("title"):
            titles.add(_normalise_title_key(p["title"]))
    return wids, dois, titles


def _drop_known_to_library(
    cands: list[Candidate], papers_json: Path,
) -> list[Candidate]:
    """Dedupe candidates against what's already in the library's
    papers.json: by wid, by DOI, or by normalised-title match."""
    wids, dois, titles = _library_known_set(papers_json)
    out = []
    for c in cands:
        if c.wid in wids:
            continue
        if c.doi and c.doi in dois:
            continue
        if c.title and _normalise_title_key(c.title) in titles:
            continue
        out.append(c)
    return out


# ----- per-library runner --------------------------------------------------


def _candidates_for_library(
    client: OpenAlexClient, slug: str, snapshot_root: Path,
    audit_path: Path, opportunities_path: Path,
    ref_date: datetime.date, lookback_days: int, top_n: int,
) -> tuple[list[Candidate], int, list[str]]:
    """Returns (candidates_after_dedupe, credits_used, errors)."""
    errors: list[str] = []
    credits = 0
    found: list[Candidate] = []

    # 1. cites-both over genuine pairs
    if audit_path.exists():
        audit = json.loads(audit_path.read_text())
        for v in audit.get("verdicts", []):
            if v.get("verdict") != "genuine":
                continue
            try:
                works = query_cites_both_recent(
                    client, v["a_paper_id"], v["b_paper_id"],
                    ref_date=ref_date, lookback_days=lookback_days,
                    top_n=top_n,
                )
                credits += 1
            except Exception as e:
                errors.append(
                    f"[{slug}] cites-both {_wid(v['a_paper_id'])}+"
                    f"{_wid(v['b_paper_id'])}: {e!r}")
                continue
            topic = v.get("topic") or "unknown topic"
            for w in works:
                wid, title, year, doi, oa_url = _flatten_work(w)
                found.append(Candidate(
                    wid=wid, title=title, year=year, doi=doi, oa_url=oa_url,
                    reason=f"cites both sides of '{topic}'",
                    library=slug,
                ))

    # 2. cites of orphan-future-work source papers
    if opportunities_path.exists():
        opp = json.loads(opportunities_path.read_text())
        for card in opp.get("items", []):
            kind = (card.get("consumer") or {}).get("kind_id", "")
            if kind not in ("unfollowed_future_work", "orphaned_future_work"):
                continue
            sp = card.get("supporting_papers") or []
            if not sp:
                continue
            spid = sp[0].get("paper_id") if isinstance(sp[0], dict) else sp[0]
            if not spid:
                continue
            try:
                works = query_cites_recent(
                    client, spid, ref_date=ref_date,
                    lookback_days=lookback_days, top_n=top_n,
                )
                credits += 1
            except Exception as e:
                errors.append(
                    f"[{slug}] cites-orphan-fw {_wid(spid)}: {e!r}")
                continue
            headline = (card.get("consumer") or {}).get("headline", "")[:80]
            for w in works:
                wid, title, year, doi, oa_url = _flatten_work(w)
                found.append(Candidate(
                    wid=wid, title=title, year=year, doi=doi, oa_url=oa_url,
                    reason=(f"cites the paper behind the orphaned "
                            f"future-work item '{headline}'"),
                    library=slug,
                ))

    # Dedupe among the candidates…
    found = _dedupe_candidates(found)
    # …and against anything the library already knows about.
    found = _drop_known_to_library(
        found, snapshot_root / "library" / slug / "papers.json")
    # LLM-cal lives at the root, not under /library/<slug>/.
    if slug == "llm-calibration":
        found = _drop_known_to_library(found, snapshot_root / "papers.json")

    return found, credits, errors


def run(
    client: OpenAlexClient, *,
    slugs: Iterable[str],
    repo_root: Path,
    ref_date: datetime.date | None = None,
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
    top_n: int = 10,
) -> RunResult:
    ref_date = ref_date or datetime.date.today()
    result = RunResult(date=ref_date.isoformat())
    snapshot_root = repo_root / "frontend" / "public" / "data"
    for slug in slugs:
        audit = (repo_root / "data" / "domains" / slug
                 / "reasoning" / "contradiction_audit.json")
        opps_root = (snapshot_root
                     / ("library/" + slug if slug != "llm-calibration" else ""))
        opps = opps_root / "opportunities.json"
        cands, credits, errors = _candidates_for_library(
            client, slug, snapshot_root, audit, opps,
            ref_date, lookback_days, top_n,
        )
        result.libraries[slug] = cands
        result.credits_used += credits
        result.errors.extend(errors)
    return result


# ----- rendering (markdown for the GitHub Issue) --------------------------


def render_issue_body(result: RunResult, *, lookback_days: int) -> str:
    L = [
        f"# Weekly refresh candidates — {result.date}",
        "",
        "This is an **automated** scan of OpenAlex for newly-published "
        f"works ({lookback_days}-day window) that may be relevant to the ",
        "libraries in this repository. The results have not been read, "
        "classified, or added to any library.",
        "",
        "**Flagged DOES NOT mean confirmed.** Each item is a lead for a "
        "human to open and decide; the pipeline does not act on these. "
        "No corpus addition, no auto-publishing, no LLM calls.",
        "",
        f"OpenAlex credits used: **{result.credits_used}** (one per query).",
        "",
    ]
    if result.errors:
        L.append("## Errors (free-tier failures etc.)")
        for e in result.errors:
            L.append(f"- `{e}`")
        L.append("")

    if not result.all_candidates():
        L.append("## No candidates")
        L.append(
            "No OpenAlex works in the window matched either of the two "
            "query shapes (cites-both of a genuine pair, or cites a paper "
            "behind an orphaned future-work item). Honest zero.")
        L.append("")
        return "\n".join(L)

    for slug, cands in result.libraries.items():
        L.append(f"## `{slug}` — {len(cands)} candidate(s)")
        if not cands:
            L.append("_No new candidates in this window._")
            L.append("")
            continue
        for c in cands:
            year = f" ({c.year})" if c.year else ""
            doi_part = f" DOI: `{c.doi}`" if c.doi else ""
            url = (f"https://openalex.org/W{c.wid.lstrip('W')}"
                   if c.wid else "")
            L.append(f"- **{c.title}**{year} — {c.reason}.{doi_part} "
                     f"[OpenAlex]({url})")
        L.append("")
    return "\n".join(L)


# ----- CLI entrypoint ------------------------------------------------------


def _repo_root_from_env() -> Path:
    return Path(os.environ.get("REPO_ROOT") or
                Path(__file__).resolve().parents[3])


def main() -> int:
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--slugs", nargs="*",
                    default=["llm-calibration",
                             "diet-and-mortality", "ml-fairness"])
    p.add_argument("--lookback-days", type=int, default=DEFAULT_LOOKBACK_DAYS)
    p.add_argument("--top-n", type=int, default=10)
    p.add_argument("--out", type=Path, help="write JSON result here")
    p.add_argument("--body-out", type=Path,
                    help="write the issue-body markdown here")
    p.add_argument("--dry-run-fixture", type=Path,
                    help="use a fixture JSON instead of a live OpenAlex call")
    args = p.parse_args()

    repo_root = _repo_root_from_env()

    if args.dry_run_fixture:
        client = _FixtureClient(json.loads(args.dry_run_fixture.read_text()))
    else:
        api_key = os.environ.get("OPENALEX_API_KEY", "").strip()
        if not api_key:
            print("ERROR: OPENALEX_API_KEY must be set. "
                  "(Set it as a GitHub Actions secret for CI, or export "
                  "it locally for a one-off dry run.)")
            return 2
        client = LiveOpenAlexClient(api_key=api_key)

    result = run(
        client, slugs=args.slugs, repo_root=repo_root,
        lookback_days=args.lookback_days, top_n=args.top_n,
    )
    body = render_issue_body(result, lookback_days=args.lookback_days)
    if args.out:
        args.out.write_text(json.dumps(result.as_dict(), indent=2))
    if args.body_out:
        args.body_out.write_text(body)
    print(body)
    return 0


class _FixtureClient:
    """Replays canned OpenAlex responses from a JSON fixture, for the
    dry run. Fixture shape: list of {match: str, response: dict}; the
    filter is matched by substring."""

    def __init__(self, fixture: list[dict]):
        self._fixture = fixture
        self.requests_made = 0

    def get(self, path: str, params: dict) -> dict:
        self.requests_made += 1
        f = params.get("filter", "")
        for entry in self._fixture:
            if entry.get("match", "") in f:
                return entry.get("response", {"results": [], "meta": {"count": 0}})
        # No matching fixture — return empty "no new work" response.
        return {"results": [], "meta": {"count": 0}}


if __name__ == "__main__":
    raise SystemExit(main())
