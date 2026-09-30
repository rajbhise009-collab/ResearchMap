"use client";
// Static SVG timeline for a contradiction page. Shows:
// - Paper A's publication year (marker A)
// - Paper B's publication year (marker B)
// - Later cites-both papers as dots on the year axis
// Plus a screen-reader-visible list fallback.
//
// No chart library. Dark/light works because we use CSS custom
// properties for stroke/fill. Honest empty states.

import { useMemo } from "react";

export interface TimelineInput {
  a: { year: number | null; short: string };
  b: { year: number | null; short: string };
  citesBoth: Array<{ year?: number | null; title?: string | null }>;
  queryDate?: string;
}

export default function ContradictionTimeline({ a, b, citesBoth, queryDate }: TimelineInput) {
  const aYear = a.year ?? null;
  const bYear = b.year ?? null;

  // Build the year distribution + axis bounds.
  const laterYears = citesBoth
    .map((c) => c.year)
    .filter((y): y is number => Number.isFinite(y as number));
  const yearsWithAB = [
    ...(aYear != null ? [aYear] : []),
    ...(bYear != null ? [bYear] : []),
    ...laterYears,
  ];
  const yMin = yearsWithAB.length ? Math.min(...yearsWithAB) : null;
  const yMax = yearsWithAB.length ? Math.max(...yearsWithAB) : null;

  // Recency readout: N of the later papers are from the last 3 years
  // relative to the query date (or today if not given). Explicitly
  // presented as a rough sign, not a resolution.
  const referenceYear = useMemo(() => {
    if (queryDate) {
      const d = new Date(queryDate + "T00:00:00Z");
      if (!isNaN(d.getTime())) return d.getUTCFullYear();
    }
    return new Date().getUTCFullYear();
  }, [queryDate]);
  const recentCount = laterYears.filter((y) => y >= referenceYear - 3).length;
  const recencyLine = laterYears.length === 0
    ? null
    : (
      `${recentCount} of the ${laterYears.length} later papers citing both sides ${
        recentCount === 1 ? "is" : "are"
      } from the last 3 years — a rough sign the question is still discussed, not proof either side is right.`
    );

  // Nothing to draw: no cites-both AND both years missing.
  if (yMin == null || yMax == null || (aYear == null && bYear == null)) {
    return (
      <section id="timeline" className="block">
        <h2>Timeline</h2>
        <p className="muted">
          Not enough dated papers to draw a timeline. Showing one side's
          year alone would misrepresent the disagreement.
        </p>
      </section>
    );
  }

  // Axis: extend by ±1 year to avoid dots on the edge.
  const pad = 1;
  const lo = yMin - pad;
  const hi = Math.max(yMax + pad, referenceYear + pad);
  const range = hi - lo || 1;
  const W = 560;
  const H = 120;
  const marginX = 40;
  const midY = 60;
  const x = (y: number) => marginX + ((y - lo) / range) * (W - marginX * 2);

  // Bin the later years so overlapping dots stack visibly.
  const laterByYear = new Map<number, number>();
  for (const y of laterYears) laterByYear.set(y, (laterByYear.get(y) || 0) + 1);

  // Year ticks: every 2 years within the range.
  const ticks: number[] = [];
  for (let t = Math.ceil(lo / 2) * 2; t <= hi; t += 2) ticks.push(t);

  return (
    <section id="timeline" className="block">
      <h2>Timeline</h2>
      <p className="block-lede">
        When each side was published and when other papers cited both.
        {recencyLine && <> {recencyLine}</>}
      </p>
      <div className="timeline-wrap" aria-hidden="true">
        <svg viewBox={`0 0 ${W} ${H}`} width="100%" height={H}
              role="img"
              aria-label="Static timeline of the two disagreeing papers and later papers citing both.">
          {/* baseline */}
          <line x1={marginX} y1={midY} x2={W - marginX} y2={midY}
                 stroke="var(--rule-strong)" strokeWidth={1.5} />
          {/* year ticks */}
          {ticks.map((t) => (
            <g key={t}>
              <line x1={x(t)} y1={midY - 4} x2={x(t)} y2={midY + 4}
                     stroke="var(--rule-strong)" strokeWidth={1} />
              <text x={x(t)} y={midY + 22} textAnchor="middle"
                     fontSize="10" fill="var(--muted)">{t}</text>
            </g>
          ))}
          {/* later-cites dots (stacked when same year) */}
          {[...laterByYear.entries()].map(([y, n]) => (
            <g key={`c-${y}`}>
              {Array.from({ length: n }).map((_, i) => (
                <circle key={i}
                         cx={x(y)}
                         cy={midY - 10 - i * 6}
                         r={3}
                         fill="var(--accent)"
                         fillOpacity={0.7} />
              ))}
            </g>
          ))}
          {/* Paper A marker */}
          {aYear != null && (
            <g>
              <line x1={x(aYear)} y1={midY - 34} x2={x(aYear)} y2={midY + 8}
                     stroke="var(--fg)" strokeWidth={2} />
              <text x={x(aYear)} y={midY - 40} textAnchor="middle"
                     fontSize="11" fill="var(--fg)" fontWeight="bold">
                A · {aYear}
              </text>
            </g>
          )}
          {/* Paper B marker */}
          {bYear != null && (
            <g>
              <line x1={x(bYear)} y1={midY + 8} x2={x(bYear)} y2={midY + 40}
                     stroke="var(--fg)" strokeWidth={2} />
              <text x={x(bYear)} y={midY + 52} textAnchor="middle"
                     fontSize="11" fill="var(--fg)" fontWeight="bold">
                B · {bYear}
              </text>
            </g>
          )}
        </svg>
      </div>
      {/* Screen-reader-visible list fallback: same data as the SVG. */}
      <ul className="sr-only">
        {aYear != null && (
          <li>Paper A ({a.short}) published in {aYear}.</li>
        )}
        {bYear != null && (
          <li>Paper B ({b.short}) published in {bYear}.</li>
        )}
        {[...laterByYear.entries()]
          .sort(([y1], [y2]) => y1 - y2)
          .map(([y, n]) => (
            <li key={y}>
              {y}: {n} paper{n === 1 ? "" : "s"} citing both sides.
            </li>
          ))}
      </ul>
    </section>
  );
}
