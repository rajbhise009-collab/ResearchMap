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
import { matchingLibraries, type OtherLib } from "../../lib/otherLibraries";
import { search } from "../../lib/search";
import { useDev, DevKV, DevJSON } from "./DevMode";
import { asset } from "../../lib/basePath";
import { GapResult, PaperResult } from "./ResultCard";
import { storageGet, typingInField, LIBRARY_KEY } from "../../lib/storage";
import { cleanQuery, echoQuery, MAX_QUERY } from "../../lib/query";
import { examplesFor, tryHintFor } from "../../lib/examples";
import { handOffQuery, takeHandedOffQuery, HANDOFF_EVENT } from "../../lib/handoff";
import { getLibraries, takeEarlyQuery, takeIndexPrefetch } from "../../lib/prefetch";

// The out-of-scope panel lists this many other libraries before folding the
// rest into "All N other libraries" (scales to any number of libraries).
const OTHER_LIBS_SHOWN = 3;
import { adviceLike, distress, HELPLINE_URL, panelBlocked, selfHarm } from "../../lib/safety";

const DEBOUNCE_MS = 200;
// How long after the last keystroke do the "borderline"/"out of domain"
// banners become visible. The reader must not see a refusal flash during
// typing; only after they've paused long enough that they clearly meant
// to look at that query as a whole.
const BANNER_PAUSE_MS = 700;
// Minimum characters before the type-ahead box reaches for the index.
// Under 3 chars we show nothing (no results, no banner).
const MIN_TYPEAHEAD_CHARS = 3;

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
  // A search asked for before the index has arrived (Enter, Ask or an
  // example): kept here and run the moment the index is ready.
  const [pending, setPending] = useState<string | null>(null);
  // Bumped on each submitted search: its cards arrive with a short cascade
  // (globals.css .results-enter); type-ahead updates never animate.
  const [runKey, setRunKey] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const resultsRef = useRef<HTMLDivElement>(null);

  // Per-library opportunities + papers, resolved client-side from the
  // active library's snapshot (so the Ask box's lookup maps match the
  // library the index was built from — the SSR props below are
  // LLM-cal-only). Without this, a Diet search returns correct hits
  // but the UI drops them because `gapBySlug.get(dietSlug)` is undef.
  const [liveGaps, setLiveGaps] = useState<GapDoc[] | null>(null);
  const [livePapers, setLivePapers] = useState<PaperDoc[] | null>(null);
  const [otherLibHits, setOtherLibHits] = useState<
    { slug: string; name: string } | null>(null);
  const [activeLib, setActiveLib] = useState<
    { slug: string; name: string; blurb?: string; not_advice_note?: string | null;
      health_adjacent?: boolean } | null>(null);
  // Until the active library is known, show no examples (never another
  // library's questions for a moment).
  const examples = examplesFor(activeLib?.slug);
  const tryHint = tryHintFor(activeLib?.slug);

  // Preload the index so the first keystroke is already answered.
  // Reads the currently-selected library's search-index (via ?lib=…);
  // falls back to the root snapshot for the legacy single-library
  // deploy shape.
  useEffect(() => {
    let live = true;
    const loadAll = async () => {
      let snapshotPath = "/data";
      let activeSlug: string | null = null;
      let allLibs: Array<{ slug: string; name: string;
                            snapshot_path: string }> = [];
      try {
        const manifest = await getLibraries();
        if (manifest) {
          allLibs = manifest.libraries || [];
          const requested = new URLSearchParams(window.location.search).get("lib");
          const remembered = storageGet(LIBRARY_KEY);
          const slug = requested || remembered || manifest.default_slug;
          const lib = allLibs.find((l) => l.slug === slug) || allLibs[0];
          if (lib) {
            snapshotPath = lib.snapshot_path;
            activeSlug = lib.slug;
            if (live) {
              setActiveLib({ slug: lib.slug, name: lib.name,
                             blurb: (lib as any).blurb,
                             not_advice_note: (lib as any).not_advice_note ?? null,
                             health_adjacent: !!(lib as any).health_adjacent });
            }
          }
        }
      } catch { /* libraries.json missing — legacy deploy */ }
      // The index and the cards' data load together, and search counts as
      // ready only when both are in: a search run on the index alone would
      // draw thin cards that then grow when their data arrives (layout
      // shift). The <head> script usually started the index already.
      const indexP = (takeIndexPrefetch(snapshotPath) ?? Promise.resolve(null))
        .then(async (j) => {
          if (j) return j;
          const r = await fetch(asset(`${snapshotPath}/search-index.json`));
          if (!r.ok) throw new Error(String(r.status));
          return (await r.json()) as SearchIndex;
        });
      // Missing card data falls back to the SSR props, as before.
      const json = (f: string) => fetch(asset(`${snapshotPath}/${f}`))
        .then((r) => (r.ok ? r.json() : null)).catch(() => null);
      try {
        const [j, oj, pj] = await Promise.all([indexP, json("opportunities.json"), json("papers.json")]);
        if (!live) return;
        if (oj) {
          // Only results count: set-aside and not-yet-checked items live on
          // /gaps in their own sections, never in search.
          setLiveGaps((oj.items || []).filter((o: any) => {
            const v = o.verdict ?? o.consumer?.verdict ?? null;
            return v === null || v === "genuine";
          }).map((o: any) => ({
            slug: o.slug, consumer: o.consumer,
            dev: { rank: o.rank ?? 0, gap_type: o.gap_type ?? "" },
          })));
        }
        if (pj) {
          setLivePapers((pj.items || []).map((p: any) => ({
            wid: p.wid, title: p.title ?? p.wid,
            year: p.year, abstract_only: p.abstract_only,
            domain_centrality: p.domain_centrality,
            dev: { year: p.year, abstract_only: p.abstract_only ?? null,
                    domain_centrality: p.domain_centrality ?? "" },
          })));
        }
        setIndex(j);
      } catch {
        if (live) setIndexError(true);
      }
      // Stash the other libraries' metadata for the OOD suggestion.
      if (activeSlug && allLibs.length > 1) {
        (window as any).__researchmap_other_libs =
          allLibs.filter((l) => l.slug !== activeSlug);
      }
    };
    loadAll();
    return () => { live = false; };
  }, []);

  // When the current library returns out_of_domain but another library's
  // index would say in_domain for the same query, surface a one-line
  // "wrong library?" nudge. Keeps the honest OOD refusal next to it, so
  // the user still sees that the current library cannot answer.
  useEffect(() => {
    setOtherLibHits(null);
    if (!result || result.verdict !== "out_of_domain") return;
    const others = (window as any).__researchmap_other_libs as
      Array<{ slug: string; name: string; snapshot_path: string }> | undefined;
    if (!others || !committed.trim()) return;
    let live = true;
    matchingLibraries(others, committed).then((m) => {
      if (live && m.length) setOtherLibHits({ slug: m[0].slug, name: m[0].name });
    });
    return () => { live = false; };
  }, [result, committed]);

  // "/" from anywhere focuses the input. It's the fastest way to start a
  // second question after reading one result.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "/" && !typingInField() && !e.metaKey && !e.ctrlKey) {
        e.preventDefault();
        inputRef.current?.focus();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  // A query handed over from another page (the command palette, or a
  // "switch and ask there" link) arrives through sessionStorage, never the
  // URL: a query in the URL would reach the server, every Referer header and
  // page-view analytics (lib/handoff.ts). A ?q= in the address (an old shared
  // link) is ignored: the page opens with an empty box. Setting only `q` lets
  // the debounced effect below run the search once the index is ready.
  useEffect(() => {
    const take = () => { const h = takeHandedOffQuery(); if (h.trim()) setQ(h); };
    take();
    window.addEventListener(HANDOFF_EVENT, take);
    return () => window.removeEventListener(HANDOFF_EVENT, take);
  }, []);

  // `banner` controls whether the borderline/out-of-domain banners are
  // allowed to render. Starts off while the user is typing and flips on
  // after BANNER_PAUSE_MS of silence or when they press Enter / Ask.
  // That way the typing path never flashes a refusal between keystrokes.
  const [bannerAllowed, setBannerAllowed] = useState(false);

  const run = useCallback((text: string) => {
    if (!text.trim()) return;
    if (!index) { setPending(text); return; }
    // Enter / Ask expands a trailing prefix to its best completion so
    // "alc" + Enter behaves like "alcohol" + Enter — the verdict reads
    // the full word.
    setResult(search(index, text, 24, { expandTrailing: true }));
    setRunKey((k) => k + 1);
    setCommitted(text);
    setBannerAllowed(true);
    requestAnimationFrame(() => resultsRef.current?.scrollIntoView({ behavior: "smooth", block: "start" }));
  }, [index]);

  // Debounced live search: as-you-type once the query settles.
  // - Under MIN_TYPEAHEAD_CHARS: no results, no banner (neutral state).
  // - Otherwise: type-ahead with prefix on the LAST token for retrieval.
  // - Banner (borderline / OOD label) stays suppressed until a pause of
  //   BANNER_PAUSE_MS after the last keystroke OR Enter / Ask.
  //
  // Depending only on `q` and `index` here is deliberate: the earlier
  // version depended on `committed` too, so the setCommitted() inside
  // the debounce fired a re-run that cancelled the 700 ms banner timer
  // and left bannerAllowed stuck at false forever.
  useEffect(() => {
    if (!index) { setAsking(false); return; }
    const trimmed = q.trim();
    if (!trimmed) {
      setResult(null); setCommitted(""); setAsking(false);
      setBannerAllowed(false);
      return;
    }
    if (trimmed.length < MIN_TYPEAHEAD_CHARS) {
      setResult(null); setAsking(false);
      setBannerAllowed(false);
      return;
    }
    setAsking(true);
    setBannerAllowed(false);
    const t = setTimeout(() => {
      // prefixLast: expand the last typed word as a prefix so "alc"
      // retrieves the alcohol gaps mid-typing. The verdict is still
      // computed from complete tokens only; a half-typed trailing word
      // produces verdict "typing" rather than out_of_domain.
      setResult(search(index, q, 24, { prefixLast: true }));
      setCommitted(q);
      setAsking(false);
    }, DEBOUNCE_MS);
    const banner = setTimeout(() => setBannerAllowed(true), BANNER_PAUSE_MS);
    return () => {
      clearTimeout(t); clearTimeout(banner); setAsking(false);
    };
  }, [q, index]);

  useEffect(() => {
    if (index && pending) { const t = pending; setPending(null); run(t); }
  }, [index, pending, run]);

  // Anything typed before the app took over the page is kept: a submitted
  // question is queued (it runs when the index is ready); unsubmitted text
  // stays in the box.
  useEffect(() => {
    const early = cleanQuery(takeEarlyQuery());
    const typed = cleanQuery(inputRef.current?.value ?? "");
    if (early.trim()) { setQ(early); setPending(early); }
    else if (typed.trim()) setQ(typed);
  }, []);

  const onSubmit = (e: React.FormEvent) => { e.preventDefault(); run(q); };

  // Prefer the live per-library maps (fetched from the active library's
  // snapshot); fall back to the SSR-provided LLM-cal props so legacy
  // single-library deploys keep working.
  const effectiveGaps = liveGaps ?? gaps;
  const effectivePapers = livePapers ?? papers;
  const gapBySlug = useMemo(
    () => new Map(effectiveGaps.map((g) => [g.slug, g])),
    [effectiveGaps]);
  const paperByWid = useMemo(
    () => new Map(effectivePapers.map((p) => [p.wid, p])),
    [effectivePapers]);

  // When the lookup map doesn't have a hit's ref (which happens on
  // libraries that ship a card the SSR props never saw), synth a
  // minimal GapDoc / PaperDoc from the hit's own fields so the result
  // STILL renders a card instead of silently dropping it.
  const gapHits = (result?.hits ?? [])
    .filter((h) => h.type === "opportunity")
    .map((h): GapDoc => gapBySlug.get(h.ref) ?? ({
      slug: h.ref,
      consumer: {
        headline: h.title, headline_is_quoted: false,
        kind: h.kind || "A result", kind_id: h.kind || "result",
        kind_short: "", kind_long: "",
        strength: h.strength || "Unverified lead",
        strength_meaning: "",
        why: "", caveats: [], paper_count: 0,
      },
      dev: { rank: 0, gap_type: h.kind || "" },
    } as unknown as GapDoc));
  const paperHits = (result?.hits ?? [])
    .filter((h) => h.type === "paper")
    .map((h): PaperDoc => paperByWid.get(h.ref) ?? ({
      wid: h.ref,
      title: h.title,
      year: null,
      abstract_only: false,
      domain_centrality: "",
      dev: { year: null, abstract_only: null, domain_centrality: "" },
    } as unknown as PaperDoc))
    .slice(0, 8);

  const S = lang.search;
  // Results render for in-domain / borderline / typing. Only
  // out_of_domain and empty hide the results pane. The OOD panel
  // further gates on bannerAllowed so nothing flashes mid-typing.
  const showResults = result
    && result.verdict !== "out_of_domain"
    && result.verdict !== "empty";
  const isTyping = result?.verdict === "typing" || !!result?.typing;
  // Personal distress: no research results, no "build a library" offer,
  // one calm message instead (lib/safety.ts). Checked on what is being typed
  // as well as what was submitted, so nothing flashes first.
  const distressed = distress(q) || distress(committed);

  return (
    <>
      <form className="ask" onSubmit={onSubmit} role="search"
            data-ready={index ? "" : undefined}>
        <label className="ask-box" htmlFor="ask-input">
          <SearchIcon className="ask-icon" />
          <input
            id="ask-input"
            ref={inputRef}
            value={q}
            onChange={(e) => setQ(cleanQuery(e.target.value))}
            maxLength={MAX_QUERY}
            dir="auto"
            placeholder={S.placeholder}
            aria-label={S.placeholder}
            autoComplete="off"
            spellCheck="false"
          />
          <button className="ask-btn" type="submit" disabled={!q.trim() || indexError}>
            {asking || pending ? "…" : "Ask"}
          </button>
        </label>

        {indexError ? (
          <div className="load-error ask-error" role="alert">
            <p><strong>Search couldn&rsquo;t load this library.</strong> The connection may have
              dropped, or the site was updated while this page was open.</p>
            <button type="button" className="cta" onClick={() => window.location.reload()}>
              Reload the page
            </button>
          </div>
        ) : (
          <p className="ask-hint" aria-live="polite">
            {!index
              ? (<><span className="swatch" aria-hidden /> {S.searching}{" "}
                  You can start typing.</>)
              : (<>Press <kbd className="inline-kbd">/</kbd> from anywhere to focus this.{tryHint ? ` ${tryHint}` : ""}</>)}
          </p>
        )}

        {examples.length > 0 && !indexError && (
          <div className="examples">
            <span className="label">Examples</span>
            {examples.map((ex) => (
              <button key={ex} type="button" className="example-chip"
                onClick={() => { setQ(ex); run(ex); }} disabled={indexError}>
                {ex}
              </button>
            ))}
          </div>
        )}
      </form>

      {/* data-lib: the library is known (on phones the library card waits
          for it, so it is never pushed down once shown). */}
      <div ref={resultsRef} className="ask-results"
           data-lib={activeLib ? "" : undefined}>
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

        {((asking && !result) || pending) && <ResultsSkeleton />}

        {result?.verdict === "empty" && (
          <EmptyHelp title={S.no_results.label}
                     body="Try naming the thing you want to know about."
                     covers={activeLib} examples={examples}
                     onPick={(ex) => { setQ(ex); run(ex); }} />
        )}

        {/* Out-of-domain banner is only allowed to render after a pause
            of about 700 ms or Enter — so a word being typed never
            flashes a refusal between keystrokes. */}
        {distressed && (
          <div className="distress-note" role="note" aria-live="polite" style={{ marginTop: "var(--s-6)" }}>
            <p>
              <strong>This is a research tool, not a support service.</strong> It reads academic
              papers and cannot help with how you are feeling.
            </p>
            <p>
              If you are struggling, you deserve support from a person. You can find a free,
              confidential helpline in your country at{" "}
              <a href={HELPLINE_URL} target="_blank" rel="noopener noreferrer">findahelpline.com</a>.
              If you are in immediate danger, contact your local emergency number.
            </p>
          </div>
        )}

        {!distressed && result?.verdict === "out_of_domain" && bannerAllowed && (
          <>
            {otherLibHits && (
              <div className="caveat" style={{ marginTop: "var(--s-6)" }}>
                <span className="cav-label">Maybe wrong library?</span>
                This looks like it's about the{" "}
                <strong>{otherLibHits.name}</strong> library.{" "}
                <a href={`?lib=${encodeURIComponent(otherLibHits.slug)}`}
                   onClick={() => handOffQuery(committed)}>
                  Switch and ask there →
                </a>
              </div>
            )}
            <OutOfDomain lang={lang} query={committed} activeLibrary={activeLib} />
          </>
        )}

        {!distressed && showResults && (
          <>
            <div className="verdict-line">
              <span className="count">
                {gapHits.length} gap{gapHits.length === 1 ? "" : "s"} ·{" "}
                {paperHits.length} paper{paperHits.length === 1 ? "" : "s"}
              </span>
              <span>for</span>
              <span className="query">“<bdi>{echoQuery(committed)}</bdi>”</span>
              {/* Edge-of-library tag held back until the banner is
                  allowed — same reason as the OOD panel. Never fires
                  during the typing state. */}
              {bannerAllowed && !isTyping && result.verdict === "borderline" && (
                <span style={{ color: "var(--note-icon)" }}>· at the edge of this library</span>
              )}
            </div>

            {/* Medical safety: in a library with a not-advice note (Diet),
                results always lead with it; advice-like phrasing adds a
                plain sentence that we cannot advise anyone. */}
            {activeLib?.not_advice_note && (
              <p className="not-advice" role="note" style={{ marginTop: "var(--s-3)" }}>
                {adviceLike(committed) && activeLib.health_adjacent && (
                  <><strong>This is research literature, not medical or parenting advice.</strong>{" "}
                  It only shows what research papers report.{" "}</>
                )}
                <strong>Note:</strong> {activeLib.not_advice_note}
              </p>
            )}

            {/* Typing hint: half-typed trailing word. Neutral — never
                a refusal or an edge label. */}
            {isTyping && result.trailing_prefix && (
              <p className="small muted" style={{ margin: "var(--s-2) 0 0" }}>
                Showing matches for &lsquo;{result.trailing_prefix}&hellip;&rsquo;.
                Press Enter to search the full word.
              </p>
            )}

            {bannerAllowed && !isTyping && result.verdict === "borderline" && (
              <div className="caveat" style={{ marginTop: 0 }}>
                <span className="cav-label">{S.borderline.label}</span>
                {S.borderline.note}
              </div>
            )}

            {gapHits.length === 0 && paperHits.length === 0 ? (
              <EmptyHelp title={S.no_results.label} body={S.no_results.note}
                         covers={activeLib} examples={examples}
                         onPick={(ex) => { setQ(ex); run(ex); }} />
            ) : (
              <>
                {gapHits.length > 0 ? (
                  <section style={{ marginTop: "var(--s-6)" }} key={runKey}
                           className={runKey ? "results-enter" : undefined}>
                    <p className="section-eyebrow" role="heading" aria-level={2}>Gaps we found</p>
                    <div className="results-list">
                      {gapHits.map((g) => (
                        <GapResult key={g.slug} gap={g} readMore={lang.ui.read_more} />
                      ))}
                    </div>
                  </section>
                ) : (
                  /* ZERO-GAP HONESTY: the library has papers matching
                     this query but no gap cards. Call it out in plain
                     language, reusing the library's own zero_finding_note
                     and coverage line (never hard-coded). */
                  <section style={{ marginTop: "var(--s-6)" }} className="empty">
                    <h2 className="empty-h">
                      {/* Count actual gap cards, not scorer_yields: a
                          yield (e.g. a code-only persistent-limitations
                          count) isn't a card the reader can open. */}
                      {liveGaps !== null && liveGaps.length === 0
                        ? "This library has no gaps to show yet."
                        : "No gaps match this search."}
                    </h2>
                    <p>
                      {paperHits.length > 0
                        ? `${paperHits.length} paper${paperHits.length === 1 ? "" : "s"} match${paperHits.length === 1 ? "es" : ""} below.`
                        : "No matching papers either."}
                    </p>
                    {liveGaps !== null && liveGaps.length === 0 && (
                      <p className="small muted">
                        None were found among the papers read, which is not the
                        same as none existing.
                      </p>
                    )}
                  </section>
                )}
                {paperHits.length > 0 && (
                  <section style={{ marginTop: "var(--s-7)" }}>
                    <p className="section-eyebrow" role="heading" aria-level={2}>Papers on this</p>
                    <div className="results-list papers">
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

      {/* Before a search: the library's safety note (the results repeat it
          at their top), then what you'll find. Both wait for the library to
          be known, so nothing on screen is pushed down when they arrive. */}
      {activeLib?.not_advice_note && !(showResults && !distressed) && (
        <p className="not-advice hero-note" role="note">
          <strong>Note:</strong> {activeLib.not_advice_note}
        </p>
      )}
      {activeLib && !result && !distressed && (
        <section className="hero-intro" aria-labelledby="what-youll-find">
          {activeLib.blurb && (
            <p className="covers"><strong>{activeLib.name}.</strong> {activeLib.blurb}</p>
          )}
          <h2 id="what-youll-find" className="intro-h">What you&rsquo;ll find</h2>
          <ul className="kinds-list">
            {Object.values(lang.kinds).map((k) => (
              <li key={k.id}>
                <span className="kind-name">{k.name}</span>
                <span className="kind-short">{k.short}</span>
              </li>
            ))}
          </ul>
          <p className="lede">{lang.ui.what_it_does}</p>
        </section>
      )}
    </>
  );
}

/** Nothing matched: say so, say what this library does cover, and offer its
 *  own example questions so the next try is one tap away. */
function EmptyHelp({ title, body, covers, examples, onPick }: {
  title: string; body: string;
  covers: { name: string; blurb?: string } | null;
  examples: string[];
  onPick: (ex: string) => void;
}) {
  return (
    <div className="empty empty-help" role="status">
      <h2 className="empty-h">{title}</h2>
      <p>{body}</p>
      {covers?.blurb && (
        <p className="empty-covers"><strong>This library covers:</strong> {covers.blurb}</p>
      )}
      {examples.length > 0 && (
        <div className="examples in-empty">
          <span className="label">Try</span>
          {examples.map((ex) => (
            <button key={ex} type="button" className="example-chip" onClick={() => onPick(ex)}>
              {ex}
            </button>
          ))}
        </div>
      )}
    </div>
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
function OutOfDomain({ lang, query, activeLibrary }: {
  lang: LanguagePack; query: string;
  activeLibrary: { slug: string; name: string; blurb?: string } | null;
}) {
  const blocked = panelBlocked(query);
  const harm = selfHarm(query);
  const [showBuild, setShowBuild] = useState(false);
  const [preflight, setPreflight] = useState<PreflightResult | null>(null);
  const [preflightState, setPreflightState] = useState<
    "idle" | "loading" | "ok" | "unavailable"
  >("idle");
  const [otherLibs, setOtherLibs] = useState<OtherLib[] | null>(null);
  const { dev } = useDev();
  const S = lang.search.out_of_domain;
  const B = lang.build_library;

  // Fetch the other libraries so the OOD panel can list switch links.
  useEffect(() => {
    let live = true;
    getLibraries()
      .then((m) => {
        if (!live || !m) return;
        const others = (m.libraries || [])
          .filter((l: any) => !activeLibrary || l.slug !== activeLibrary.slug);
        setOtherLibs(others);
        // Libraries whose index matches the query go first.
        matchingLibraries(others, query).then((hits) => {
          if (!live || !hits.length) return;
          const first = new Set(hits.map((h) => h.slug));
          setOtherLibs([...hits, ...others.filter((o: any) => !first.has(o.slug))]);
        });
      })
      .catch(() => {});
    return () => { live = false; };
  }, [activeLibrary]);

  // Prefer the active library's own copy. Falls back to the LLM-cal-
  // tuned language-pack strings when we don't yet know the library
  // (pre-hydration / legacy single-library deploy).
  const covers = activeLibrary?.blurb || lang.ui.library_covers;
  const summary = activeLibrary
    ? `Right now this library holds papers on ${activeLibrary.name.toLowerCase()}: ${activeLibrary.blurb || ""}`
    : lang.ui.library_summary;

  // Lazily fetch when the user opens the panel. Aborts if the panel
  // gets closed before the response returns.
  useEffect(() => {
    // Developer mode only: the consumer view never calls the pre-flight.
    if (!dev || !showBuild || preflightState !== "idle" || !query.trim()) return;
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
  }, [dev, showBuild, preflightState, query]);

  return (
    <div style={{ marginTop: "var(--s-7)" }}>
      <div className="empty">
        <h3>{S.label}</h3>
        <p>{S.note.replace("{covers}", covers)}</p>
      </div>

      <section className="block">
        <h2>{S.what_we_have}</h2>
        <p>{summary}</p>
        <p className="small" style={{ marginTop: "var(--s-4)" }}>
          <Link href={`/gaps/${activeLibrary ? `?lib=${activeLibrary.slug}` : ""}`}>
            {lang.ui.all_opportunities}
          </Link>
          <span className="foot-dot" style={{ margin: "0 var(--s-3)", color: "var(--rule-strong)" }}>·</span>
          <Link href={`/papers/${activeLibrary ? `?lib=${activeLibrary.slug}` : ""}`}>
            {lang.ui.all_papers}
          </Link>
        </p>
      </section>

      {otherLibs && otherLibs.length > 0 && (
        <section className="block">
          <h2>Other libraries you can try</h2>
          <ul className="foot-sources-list">
            {otherLibs.slice(0, OTHER_LIBS_SHOWN).map((lib) => (
              <li key={lib.slug}>
                <strong>{lib.name}</strong>
                {lib.blurb && (
                  <span className="foot-sources-note"> — {lib.blurb}</span>
                )}
                {" "}
                <a href={`?lib=${encodeURIComponent(lib.slug)}`} onClick={() => handOffQuery(query)}>
                  switch and ask there →
                </a>
              </li>
            ))}
          </ul>
          {otherLibs.length > OTHER_LIBS_SHOWN && (
            <details className="more-libs">
              <summary>All {otherLibs.length} other libraries</summary>
              <ul className="foot-sources-list">
                {otherLibs.slice(OTHER_LIBS_SHOWN).map((lib) => (
                  <li key={lib.slug}>
                    <strong>{lib.name}</strong>{" "}
                    <a href={`?lib=${encodeURIComponent(lib.slug)}`} onClick={() => handOffQuery(query)}>
                      switch and ask there →
                    </a>
                  </li>
                ))}
              </ul>
            </details>
          )}
        </section>
      )}

      {harm && (
        <p className="not-advice" role="note" style={{ marginTop: "var(--s-5)" }}>
          If you are thinking about harming yourself, you deserve support from a person: find a free
          helpline in your country at{" "}
          <a href={HELPLINE_URL} target="_blank" rel="noopener noreferrer">findahelpline.com</a>,
          or contact your local emergency number.
        </p>
      )}
      {blocked ? null : !showBuild ? (
        <button className="cta" onClick={() => setShowBuild(true)}>
          {S.build_cta} <span aria-hidden>→</span>
        </button>
      ) : (
        <div className="panel">
          <h2>{B.title}</h2>
          {!dev ? (
            <p>
              {B.consumer_body} <Link href="/contact/">Contact</Link>
            </p>
          ) : (<>
          {/* Developer mode only: says where the query goes before the
              pre-flight lookup's result appears. */}
          <p className="small muted" data-testid="dev-openalex-note">
            In developer mode, opening this panel sends your question, through the local server, to OpenAlex (api.openalex.org), a public catalogue of research papers, to estimate how much literature exists on it.
          </p>
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
                <span className="v" style={{ fontStyle: "italic" }}>“<bdi>{echoQuery(query)}</bdi>”</span>
              </div>
            )}
          </div>
          <p className="not-yet">{B.not_yet}</p>
          {B.predictor_note && (
            <p className="not-advice" role="note" style={{ marginTop: "var(--s-4)" }}>
              <strong>About the pre-flight number:</strong> {B.predictor_note}
            </p>
          )}
          </>)}
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
