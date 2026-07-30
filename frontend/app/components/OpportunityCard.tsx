import Link from "next/link";
import type { Opportunity } from "../../lib/types";
import { TierBadge, GapPill, ConfirmBadge } from "./badges";
import Caveats from "./Caveats";

export default function OpportunityCard({ o }: { o: Opportunity }) {
  const isHole = o.scorer === "structural_holes";
  const weak = o.confidence_tier === "low" || (isHole && o.confirm_status !== "substantive");
  return (
    <div className={`card${weak ? " weak" : ""}`}>
      <div className="row">
        <span className="mono muted">#{o.rank}</span>
        <GapPill gap={o.gap_type} />
        <TierBadge tier={o.confidence_tier} />
        {isHole && <ConfirmBadge status={o.confirm_status} />}
        <span className="spacer" />
        <span className="small muted mono" title="score × confidence">
          trust {o.trust.toFixed(2)}
        </span>
      </div>
      <h3 style={{ margin: "10px 0 4px" }}>
        <Link href={`/opportunities/${o.slug}/`}>{o.title}</Link>
      </h3>
      <div className="small muted mono">
        score {o.score.toFixed(3)} · confidence {o.confidence.toFixed(2)} ·{" "}
        {o.supporting_papers.length} paper{o.supporting_papers.length === 1 ? "" : "s"}
      </div>
      <Caveats caveats={o.caveats} />
    </div>
  );
}
