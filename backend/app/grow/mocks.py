"""Offline stand-ins for OpenAlex and Gemini, for the weekly-growth
end-to-end test ONLY (tools/grow/e2e_mock.py runs it in a throwaway copy of
the repository with a temporary ledger). Nothing here is ever published:
the runner refuses to commit or push when GROW_MOCK=1.

The fake OpenAlex serves, per library, a small pool built from that
library's own records with new ids and test titles, plus planted cases the
pipeline must reject: a DOI duplicate, a title duplicate, a pair of
duplicates among candidates, and an off-topic record. The fake batch API
persists jobs in a state directory so a submit in one run is collected by
the next. The fake embedder returns the real cached vector for any text
identical to an existing claim, so a copied claim produces a new
disagreement pair; anything else gets a deterministic hash vector.
"""

from __future__ import annotations

import copy
import json
import os
import re
from pathlib import Path

import httpx

from backend.app.config import REPO_ROOT
from backend.app.corpus import records
from backend.app.extraction.batch_client import BatchJob
from backend.app.grow.core import Clients, _wid, domains_dir, grow_slugs
from backend.app.relationships.embeddings import MockEmbeddingClient

_M = int(os.environ.get("GROW_MOCK_USAGE_MULT") or 1)     # tests: make collection expensive
_USAGE = {"promptTokenCount": 1800 * _M, "candidatesTokenCount": 900 * _M, "thoughtsTokenCount": 600 * _M}


def _fail(kind: str) -> bool:
    return kind in (os.environ.get("GROW_MOCK_FAIL") or "").split(",")


