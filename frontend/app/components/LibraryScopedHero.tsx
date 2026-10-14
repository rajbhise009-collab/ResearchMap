"use client";
// Landing hero + library card, library-scoped.
//
// Order is the reading order a first-time visitor needs: what this is (the
// headline), how far to trust it (the qualifier, at body size), then the one
// primary action (the search, passed in as children). What the tool looks for
// and the full description come after the search, and fold away while results
// are on screen (CSS :has) so results start right under the box. Safety notes
// (not_advice_note) are never folded away: the results repeat them at the top.
//
// The card shows the subject, one compact "<N> papers · <R> results" line and
// a "How this library was built" toggle (LibrarySummary); numbers come from
// site-facts.json, built at export time.

import type { ReactNode } from "react";
import { useLibraries, useCurrentLibrary, LibrarySwitcher } from "./LibrarySwitcher";
import type { Kind, SiteFactsLibrary } from "../../lib/types";
import LibrarySummary from "./LibrarySummary";

export default function LibraryScopedHero({ tagline, whatItDoes, qualifier, facts, kinds, children }: {
  tagline: string;
  whatItDoes: string;
  qualifier?: string;
  facts: SiteFactsLibrary[];
  kinds: Kind[];
  children?: ReactNode;
}) {
  const libraries = useLibraries();
  const current = useCurrentLibrary(libraries);
  const fact = current ? facts.find((f) => f.slug === current.slug) : undefined;

  const libCount = libraries?.libraries.length ?? 1;
  const eyebrow = libCount > 1
    ? <>Working prototype · {libCount} libraries · viewing{" "}
        <strong>{current?.short_name ?? "…"}</strong></>
    : "Working prototype · One library";

  return (
    <div className="hero-grid">
      <div className="hero">
        <div className="eyebrow"><span>{eyebrow}</span></div>
        <h1>{tagline}</h1>
        {qualifier && <p className="hero-qualifier">{qualifier}</p>}

        {children}

        {current?.not_advice_note && (
          <p className="not-advice hero-note" role="note">
            <strong>Note:</strong> {current.not_advice_note}
          </p>
        )}

        <section className="hero-intro" aria-labelledby="what-youll-find">
          {current && (
            <p className="covers">
              <strong>{current.name}.</strong>{" "}
              {current.blurb}
            </p>
          )}
          <h2 id="what-youll-find" className="intro-h">What you&rsquo;ll find</h2>
          <ul className="kinds-list">
            {kinds.map((k) => (
              <li key={k.id}>
                <span className="kind-name">{k.name}</span>
                <span className="kind-short">{k.short}</span>
              </li>
            ))}
          </ul>
          <p className="lede">{whatItDoes}</p>
        </section>
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
