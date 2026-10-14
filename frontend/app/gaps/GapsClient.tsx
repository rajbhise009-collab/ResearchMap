"use client";
import { useState, type ReactNode } from "react";
import Link from "next/link";
import type { GapDoc, LanguagePack } from "../../lib/types";
import { GapResult } from "../components/ResultCard";

// The list sits in the reading column; the library summary and the filters
// sit in the aside (sticky on wide screens, above the list on phones).
// `after` is anything that belongs under the list in the same column.
export default function GapsClient({ gaps, lang, aside, after }: {
  gaps: GapDoc[];
  lang: LanguagePack;
  aside?: ReactNode;
  after?: ReactNode;
}) {
  const [kind, setKind] = useState("all");
  const [strength, setStrength] = useState("all");

  const shown = gaps.filter(
    (g) =>
      (kind === "all" || g.consumer.kind_id === kind) &&
      (strength === "all" || g.consumer.strength === strength)
  );

  const kinds = Object.values(lang.kinds);
  const strengths = Object.keys(lang.strength_meaning)
    .sort((a, b) => lang.strength_order[a] - lang.strength_order[b]);

  // Asking for disagreements is the one filter that can legitimately come
  // back empty, and the reason is a finding rather than a gap in the data.
  const askedForDisagreements = kind === "disagreement";

  return (
    <div className="page-grid">
      <aside className="page-aside" aria-label="This library and filters">
      {aside}
      <div className="filters">
        <label>
          kind
          <select value={kind} onChange={(e) => setKind(e.target.value)}>
            <option value="all">everything</option>
            {kinds.map((k) => (
              <option key={k.id} value={k.id}>{k.name}</option>
            ))}
          </select>
        </label>
        <label>
          how sure
          <select value={strength} onChange={(e) => setStrength(e.target.value)}>
            <option value="all">any</option>
            {strengths.map((s) => (
              <option key={s} value={s}>{s}</option>
            ))}
          </select>
        </label>
        <span className="count">{shown.length} of {gaps.length}</span>
      </div>
      </aside>
      <div className="page-main">

      {kind !== "all" && (
        <p className="small muted sans" style={{ margin: "0 0 var(--s-4)" }}>
          {kinds.find((k) => k.id === kind)?.long}
        </p>
      )}

      {shown.length === 0 ? (
        askedForDisagreements ? (
          <div className="empty" style={{ marginTop: "2rem" }}>
            <h2 className="empty-h">{lang.no_disagreements.headline}</h2>
            <p>{lang.no_disagreements.body}</p>
            <p className="small">
              <Link href="/library/">{lang.no_disagreements.link_label} →</Link>
            </p>
          </div>
        ) : (
          <div className="empty" style={{ marginTop: "2rem" }}>
            <h2 className="empty-h">Nothing matches those filters</h2>
            <p>Widen them and everything comes back.</p>
            <p className="small">
              <button type="button" className="text-btn"
                      onClick={() => { setKind("all"); setStrength("all"); }}>
                Show everything
              </button>
            </p>
          </div>
        )
      ) : (
        <div className="results-list">
          <h2 className="sr-only">Results</h2>
          {shown.map((g) => (
            <GapResult key={g.slug} gap={g} readMore={lang.ui.read_more} />
          ))}
        </div>
      )}
      {after}
      </div>
    </div>
  );
}
