"use client";
import { useMemo, useState } from "react";
import type { Opportunity, Tier } from "../../lib/types";
import OpportunityCard from "../components/OpportunityCard";

export default function OpportunitiesClient({ items }: { items: Opportunity[] }) {
  const [gap, setGap] = useState<string>("all");
  const [tier, setTier] = useState<string>("all");

  const gaps = useMemo(
    () => Array.from(new Set(items.map((o) => o.gap_type))).sort(),
    [items]
  );
  const shown = items.filter(
    (o) => (gap === "all" || o.gap_type === gap) && (tier === "all" || o.confidence_tier === tier)
  );

  return (
    <>
      <div className="filters">
        <label className="small muted">gap type</label>
        <select value={gap} onChange={(e) => setGap(e.target.value)}>
          <option value="all">all</option>
          {gaps.map((g) => (
            <option key={g} value={g}>{g.replace(/_/g, " ")}</option>
          ))}
        </select>
        <label className="small muted">confidence</label>
        <select value={tier} onChange={(e) => setTier(e.target.value)}>
          {(["all", "high", "medium", "low"] as (Tier | "all")[]).map((t) => (
            <option key={t} value={t}>{t}</option>
          ))}
        </select>
        <span className="spacer" />
        <span className="small muted">{shown.length} of {items.length}</span>
      </div>

      {shown.length === 0 ? (
        <div className="empty">
          No opportunities match this filter. Note that <strong>0 contradictions</strong>{" "}
          exist corpus-wide — candidates scale ~N^1.89 while confirmed stays at 0; see the
          findings. Try widening the filter.
        </div>
      ) : (
        shown.map((o) => <OpportunityCard key={o.id} o={o} />)
      )}
    </>
  );
}
