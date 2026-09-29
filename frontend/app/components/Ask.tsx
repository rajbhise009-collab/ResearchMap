"use client";
// The landing query box and what happens after it.
//
// A search box implies "ask me anything", but there is exactly one library
// behind it. The answer to a question the library can't cover is never a
// weak match dressed up as an answer — it's a plain statement that the
// subject is absent, what IS here instead, and what building the missing
// library would actually cost.

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import type {
  GapDoc, PaperDoc, LanguagePack, SearchIndex, SearchResult,
  PreflightResult,
} from "../../lib/types";
import { search } from "../../lib/search";
import { useDev, DevKV, DevJSON } from "./DevMode";
import { asset } from "../../lib/basePath";
import { GapResult, PaperResult } from "./ResultCard";

const EXAMPLES = [
  "why do language models sound confident when they're wrong",
  "when should a chatbot refuse to answer",
  "fake citations in AI answers",
];
const DEBOUNCE_MS = 140;

export default function Ask({ lang, gaps, papers }: {
  lang: LanguagePack;
  gaps: GapDoc[];
  papers: PaperDoc[];
}) {
  const [q, setQ] = useState("");
  const [committed, setCommitted] = useState("");
  const [index, setIndex] = useState<SearchIndex | null>(null);
  const [indexError, setIndexError] = useState(false);
  const [result, setResult] = useState<SearchResult | null>(null);
  const [asking, setAsking] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const resultsRef = useRef<HTMLDivElement>(null);

  // Preload the index so the first keystroke is already answered.
  // Reads the currently-selected library's search-index (via ?lib=…);
  // falls back to the root snapshot for the legacy single-library
  // deploy shape.
  useEffect(() => {
    let live = true;
    // Two-step: fetch libraries.json to know the selected library's
    // snapshot_path, then fetch that library's search-index. If
    // libraries.json is absent (old deploy) fall back to root.
    const loadIndex = async () => {
      let indexUrl = asset("/data/search-index.json");
      try {
        const libResp = await fetch(asset("/data/libraries.json"));
        if (libResp.ok) {
          const manifest = await libResp.json();
          const requested = new URLSearchParams(window.location.search).get("lib");
          const remembered = (() => {
            try { return window.localStorage.getItem("researchmap.library"); }
            catch { return null; }
          })();
          const slug = requested || remembered || manifest.default_slug;
          const lib = (manifest.libraries || []).find((l: any) => l.slug === slug)
                       || (manifest.libraries || [])[0];
          if (lib?.snapshot_path) {
            indexUrl = asset(`${lib.snapshot_path}/search-index.json`);
          }
        }
      } catch { /* libraries.json missing — legacy deploy */ }
      try {
        const r = await fetch(indexUrl);
        if (!r.ok) throw new Error(String(r.status));
        const j: SearchIndex = await r.json();
        if (live) setIndex(j);
      } catch {
        if (live) setIndexError(true);
      }
    };
    loadIndex();
    return () => { live = false; };
  }, []);

  // "/" from anywhere focuses the input. It's the fastest way to start a
  // second question after reading one result.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const inField = document.activeElement instanceof HTMLElement &&
        ["INPUT", "TEXTAREA"].includes(document.activeElement.tagName);
      if (e.key === "/" && !inField) {
        e.preventDefault();
        inputRef.current?.focus();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  // Read ?q= from the URL on load — the command palette hands off here for
  // out-of-domain queries so the user sees the honest refusal in context.
  // Setting only `q` lets the debounced effect below run the search once
  // the index is ready.
  useEffect(() => {
    const u = new URLSearchParams(window.location.search).get("q");
    if (u) setQ(u);
  }, []);

  const run = useCallback((text: string) => {
    if (!index || !text.trim()) return;
    setResult(search(index, text, 24));
    setCommitted(text);
    // Nudge the viewport toward the results on the first ask.
    requestAnimationFrame(() => resultsRef.current?.scrollIntoView({ behavior: "smooth", block: "start" }));
  }, [index]);

  // Debounced live search: as-you-type once the query settles.
  useEffect(() => {
    if (!index || !q.trim()) { setAsking(false); return; }
    if (q === committed) return;
    setAsking(true);
    const t = setTimeout(() => {
      setResult(search(index, q, 24));
      setCommitted(q);
      setAsking(false);
    }, DEBOUNCE_MS);
    return () => { clearTimeout(t); setAsking(false); };
  }, [q, committed, index]);

  const onSubmit = (e: React.FormEvent) => { e.preventDefault(); run(q); };

  const gapBySlug = useMemo(() => new Map(gaps.map((g) => [g.slug, g])), [gaps]);
  const paperByWid = useMemo(() => new Map(papers.map((p) => [p.wid, p])), [papers]);

  const gapHits = (result?.hits ?? [])
    .filter((h) => h.type === "opportunity")
    .map((h) => gapBySlug.get(h.ref))
    .filter((x): x is GapDoc => !!x);
  const paperHits = (result?.hits ?? [])
    .filter((h) => h.type === "paper")
    .map((h) => paperByWid.get(h.ref))
    .filter((x): x is PaperDoc => !!x)
    .slice(0, 8);

  const S = lang.search;
  const showResults = result && result.verdict !== "out_of_domain" && result.verdict !== "empty";

  return (
    <>
      <form className="ask" onSubmit={onSubmit} role="search">
        <label className="ask-box" htmlFor="ask-input">
          <SearchIcon className="ask-icon" />
          <input
            id="ask-input"
            ref={inputRef}
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder={S.placeholder}
            aria-label={S.placeholder}
            autoComplete="off"
            spellCheck="false"
          />
          <button className="ask-btn" type="submit" disabled={!index || !q.trim()}>
            {asking ? "…" : "Ask"}
          </button>
        </label>

        <p className="ask-hint" aria-live="polite">
          {indexError
            ? "Search needs to load its index over http — open this site with a web server, not from disk."
            : !index
              ? (<><span className="swatch" aria-hidden /> {S.searching}</>)
              : (<>Press <kbd className="inline-kbd">/</kbd> from anywhere to focus this. Try: {S.hint.replace(/^Try: /, "")}</>)}
        </p>

        <div className="examples">
          <span className="label">Examples</span>
          {EXAMPLES.map((ex) => (
            <button key={ex} type="button" className="example-chip"
              onClick={() => { setQ(ex); run(ex); }} disabled={!index}>
              {ex}
            </button>
          ))}
        </div>
      </form>

      <div ref={resultsRef}>
        {result && (
          <DevKV title={lang.dev.search_heading} data={{
            query: committed,
            verdict: result.verdict,
            coverage: result.coverage.toFixed(4),
            best_score: result.best.toFixed(5),
            breadth: result.breadth.toFixed(4),
            docs_matched: result.n_matched,
            known_terms: result.known,
            unknown_terms: result.unknown,
            expanded_terms: result.expanded,
            note: "lexical term-weight match over the library's own vocabulary; no embedding call, no spend",
          }} />
        )}

        {asking && !result && <ResultsSkeleton />}

        {result?.verdict === "empty" && (
          <div className="empty" style={{ marginTop: "var(--s-7)" }}>
            <h3>{S.no_results.label}</h3>
            <p>Try naming the thing you want to know about.</p>
          </div>
        )}

        {result?.verdict === "out_of_domain" && (
          <OutOfDomain lang={lang} query={committed} />
        )}

        {showResults && (
          <>
            <div className="verdict-line">
              <span className="count">
                {gapHits.length + paperHits.length} results
              </span>
              <span>for</span>
              <span className="query">“{committed}”</span>
              {result.verdict === "borderline" && (
                <span style={{ color: "var(--note-icon)" }}>· at the edge of this library</span>
              )}
            </div>

            {result.verdict === "borderline" && (
              <div className="caveat" style={{ marginTop: 0 }}>
                <span className="cav-label">{S.borderline.label}</span>
                {S.borderline.note}
              </div>
            )}

            {gapHits.length === 0 && paperHits.length === 0 ? (
              <div className="empty">
                <h3>{S.no_results.label}</h3>
                <p>{S.no_results.note}</p>
              </div>
            ) : (
              <>
                {gapHits.length > 0 && (
                  <section style={{ marginTop: "var(--s-6)" }}>
                    <p className="section-eyebrow">Gaps we found</p>
                    <div className="results-list">
                      {gapHits.map((g) => (
                        <GapResult key={g.slug} gap={g} readMore={lang.ui.read_more} />
                      ))}
                    </div>
                  </section>
                )}
                {paperHits.length > 0 && (
                  <section style={{ marginTop: "var(--s-7)" }}>
                    <p className="section-eyebrow">Papers on this</p>
                    <div className="results-list">
                      {paperHits.map((p) => (
                        <PaperResult key={p.wid} paper={p}
                          fidelityLabel={lang.abstract_only.label}
                          fidelityNote={lang.abstract_only.text} />
                      ))}
                    </div>
                  </section>
                )}
              </>
            )}
          </>
        )}
      </div>
    </>
  );
}

function ResultsSkeleton() {
  return (
    <div style={{ marginTop: "var(--s-7)" }} aria-hidden>
      <div className="skel-block">
        <div className="skel-head" />
        <div className="skel-title" />
        <div className="skel-title b" />
      </div>
      <div className="skel-block">
        <div className="skel-head" />
        <div className="skel-title" />
        <div className="skel-title b" />
      </div>
    </div>
  );
}

function SearchIcon({ className }: { className?: string }) {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24"
      fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"
      className={className} aria-hidden>
      <circle cx="11" cy="11" r="7" />
      <line x1="16.4" y1="16.4" x2="21" y2="21" />
    </svg>
  );
}

