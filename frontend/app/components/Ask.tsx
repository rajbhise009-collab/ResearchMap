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
    { slug: string; name: string; blurb?: string } | null>(null);
  const [libStats, setLibStats] = useState<any | null>(null);

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
        const libResp = await fetch(asset("/data/libraries.json"));
        if (libResp.ok) {
          const manifest = await libResp.json();
          allLibs = manifest.libraries || [];
          const requested = new URLSearchParams(window.location.search).get("lib");
          const remembered = (() => {
            try { return window.localStorage.getItem("researchmap.library"); }
            catch { return null; }
          })();
          const slug = requested || remembered || manifest.default_slug;
          const lib = allLibs.find((l) => l.slug === slug) || allLibs[0];
          if (lib) {
            snapshotPath = lib.snapshot_path;
            activeSlug = lib.slug;
            if (live) {
              setActiveLib({ slug: lib.slug, name: lib.name,
                             blurb: (lib as any).blurb });
            }
          }
        }
      } catch { /* libraries.json missing — legacy deploy */ }
      try {
        const r = await fetch(asset(`${snapshotPath}/search-index.json`));
        if (!r.ok) throw new Error(String(r.status));
        const j: SearchIndex = await r.json();
        if (live) setIndex(j);
      } catch {
        if (live) setIndexError(true);
      }
      // Fetch opportunities + papers for the ACTIVE library so the
      // result-lookup maps are keyed on this library's slugs/wids.
      try {
        const [oppResp, papResp, statsResp] = await Promise.all([
          fetch(asset(`${snapshotPath}/opportunities.json`)),
          fetch(asset(`${snapshotPath}/papers.json`)),
          fetch(asset(`${snapshotPath}/stats.json`)),
        ]);
        if (statsResp.ok && live) {
          setLibStats(await statsResp.json());
        }
        if (oppResp.ok && live) {
          const oj = await oppResp.json();
          setLiveGaps((oj.items || []).map((o: any) => ({
            slug: o.slug, consumer: o.consumer,
            dev: { rank: o.rank ?? 0, gap_type: o.gap_type ?? "" },
          })));
        }
        if (papResp.ok && live) {
          const pj = await papResp.json();
          setLivePapers((pj.items || []).map((p: any) => ({
            wid: p.wid, title: p.title ?? p.wid,
            year: p.year, abstract_only: p.abstract_only,
            domain_centrality: p.domain_centrality,
            dev: { year: p.year, abstract_only: p.abstract_only ?? null,
                    domain_centrality: p.domain_centrality ?? "" },
          })));
        }
      } catch { /* missing — fall back to SSR props */ }
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
    (async () => {
      for (const other of others) {
        try {
          const r = await fetch(asset(`${other.snapshot_path}/search-index.json`));
          if (!r.ok) continue;
          const idx = await r.json();
          const probe = search(idx, committed, 1);
          if (probe.verdict === "in_domain" && live) {
            setOtherLibHits({ slug: other.slug, name: other.name });
            return;
          }
        } catch {}
      }
    })();
    return () => { live = false; };
  }, [result, committed]);

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

  // `banner` controls whether the borderline/out-of-domain banners are
  // allowed to render. Starts off while the user is typing and flips on
  // after BANNER_PAUSE_MS of silence or when they press Enter / Ask.
  // That way the typing path never flashes a refusal between keystrokes.
  const [bannerAllowed, setBannerAllowed] = useState(false);

  const run = useCallback((text: string) => {
    if (!index || !text.trim()) return;
    // Enter / Ask expands a trailing prefix to its best completion so
    // "alc" + Enter behaves like "alcohol" + Enter — the verdict reads
    // the full word.
    setResult(search(index, text, 24, { expandTrailing: true }));
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

        {/* Out-of-domain banner is only allowed to render after a pause
            of about 700 ms or Enter — so a word being typed never
            flashes a refusal between keystrokes. */}
        {result?.verdict === "out_of_domain" && bannerAllowed && (
          <>
            {otherLibHits && (
              <div className="caveat" style={{ marginTop: "var(--s-6)" }}>
                <span className="cav-label">Maybe wrong library?</span>
                This looks like it's about the{" "}
                <strong>{otherLibHits.name}</strong> library.{" "}
                <a href={`?lib=${encodeURIComponent(otherLibHits.slug)}&q=${encodeURIComponent(committed)}`}>
                  Switch and ask there →
                </a>
              </div>
            )}
            <OutOfDomain lang={lang} query={committed} activeLibrary={activeLib} />
          </>
        )}

        {showResults && (
          <>
            <div className="verdict-line">
              <span className="count">
                {gapHits.length} gap{gapHits.length === 1 ? "" : "s"} ·{" "}
                {paperHits.length} paper{paperHits.length === 1 ? "" : "s"}
              </span>
              <span>for</span>
              <span className="query">“{committed}”</span>
              {/* Edge-of-library tag held back until the banner is
                  allowed — same reason as the OOD panel. Never fires
                  during the typing state. */}
              {bannerAllowed && !isTyping && result.verdict === "borderline" && (
                <span style={{ color: "var(--note-icon)" }}>· at the edge of this library</span>
              )}
            </div>

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
              <div className="empty">
                <h3>{S.no_results.label}</h3>
                <p>{S.no_results.note}</p>
              </div>
            ) : (
              <>
                {gapHits.length > 0 ? (
                  <section style={{ marginTop: "var(--s-6)" }}>
                    <p className="section-eyebrow">Gaps we found</p>
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
                    <h3>
                      {/* Count actual gap cards, not scorer_yields: a
                          yield (e.g. a code-only persistent-limitations
                          count) isn't a card the reader can open. */}
                      {liveGaps !== null && liveGaps.length === 0
                        ? "This library has no gaps to show yet."
                        : "No gaps match this search."}
                    </h3>
                    <p>
                      {paperHits.length > 0
                        ? `${paperHits.length} paper${paperHits.length === 1 ? "" : "s"} match${paperHits.length === 1 ? "es" : ""} below.`
                        : "No matching papers either."}
                    </p>
                    {libStats?.zero_finding_note && (
                      <p className="small muted">
                        {libStats.zero_finding_note}{" "}
                        {libStats.extraction_coverage_note}
                      </p>
                    )}
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
function OutOfDomain({ lang, query, activeLibrary }: {
  lang: LanguagePack; query: string;
  activeLibrary: { slug: string; name: string; blurb?: string } | null;
}) {
  const [showBuild, setShowBuild] = useState(false);
  const [preflight, setPreflight] = useState<PreflightResult | null>(null);
  const [preflightState, setPreflightState] = useState<
    "idle" | "loading" | "ok" | "unavailable"
  >("idle");
  const [otherLibs, setOtherLibs] = useState<
    Array<{ slug: string; name: string; blurb?: string }> | null>(null);
  const { dev } = useDev();
  const S = lang.search.out_of_domain;
  const B = lang.build_library;

  // Fetch the other libraries so the OOD panel can list switch links.
  useEffect(() => {
    let live = true;
    fetch(asset("/data/libraries.json"))
      .then((r) => (r.ok ? r.json() : Promise.reject()))
      .then((m) => {
        if (!live) return;
        const others = (m.libraries || [])
          .filter((l: any) => !activeLibrary || l.slug !== activeLibrary.slug);
        setOtherLibs(others);
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
            {otherLibs.map((lib) => (
              <li key={lib.slug}>
                <strong>{lib.name}</strong>
                {lib.blurb && (
                  <span className="foot-sources-note"> — {lib.blurb}</span>
                )}
                {" "}
                <a href={`?lib=${encodeURIComponent(lib.slug)}&q=${encodeURIComponent(query)}`}>
                  switch and ask there →
                </a>
              </li>
            ))}
          </ul>
        </section>
      )}

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
          {B.predictor_note && (
            <p className="not-advice" role="note" style={{ marginTop: "var(--s-4)" }}>
              <strong>About the pre-flight number:</strong> {B.predictor_note}
            </p>
          )}
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
