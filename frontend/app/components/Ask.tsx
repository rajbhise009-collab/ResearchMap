"use client";
// The query box and what happens after it.
//
// The design constraint this file exists to solve: a query box implies
// "ask me anything", but there is exactly one library behind it. So the
// answer to a question the library cannot cover is never a weak match —
// it is a plain statement that the subject is absent, what *is* here
// instead, and what building the missing library would actually cost.

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import type {
  GapDoc, PaperDoc, LanguagePack, SearchIndex, SearchResult,
} from "../../lib/types";
import { search } from "../../lib/search";
import { GapResult, PaperResult } from "./ResultCard";
import { Dev, DevKV } from "./DevMode";

const EXAMPLES = [
  "why do language models sound confident when they're wrong",
  "when should a chatbot refuse to answer",
  "fake citations in AI answers",
];

export default function Ask({ lang, gaps, papers }: {
  lang: LanguagePack;
  gaps: GapDoc[];
  papers: PaperDoc[];
}) {
  const [q, setQ] = useState("");
  const [index, setIndex] = useState<SearchIndex | null>(null);
  const [indexError, setIndexError] = useState(false);
  const [result, setResult] = useState<SearchResult | null>(null);
  const [asked, setAsked] = useState("");
  const resultsRef = useRef<HTMLDivElement>(null);

  // The index is fetched once, in the background, so that by the time
  // anyone has finished typing it is already there.
  useEffect(() => {
    let live = true;
    fetch("data/search-index.json")
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(String(r.status)))))
      .then((j: SearchIndex) => { if (live) setIndex(j); })
      .catch(() => { if (live) setIndexError(true); });
    return () => { live = false; };
  }, []);

  const run = useCallback((text: string) => {
    if (!index || !text.trim()) return;
    setResult(search(index, text, 24));
    setAsked(text);
  }, [index]);

  const onSubmit = (e: React.FormEvent) => { e.preventDefault(); run(q); };

  const gapBySlug = new Map(gaps.map((g) => [g.slug, g]));
  const paperByWid = new Map(papers.map((p) => [p.wid, p]));

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
      <form className="ask" onSubmit={onSubmit}>
        <div className="ask-row">
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder={S.placeholder}
            aria-label={S.placeholder}
            autoComplete="off"
          />
          <button type="submit" disabled={!index || !q.trim()}>
            {index ? "Ask" : "…"}
          </button>
        </div>
        <p className="ask-hint">
          {indexError
            ? "Search needs to load its index over http — open this site with a web server rather than from the file system."
            : !index ? S.searching : S.hint}
        </p>
        <div className="examples">
          {EXAMPLES.map((ex) => (
            <button key={ex} type="button"
              onClick={() => { setQ(ex); run(ex); }}
              disabled={!index}>
              {ex}
            </button>
          ))}
        </div>
      </form>

      <div ref={resultsRef}>
        {result && (
          <DevKV title={lang.dev.search_heading} data={{
            query: asked,
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

        {result?.verdict === "empty" && (
          <div className="empty">
            <h3>{S.no_results.label}</h3>
            <p>Try naming the thing you want to know about.</p>
          </div>
        )}

        {result?.verdict === "out_of_domain" && (
          <OutOfDomain lang={lang} query={asked} />
        )}

        {showResults && (
          <>
            {result.verdict === "borderline" && (
              <div className="caveat" style={{ marginTop: "2.5rem" }}>
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
                  <section style={{ marginTop: "2.5rem" }}>
                    <p className="section-label">{lang.ui.results_heading}</p>
                    <div className="results">
                      {gapHits.map((g) => (
                        <GapResult key={g.slug} gap={g} readMore={lang.ui.read_more} />
                      ))}
                    </div>
                  </section>
                )}
                {paperHits.length > 0 && (
                  <section style={{ marginTop: "3rem" }}>
                    <p className="section-label">Papers on this</p>
                    <div className="results">
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

/** The honest refusal, plus what it would take to fix it. */
function OutOfDomain({ lang, query }: { lang: LanguagePack; query: string }) {
  const [showBuild, setShowBuild] = useState(false);
  const S = lang.search.out_of_domain;
  const B = lang.build_library;
  return (
    <div style={{ marginTop: "2.75rem" }}>
      <div className="empty">
        <h3>{S.label}</h3>
        <p>{S.note.replace("{covers}", lang.ui.library_covers)}.</p>
        <p className="small muted">{lang.ui.one_library_note}</p>
      </div>

      <section className="block">
        <h2>{S.what_we_have}</h2>
        <p>{lang.ui.library_summary}</p>
        <p className="small">
          <Link href="/gaps/">{lang.ui.all_opportunities}</Link>
          {" · "}
          <Link href="/papers/">{lang.ui.all_papers}</Link>
        </p>
      </section>

      {!showBuild ? (
        <button className="cta" onClick={() => setShowBuild(true)}>
          {S.build_cta} →
        </button>
      ) : (
        <div className="panel">
          <h2>{B.title}</h2>
          <p>{B.body}</p>
          <div className="estimate">
            <p className="section-label" style={{ marginBottom: "0.5rem" }}>
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
                <span className="v">“{query}”</span>
              </div>
            )}
          </div>
          <p className="not-yet">{B.not_yet}</p>
        </div>
      )}
    </div>
  );
}
