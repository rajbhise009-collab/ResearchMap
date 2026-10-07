"use client";
// Landing hero + library card, library-scoped. The card shows the subject,
// one compact "<N> papers · <R> results" line and a "How this library was
// built" toggle (LibrarySummary); numbers come from site-facts.json, built
// at export time. Renders the library's not_advice_note when present.

import { useLibraries, useCurrentLibrary, LibrarySwitcher } from "./LibrarySwitcher";
import type { SiteFactsLibrary } from "../../lib/types";
import LibrarySummary from "./LibrarySummary";

export default function LibraryScopedHero({ tagline, whatItDoes, qualifier, facts }: {
  tagline: string;
  whatItDoes: string;
  qualifier?: string;
  facts: SiteFactsLibrary[];
}) {
  const libraries = useLibraries();
  const current = useCurrentLibrary(libraries);
  const fact = current ? facts.find((f) => f.slug === current.slug) : undefined;

  const libCount = libraries?.libraries.length ?? 1;
  const eyebrow = libCount > 1
    ? `Working prototype · ${libCount} libraries · currently viewing`
    : "Working prototype · One library";

  return (
    <div className="hero-grid">
      <div className="hero">
        <div className="eyebrow">{eyebrow}</div>
        <h1>{tagline}</h1>
        {qualifier && <p className="hero-qualifier">{qualifier}</p>}
        <p className="lede">{whatItDoes}</p>
        {/* Library-specific lines appear after the active library is known
            (client-side); their space is reserved so nothing below jumps. */}
        <div className="hero-libblock">
        {current && (
          <p className="covers">
            <strong>{current.name}.</strong>{" "}
            {current.blurb}
          </p>
        )}
        {current?.not_advice_note && (
          <p className="not-advice" role="note">
            <strong>Note:</strong> {current.not_advice_note}
          </p>
        )}
        </div>
      </div>

      <aside className="about-card" aria-label="About the selected library">
        <div className="kicker">
          <LibrarySwitcher />
        </div>
        <dl>
          <div>
            <dt>Subject</dt>
            <dd>{current?.name ?? "…"}</dd>
          </div>
        </dl>
        {fact ? <LibrarySummary fact={fact} /> : <p className="lib-summary-line">…</p>}
      </aside>
    </div>
  );
}
