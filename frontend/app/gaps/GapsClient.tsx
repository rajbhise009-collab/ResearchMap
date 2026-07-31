"use client";
import { useState } from "react";
import Link from "next/link";
import type { GapDoc, LanguagePack } from "../../lib/types";
import { GapResult } from "../components/ResultCard";

export default function GapsClient({ gaps, lang }: {
  gaps: GapDoc[];
  lang: LanguagePack;
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
    <>
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

      {kind !== "all" && (
        <p className="small muted sans" style={{ margin: "1rem 0 0" }}>
          {kinds.find((k) => k.id === kind)?.long}
        </p>
      )}

      {shown.length === 0 ? (
        askedForDisagreements ? (
          <div className="empty" style={{ marginTop: "2rem" }}>
            <h3>{lang.no_disagreements.headline}</h3>
            <p>{lang.no_disagreements.body}</p>
            <p className="small">
              <Link href="/library/">{lang.no_disagreements.link_label} →</Link>
            </p>
          </div>
        ) : (
          <div className="empty" style={{ marginTop: "2rem" }}>
            <h3>Nothing matches those filters</h3>
            <p>Widen them and everything comes back.</p>
          </div>
        )
      ) : (
        <div className="results">
          {shown.map((g) => (
            <GapResult key={g.slug} gap={g} readMore={lang.ui.read_more} />
          ))}
        </div>
      )}
    </>
  );
}