/** The honest refusal, plus a live pre-flight check on the subject the
 *  user asked about. The pre-flight uses ONLY free OpenAlex metadata
 *  (no LLM, no extraction, no spend) and returns:
 *   - how much literature exists on the subject
 *   - a hypothesis-driven diagnostic about what kinds of findings the
 *     reasoning engine would likely surface
 *   - a cost + time estimate for building the library
 *
 *  This only works when the full stack is running (uvicorn serving
 *  /api/*). On a static host with no backend, we fall back to the copy
 *  from the translation layer — same headline, no live diagnostic.
 */
function OutOfDomain({ lang, query }: { lang: LanguagePack; query: string }) {
  const [showBuild, setShowBuild] = useState(false);
  const [preflight, setPreflight] = useState<PreflightResult | null>(null);
  const [preflightState, setPreflightState] = useState<
    "idle" | "loading" | "ok" | "unavailable"
  >("idle");
  const { dev } = useDev();
  const S = lang.search.out_of_domain;
  const B = lang.build_library;

  // Lazily fetch when the user opens the panel. Aborts if the panel
  // gets closed before the response returns.
  useEffect(() => {
    if (!showBuild || preflightState !== "idle" || !query.trim()) return;
    setPreflightState("loading");
    const ctrl = new AbortController();
    fetch(`/api/preflight?q=${encodeURIComponent(query)}`, { signal: ctrl.signal })
      .then(async (r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return (await r.json()) as PreflightResult;
      })
      .then((data) => { setPreflight(data); setPreflightState("ok"); })
      .catch((e) => {
        if ((e as Error).name === "AbortError") return;
        setPreflightState("unavailable");
      });
    return () => ctrl.abort();
  }, [showBuild, preflightState, query]);

  return (
    <div style={{ marginTop: "var(--s-7)" }}>
      <div className="empty">
        <h3>{S.label}</h3>
        <p>{S.note.replace("{covers}", lang.ui.library_covers)}</p>
        <p className="small muted">{lang.ui.one_library_note}</p>
      </div>

      <section className="block">
        <h2>{S.what_we_have}</h2>
        <p>{lang.ui.library_summary}</p>
        <p className="small" style={{ marginTop: "var(--s-4)" }}>
          <Link href="/gaps/">{lang.ui.all_opportunities}</Link>
          <span className="foot-dot" style={{ margin: "0 var(--s-3)", color: "var(--rule-strong)" }}>·</span>
          <Link href="/papers/">{lang.ui.all_papers}</Link>
        </p>
      </section>

      {!showBuild ? (
        <button className="cta" onClick={() => setShowBuild(true)}>
          {S.build_cta} <span aria-hidden>→</span>
        </button>
      ) : (
        <div className="panel">
          <h2>{B.title}</h2>
          <p>{B.body}</p>

          {preflightState === "loading" && (
            <p className="small muted" style={{ marginTop: "var(--s-4)" }}>
              Looking up how much literature exists on this…
            </p>
          )}

          {preflightState === "ok" && preflight && (
            <PreflightBlock preflight={preflight} devMode={dev} />
          )}

          {preflightState === "unavailable" && (
            <p className="small muted" style={{ marginTop: "var(--s-4)" }}>
              (Live pre-flight isn&apos;t available on this deployment —
              it only runs when the local backend is up. Estimates below
              are for a typical ~200-paper build.)
            </p>
          )}

          {/* Static fallback — always shown so the panel is informative
              even without a live pre-flight. */}
          <div className="estimate">
            <p className="section-eyebrow" style={{ marginBottom: "var(--s-3)" }}>
              {B.estimate_label}
            </p>
            {B.estimates.map(([k, v]) => (
              <div className="row" key={k}>
                <span className="k">{k}</span>
                <span className="v">{v}</span>
              </div>
            ))}
            {query && (
              <div className="row">
                <span className="k">Subject</span>
                <span className="v" style={{ fontStyle: "italic" }}>“{query}”</span>
              </div>
            )}
          </div>
          <p className="not-yet">{B.not_yet}</p>
        </div>
      )}
    </div>
  );
}

