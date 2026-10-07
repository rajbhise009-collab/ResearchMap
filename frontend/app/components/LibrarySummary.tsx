"use client";
// One library's numbers, said once: a compact visible line, and the detail
// behind an accessible "How this library was built" toggle. Shared by the
// home card and the /gaps header so the wording is identical everywhere.
// Numbers come from site-facts.json (backend/app/api/site_facts.py).
import { useId, useState } from "react";
import type { SiteFactsLibrary } from "../../lib/types";

const plural = (n: number, one: string, many: string) => `${n} ${n === 1 ? one : many}`;

export default function LibrarySummary({ fact }: { fact: SiteFactsLibrary }) {
  const [open, setOpen] = useState(false);
  const panel = useId();
  return (
    <div className="lib-summary">
      <p className="lib-summary-line">
        {plural(fact.papers, "paper", "papers")} · {plural(fact.results_total, "result", "results")}
      </p>
      {fact.results_total === 0 && (
        <p className="lib-summary-zero small">
          No results yet: none were found among the papers read, which is not the same as none
          existing.
        </p>
      )}
      <button type="button" className="lib-summary-toggle" aria-expanded={open}
              aria-controls={panel} onClick={() => setOpen((v) => !v)}>
        How this library was built <span aria-hidden>{open ? "▴" : "▾"}</span>
      </button>
      <div id={panel} className="lib-summary-panel" hidden={!open}>
        <ul>
          <li>Read in full: {fact.full_text} of {fact.papers}.</li>
          <li>Claims extracted from: {fact.claims_read ?? "not measured"} of {fact.papers}.</li>
          {fact.results.map((r) => (
            <li key={r.type}>
              {r.count === null ? (
                <>{r.label.charAt(0).toUpperCase() + r.label.slice(1)}: {r.note}.</>
              ) : (
                <>{r.count} {r.label}{r.note ? <> — {r.note}.</> : "."}</>
              )}
            </li>
          ))}
          {fact.check_line && <li>{fact.check_line}</li>}
          <li>{fact.not_run}</li>
          <li>Library built {fact.built ?? "(date not measured)"}.</li>
        </ul>
      </div>
    </div>
  );
}