class MockOpenAlex:
    def __init__(self):
        self.requests_made = 0
        self.pool: dict[str, list[dict]] = {}
        self.owner: dict[str, str] = {}
        # A new pool each week (ids and test titles carry the run's week), as
        # real OpenAlex results would be.
        import datetime as dt
        day = dt.date.fromisoformat(os.environ.get("GROW_DATE") or dt.date.today().isoformat())
        wk = day.toordinal() // 7
        self.week = wk
        for n, slug in enumerate(grow_slugs()):
            self.pool[slug] = self._build_pool(slug, 9_000_000_000 + n * 100_000 + (wk % 900) * 100, wk)
            for r in records.load(slug)["records"]:
                self.owner[_wid(r["id"])] = slug
        self.by_wid = {_wid(r["id"]): r for rs in self.pool.values() for r in rs}

    @staticmethod
    def _build_pool(slug: str, base: int, wk: int) -> list[dict]:
        pre = json.loads((domains_dir() / slug / "prelabelled.json").read_text())
        snow = records.load(slug)
        recs = {_wid(r["id"]): r for r in snow["records"]}
        from backend.app.grow.scope import core_scope
        # planted duplicates copy library papers that pass the rubric AND the
        # core scope, so they reach (and must be caught by) the dedupe steps
        on = [e for e in pre["entries"] if e.get("label") == "on-domain" and e["wid"] in recs and e.get("abstract")]
        scoped = [e for e in on if core_scope(slug, e.get("title") or "", e.get("abstract"))[0]]
        # a library with no core scope defined (e.g. one just built from the
        # queue) is not grown unattended: its candidates are all dropped by
        # select(), so any of its papers can seed the pool
        core = [recs[e["wid"]] for e in (scoped if len(scoped) >= 8 else on)]
        out = []

        def mk(src, i, title, doi=None):
            r = copy.deepcopy(src)
            r["id"] = f"https://openalex.org/W{base + i}"
            r["title"] = r["display_name"] = title
            r["doi"] = doi
            r["publication_year"] = 2026
            r["cited_by_count"] = 50 - i
            r["is_retracted"] = r["is_paratext"] = False
            r["referenced_works"] = [src["id"]]
            return r

        # Clean candidates are synthetic (not copies of library papers, whose
        # text would double-count in search), worded from the library's own
        # rubric terms so the rubric accepts them.
        from backend.app.corpus.multi_domain_reason import DOMAINS
        cfg = DOMAINS[slug]
        a, t, st = cfg.anchor_terms[0], cfg.topic_terms[0], cfg.strong_topic_terms[0]
        pair = (cfg.pair_terms or (t,))[0]
        def synth(r, tag):
            # "among adolescents": weekly growth also requires each domain's core
            # population and outcome (backend/app/grow/scope.py)
            text = (f"We examined {st} and {pair} among adolescents in test cohort {tag}. "
                    f"The {a} measure and {t} were recorded for every participant.")
            r["abstract_inverted_index"] = {}
            for pos, w in enumerate(text.split()):
                r["abstract_inverted_index"].setdefault(w, []).append(pos)
            r["authorships"] = [{"author": {"display_name": f"Test Author {tag}"}}]
            return r

        for i in range(4):
            out.append(synth(mk(core[i], i, f"Weekly growth test record {wk}-{i}: {st} and {pair}"), f"{wk}-{i}"))
        out.append(synth(mk(core[4], 4, f"Weekly growth test record {wk}: DOI duplicate",
                            doi=core[5].get("doi")), f"{wk}-doi"))
        out.append(mk(core[6], 5, core[6]["title"]))                       # title duplicate
        out.append(synth(mk(core[7], 6, f"Weekly growth test record {wk}: twin candidate"), f"{wk}-twin"))
        out.append(synth(mk(core[7], 7, f"Weekly growth test record {wk}: twin candidate"), f"{wk}-twin"))
        off = snow.get("rejected_records") or []
        if off:
            out.append(mk(off[0], 8, off[0].get("title") or "Off-topic record"))
        return out

    def get(self, path: str, params: dict) -> dict:
        self.requests_made += 1
        if _fail("openalex"):
            raise httpx.ConnectError("mock: OpenAlex unreachable")
        f = params.get("filter", "")
        if f.startswith("openalex_id:"):
            wids = f.split(":", 1)[1].split("|")
            return {"results": [self.by_wid[w] for w in wids if w in self.by_wid]}
        cited = re.findall(r"cites:([W0-9|]+)", f)
        first = cited[0].split("|")[0] if cited else ""
        slug = self.owner.get(first)
        pool = self.pool.get(slug, [])
        if len(cited) == 2:                      # cites-both
            sel = pool[:2]
        elif cited and set(cited[0].split("|")) <= self._orphan_sources(slug):
            sel = pool[2:4]
        else:
            sel = pool[2:]
        return {"results": [{k: r.get(k) for k in ("id", "doi", "display_name", "publication_year",
                                                   "cited_by_count", "is_retracted", "is_paratext")}
                            for r in sel]}

    @staticmethod
    def _orphan_sources(slug: str | None) -> set[str]:
        if not slug:
            return set()
        p = REPO_ROOT / "frontend" / "public" / "data" / "library" / slug / "opportunities.json"
        out = set()
        for c in json.loads(p.read_text()).get("items", []):
            if (c.get("consumer") or {}).get("kind_id") == "unfollowed_future_work":
                for sp in c.get("supporting_papers") or []:
                    out.add(_wid(sp.get("paper_id") if isinstance(sp, dict) else sp))
        return out


