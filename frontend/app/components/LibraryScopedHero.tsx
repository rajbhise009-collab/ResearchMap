"use client";
// Landing hero + library card, library-scoped.
//
// Order is the reading order a first-time visitor needs: what this is (the
// headline), how far to trust it (the qualifier, at body size), then the one
// primary action (the search, passed in as children). The library's safety
// note, what the tool looks for and the description follow the search box;
// Ask renders them, because it knows when results are on screen.
//
// The card shows the subject, one compact "<N> papers · <R> results" line and
// a "How this library was built" toggle (LibrarySummary); numbers come from
// site-facts.json, built at export time.

import type { ReactNode } from "react";
import { useLibraries, useCurrentLibrary, LibrarySwitcher } from "./LibrarySwitcher";
import type { SiteFactsLibrary } from "../../lib/types";
import LibrarySummary from "./LibrarySummary";

export default function LibraryScopedHero({ tagline, qualifier, facts, children }: {
  tagline: string;
  qualifier?: string;
  facts: SiteFactsLibrary[];
  children?: ReactNode;
}) {
  const libraries = useLibraries();
  const current = useCurrentLibrary(libraries);
  const fact = current ? facts.find((f) => f.slug === current.slug) : undefined;

  const libCount = libraries?.libraries.length ?? 1;
  // One line: the lead-in may shorten with an ellipsis on a narrow screen;
  // the library name never does.
  const eyebrow = libCount > 1
    ? <><span className="eb-lead">Working prototype · {libCount} libraries · viewing&nbsp;</span>
        <strong className="eb-name">{current?.short_name ?? "…"}</strong></>
    : <span className="eb-lead">Working prototype · One library</span>;

  return (
    <div className="hero-grid">
      <div className="hero">
        <div className="eyebrow eyebrow-line">{eyebrow}</div>
        <h1>{tagline}</h1>
        {qualifier && <p className="hero-qualifier">{qualifier}</p>}

        {children}

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
        {/* What the library covers lives with the rest of its details. */}
        {current?.blurb && <p className="card-covers">{current.blurb}</p>}
        {current?.not_advice_note && (
          <p className="not-advice card-note" role="note">
            <strong>Note:</strong> {current.not_advice_note}
          </p>
        )}
        {fact ? <LibrarySummary fact={fact} /> : <p className="lib-summary-line">…</p>}
      </aside>
    </div>
  );
}
