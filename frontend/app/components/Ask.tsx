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
} from "../../lib/types";
import { search } from "../../lib/search";
import { asset } from "../../lib/basePath";
import { GapResult, PaperResult } from "./ResultCard";
import { DevKV } from "./DevMode";

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
  useEffect(() => {
    let live = true;
    fetch(asset("/data/search-index.json"))
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(String(r.status)))))
      .then((j: SearchIndex) => { if (live) setIndex(j); })
      .catch(() => { if (live) setIndexError(true); });
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

/** The honest refusal, plus what it would take to fix it. */
function OutOfDomain({ lang, query }: { lang: LanguagePack; query: string }) {
  const [showBuild, setShowBuild] = useState(false);
  const S = lang.search.out_of_domain;
  const B = lang.build_library;
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
