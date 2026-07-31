"""ResearchMap read-only API (Phase 6). File-backed — runs with NO
DATABASE_URL and makes no external calls. Auto OpenAPI at /docs.
"""

from __future__ import annotations

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from functools import lru_cache

from backend.app.api import data, export, language, search_index
from backend.app.ranking.schema import SCHEMA_VERSION


@lru_cache(maxsize=1)
def _index() -> dict:
    """The search index, built once from the same cached files everything
    else reads. No embedding calls, no spend."""
    cards = []
    for c in data.cards():
        card = {**c.model_dump(), "slug": export.slug(c.id)}
        card["consumer"] = language.consumer_card(card)
        cards.append(card)
    details = []
    for p in data.paper_summaries():
        d = data.paper_detail(p["paper_id"])
        d["wid"] = p["paper_id"].split(":")[-1]
        details.append(d)
    return search_index.build_index(cards, details)

app = FastAPI(
    title="ResearchMap API",
    version=SCHEMA_VERSION,
    description=("Read-only, file-backed API over the reasoning-engine output. "
                "Honest by construction: confidence tiers and caveats are "
                "first-class on every opportunity."),
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_methods=["GET"],
    allow_headers=["*"],
)


@app.get("/api")
def root():
    return {"name": "ResearchMap API", "schema_version": SCHEMA_VERSION,
            "endpoints": ["/api/opportunities", "/api/opportunities/{id}",
                          "/api/papers", "/api/papers/{id}", "/api/relationships",
                          "/api/corpus/stats", "/api/findings", "/api/search",
                          "/api/language", "/docs"]}


@app.get("/api/opportunities")
def opportunities(
    gap_type: str | None = None,
    tier: str | None = Query(None, description="high | medium | low"),
    min_confidence: float = Query(0.0, ge=0.0, le=1.0),
    scorer: str | None = None,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    items = data.cards()
    if gap_type:
        items = [c for c in items if c.gap_type == gap_type]
    if tier:
        items = [c for c in items if c.confidence_tier == tier]
    if scorer:
        items = [c for c in items if c.scorer == scorer]
    if min_confidence:
        items = [c for c in items if c.confidence >= min_confidence]
    total = len(items)
    page = items[offset:offset + limit]
    return {"schema_version": SCHEMA_VERSION, "total": total,
            "limit": limit, "offset": offset,
            "items": [c.model_dump() for c in page]}


@app.get("/api/opportunities/{opp_id:path}")
def opportunity(opp_id: str):
    card = data.card_by_id(opp_id)
    if card is None:
        raise HTTPException(404, f"opportunity {opp_id!r} not found")
    return card.model_dump()


@app.get("/api/papers")
def papers(domain_centrality: str | None = None, input_source: str | None = None):
    items = data.paper_summaries()
    if domain_centrality:
        items = [p for p in items if p["domain_centrality"] == domain_centrality]
    if input_source:
        items = [p for p in items if p["input_source"] == input_source]
    return {"total": len(items), "items": items}


@app.get("/api/papers/{paper_id:path}")
def paper(paper_id: str):
    detail = data.paper_detail(paper_id)
    if detail is None:
        raise HTTPException(404, f"paper {paper_id!r} not found")
    return detail


@app.get("/api/relationships")
def relationships(type: str | None = None):
    rels = data.relationships()
    if type:
        rels = [r for r in rels if r.type == type]
    return {"total": len(rels), "items": [r.model_dump() for r in rels]}


@app.get("/api/corpus/stats")
def corpus_stats():
    return data.stats()


@app.get("/api/findings")
def findings():
    return {"items": [{k: v for k, v in f.items() if k != "markdown"}
                      for f in data.findings()]}


@app.get("/api/findings/{slug}")
def finding(slug: str):
    f = next((x for x in data.findings() if x["slug"] == slug), None)
    if f is None:
        raise HTTPException(404, f"finding {slug!r} not found")
    return f


@app.get("/api/language")
def language_pack():
    """Every word the consumer interface shows, from the single translation
    layer. The frontend renders these — it does not carry its own copy."""
    return language.language_pack()


@app.get("/api/search")
def search(q: str = Query("", description="A question in plain English"),
           limit: int = Query(20, ge=1, le=100)):
    """Search the library, and say honestly when it cannot answer.

    `verdict` is the important field: `in_domain` results are answers,
    `borderline` results sit at the edge of what the library covers, and
    `out_of_domain` means the subject is absent — in which case hits are
    withheld rather than shown as weak matches.
    """
    result = search_index.search(_index(), q, limit=limit)
    if result["verdict"] == "out_of_domain":
        result["hits"] = []
    return result


__all__ = ["app"]