/** Renders the live pre-flight result inside the "Build a library" panel.
 *  Consumer view: three plain-language lines (coverage, diagnostic,
 *  cost/time). Dev view: raw features, verdict, cost projection, and
 *  the top paper titles OpenAlex returned for the query — all clearly
 *  framed as "hypothesis, not guarantee." */
function PreflightBlock({ preflight, devMode }: {
  preflight: PreflightResult;
  devMode: boolean;
}) {
  const c = preflight.consumer;
  return (
    <div style={{ marginTop: "var(--s-5)" }}>
      <p className="section-eyebrow">Pre-flight diagnostic</p>

      <p style={{ margin: "var(--s-2) 0 var(--s-3)" }}>{c.coverage_line}</p>
      <p style={{ margin: 0 }}>{c.diagnostic_line}</p>
      <p style={{ margin: "var(--s-4) 0 0", fontWeight: 500 }}>
        {c.estimate_headline}
      </p>

      {devMode && (
        <>
          <DevKV title="preflight — features" data={preflight.dev.features} />
          <DevKV title="preflight — verdict" data={preflight.dev.verdict} />
          <DevKV title="preflight — cost projection" data={preflight.dev.cost_projection} />
          <DevJSON title="preflight — top OpenAlex results" data={preflight.dev.top_paper_titles || []} />
        </>
      )}
    </div>
  );
}