class MockBatch:
    """Jobs persist under `state_dir` so a later process can collect them."""

    def __init__(self, state_dir: Path):
        self.dir = state_dir
        self.dir.mkdir(parents=True, exist_ok=True)

    def _p(self, bid: str) -> Path:
        return self.dir / (bid.replace("/", "_") + ".json")

    def submit(self, prompts: dict[str, str], *, display_name: str) -> str:
        if _fail("gemini"):
            raise RuntimeError("mock: Gemini batch submit failed (503)")
        n = len(list(self.dir.glob("*.json"))) + 1
        bid = f"batches/mock-{n:04d}"
        self._p(bid).write_text(json.dumps({"display_name": display_name, "keys": sorted(prompts)}))
        return bid

    def poll(self, bid: str) -> BatchJob:
        st = "JOB_STATE_PENDING" if _fail("batch_pending") else "JOB_STATE_SUCCEEDED"
        return BatchJob(batch_id=bid, state=st)

    def wait(self, bid: str, *, poll_interval_s: float = 0, timeout_s: float = 0) -> BatchJob:
        return self.poll(bid)

    def results_with_usage(self, job: BatchJob) -> dict[str, tuple[str, dict]]:
        st = json.loads(self._p(job.batch_id).read_text())
        name, keys = st["display_name"], st["keys"]
        if "hole_confirm" in name:
            return {k: (json.dumps({"verdict": "substantive", "reason": "mock"}), _USAGE) for k in keys}
        if "contradiction" in name:
            return {k: (json.dumps({"relationship": "contradicts", "explanation": "mock"}), _USAGE) for k in keys}
        if "fw_match" in name:
            return {k: (json.dumps({"label": "not_addressed", "justification": "mock",
                                    "addressing_element": ""}), _USAGE) for k in keys}
        slug = name.removeprefix("researchmap-grow-").removeprefix("researchmap-")
        mirror = _first_contradiction_text(slug)
        return {k: (json.dumps(_extraction(k, mirror if i == 0 else None)), _USAGE)
                for i, k in enumerate(keys)}


def _first_contradiction_text(slug: str) -> str | None:
    p = domains_dir() / slug / "reasoning" / "contradictions.json"
    items = json.loads(p.read_text()).get("items", []) if p.exists() else []
    return items[0]["a_text"] if items else None


def _extraction(pid: str, mirror: str | None) -> dict:
    claims = [{"id": f"{pid}:c1", "paper_id": pid, "type": "finding", "confidence": 0.8,
               "text": mirror or f"Test record {pid} reports an association in its cohort."},
              {"id": f"{pid}:c2", "paper_id": pid, "type": "method", "confidence": 0.8,
               "text": f"Test record {pid} used a prospective cohort design."}]
    return {"paper_id": pid, "claims": claims, "evidence": [],
            "methodologies": [{"id": f"{pid}:m1", "paper_id": pid, "name": "prospective cohort",
                               "description": "test record method", "datasets": [], "conditions": []}],
            "limitations": [{"id": f"{pid}:l1", "paper_id": pid, "text": f"Test record {pid} relied on self-reported intake.",
                             "normalized_category": "measurement", "source_scope": "this_work"}],
            "future_work": [{"id": f"{pid}:f1", "paper_id": pid, "addressed_by": None,
                             "text": f"Test record {pid}: replicate in a second population."}]}


class MockEmbed(MockEmbeddingClient):
    name = "mock-embedding"

    def __init__(self):
        super().__init__(dim=768)
        from backend.app.corpus import multi_domain_reason as R
        self.by_text: dict[str, list[float]] = {}
        for slug in grow_slugs():
            cp = R._embedding_cache_path(slug)
            cache = json.loads(cp.read_text()) if cp.exists() else {}
            for e in R.load_extractions(slug):
                for c in e.claims:
                    v = cache.get(R._claim_seed(c.id, c.text))
                    if v is not None:
                        self.by_text.setdefault(c.text, v)

    def embed(self, texts: list[str]) -> list[list[float]]:
        if _fail("gemini"):
            raise RuntimeError("mock: Gemini embedding failed (503)")
        return [self.by_text.get(t) or super().embed([t])[0] for t in texts]


class MockLLM:
    def generate(self, prompt: str) -> str:
        return json.dumps({"relationship": "contradicts", "explanation": "mock"})


def mock_clients(_fixture: str | None = None) -> Clients:
    state = Path(os.environ.get("GROW_MOCK_STATE") or (REPO_ROOT / ".grow-mock-state"))
    return Clients(openalex=MockOpenAlex(), batch=MockBatch(state), embed=MockEmbed(),
                   llm=MockLLM(), fulltext=lambda e, r: None, mock=True)
