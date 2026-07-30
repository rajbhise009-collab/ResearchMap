import Link from "next/link";
import { getOpportunities, getOpportunity } from "../../../lib/data";
import { TierBadge, GapPill, ConfirmBadge, AbstractBadge } from "../../components/badges";
import Caveats from "../../components/Caveats";

export function generateStaticParams() {
  return getOpportunities().map((o) => ({ slug: o.slug }));
}

const wid = (pid: string) => pid.split(":").pop() as string;

export default function OpportunityDetail({ params }: { params: { slug: string } }) {
  const o = getOpportunity(params.slug);
  const isHole = o.scorer === "structural_holes";
  return (
    <>
      <p className="small"><Link href="/opportunities/">← all opportunities</Link></p>
      <div className="row" style={{ marginTop: 8 }}>
        <span className="mono muted">#{o.rank}</span>
        <GapPill gap={o.gap_type} />
        <TierBadge tier={o.confidence_tier} />
        {isHole && <ConfirmBadge status={o.confirm_status} />}
      </div>
      <h1 style={{ marginTop: 10 }}>{o.title}</h1>
      <div className="small muted mono">
        scorer {o.scorer} · score {o.score.toFixed(3)} · confidence {o.confidence.toFixed(2)}{" "}
        · trust {o.trust.toFixed(3)}
      </div>

      <Caveats caveats={o.caveats} />

      <h2>Explanation</h2>
      <p>{o.explanation}</p>

      <h2>Component scores</h2>
      <div className="kv mono">
        {Object.entries(o.component_scores).map(([k, v]) => (
          <div key={k} style={{ display: "contents" }}>
            <span className="k">{k}</span>
            <span>{v}</span>
          </div>
        ))}
      </div>

      <h2>Supporting papers</h2>
      {o.supporting_papers.map((p) => (
        <div className="row" key={p.paper_id} style={{ padding: "6px 0" }}>
          <Link href={`/papers/${wid(p.paper_id)}/`}>{p.title ?? p.paper_id}</Link>
          {p.abstract_only && <AbstractBadge />}
          <span className="pill">{p.domain_centrality}</span>
          {p.year && <span className="small muted">{p.year}</span>}
        </div>
      ))}

      <h2>Evidence trail</h2>
      <p className="small muted">
        Every item resolves to a source record — the reasoning is fully traceable.
      </p>
      <div className="trail">
        {o.evidence_trail.map((e, i) => (
          <div className="trail-item" key={i}>
            <span className="tag">{e.kind}</span>{" "}
            {e.paper_id ? (
              <Link href={`/papers/${wid(e.paper_id)}/`} className="mono">
                {e.id}
              </Link>
            ) : (
              <span className="mono">{e.id}</span>
            )}
            {e.text && <div className="small" style={{ marginTop: 3 }}>{e.text}</div>}
          </div>
        ))}
      </div>

      {o.relationship_ids.length > 0 && (
        <>
          <h2>Relationship IDs</h2>
          <ul className="small mono">
            {o.relationship_ids.map((r) => <li key={r}>{r}</li>)}
          </ul>
        </>
      )}
    </>
  );
}
