"use client";
// Landing hero + stats card, library-scoped.
//
// Replaces the static hero content on the home page. Fetches the
// selected library's stats.json and meta.json at runtime and renders
// name / blurb / paper-count / disagreement-count that reflect the
// selection. Renders the library's not_advice_note when present
// (currently: diet only).

import { useEffect, useState } from "react";
import { useLibraries, useCurrentLibrary, LibrarySwitcher } from "./LibrarySwitcher";
import { asset } from "../../lib/basePath";
import type { SiteFactsLibrary } from "../../lib/types";

interface LibStats {
  papers?: number;
  full_text?: number;
  abstract_only?: number;
  n_extractions?: number;
  extraction_coverage_note?: string;
  zero_finding_note?: string | null;
  disagreement_check_note?: string | null;
  extraction_coverage_share?: number;
  n_confirmed_contradictions?: number;
  raw_flagged_contradictions?: number;
  scorer_yields?: Record<string, number>;
  note?: string;
}

export default function LibraryScopedHero({ tagline, whatItDoes, qualifier, facts }: {
  tagline: string;
  whatItDoes: string;
  qualifier?: string;
  facts: SiteFactsLibrary[];
}) {
  const libraries = useLibraries();
  const current = useCurrentLibrary(libraries);
  const [stats, setStats] = useState<LibStats | null>(null);
  const fact = current ? facts.find((f) => f.slug === current.slug) : undefined;

  useEffect(() => {
    if (!current) return;
    let live = true;
    fetch(asset(`${current.snapshot_path}/stats.json`))
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(String(r.status)))))
      .then((j: LibStats) => { if (live) setStats(j); })
      .catch(() => { if (live) setStats(null); });
    return () => { live = false; };
  }, [current]);

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
        {fact && (
          <p className="library-built">
            Library built {fact.built ?? "(date not measured)"} · {fact.papers} papers ·
            {" "}claims read from {fact.claims_read ?? "not measured"} of {fact.papers}
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
          <div>
            <dt>Papers</dt>
            <dd>
              <span className="num tnum">
                {stats?.papers ?? current?.n_papers ?? "…"}
              </span>
            </dd>
          </div>
          <div>
            <dt>Read in full</dt>
            <dd>
              <span className="num tnum">{stats?.full_text ?? "…"}</span>
              {stats?.papers != null && (
                <span className="small muted"> of {stats.papers} papers</span>
              )}
            </dd>
          </div>
          {stats?.n_extractions != null && (
            <div>
              <dt>Claims extracted from</dt>
              <dd>
                <span className="num tnum">{stats.n_extractions}</span>
                {stats?.papers != null && (
                  <span className="small muted"> of {stats.papers} papers</span>
                )}
              </dd>
            </div>
          )}
          <div>
            <dt>Results you can open</dt>
            <dd><span className="num tnum">{fact?.gap_cards ?? "…"}</span></dd>
          </div>
          {stats?.n_confirmed_contradictions != null && (
            <div>
              <dt>Disagreements kept after checking</dt>
              <dd><span className="num tnum">{stats.n_confirmed_contradictions}</span></dd>
            </div>
          )}
        </dl>
        {stats?.extraction_coverage_note && (
          <p className="small muted coverage-note">
            {stats.extraction_coverage_note}
          </p>
        )}
        {stats?.disagreement_check_note && (
          <p className="small muted coverage-note">
            {stats.disagreement_check_note}
          </p>
        )}
        {stats?.zero_finding_note && (
          <p className="small muted coverage-note">
            {stats.zero_finding_note}
          </p>
        )}
      </aside>
    </div>
  );
}
