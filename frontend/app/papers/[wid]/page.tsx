import Link from "next/link";
import { getPapers, getPaper } from "../../../lib/data";
import { AbstractBadge } from "../../components/badges";

export function generateStaticParams() {
  return getPapers().map((p) => ({ wid: p.wid }));
}

export default function PaperDetailPage({ params }: { params: { wid: string } }) {
  const p = getPaper(params.wid);
  return (
    <>
      <p className="small"><Link href="/papers/">← all papers</Link></p>
      <div className="row" style={{ marginTop: 8 }}>
        <span className="pill">{p.domain_centrality}</span>
        {p.abstract_only ? <AbstractBadge /> : <span className="pill">full text</span>}
        {p.provenance && <span className="pill">{p.provenance}</span>}
        {p.year && <span className="small muted">{p.year}</span>}
      </div>
      <h1 style={{ marginTop: 8 }}>{p.title}</h1>
      <div className="small muted mono">
        {p.paper_id}
        {p.doi && <> · doi:{p.doi}</>}
      </div>
      {p.abstract_only && (
        <div className="caveat" style={{ marginTop: 10 }}>
          <span className="k">Abstract-only:</span>
          <span>
            No full text was recovered. Abstract-only papers yield ~11× fewer own-work
            limitations and ~13× fewer future-work items than full text — a fidelity
            caveat on everything extracted here.
          </span>
        </div>
      )}

      {p.abstract && (
        <>
          <h2>Abstract</h2>
          <p className="small">{p.abstract}</p>
        </>
      )}

      <Section title={`Claims (${p.claims.length})`}>
        {p.claims.map((c) => (
          <div className="trail-item" key={c.id}>
            <span className="tag">{c.type}</span> {c.text}
          </div>
        ))}
      </Section>

      <Section title={`Own-work & prior limitations (${p.limitations.length})`}>
        {p.limitations.map((l) => (
          <div className="trail-item" key={l.id}>
            <span className="tag">{l.source_scope} · {l.normalized_category}</span> {l.text}
          </div>
        ))}
      </Section>

      <Section title={`Future work (${p.future_work.length})`}>
        {p.future_work.map((f) => (
          <div className="trail-item" key={f.id}>{f.text}</div>
        ))}
      </Section>

      <Section title={`Methodologies (${p.methodologies.length})`}>
        {p.methodologies.map((m) => (
          <div className="trail-item" key={m.id}>
            <strong>{m.name}</strong>
            {m.description && <div className="small muted">{m.description}</div>}
          </div>
        ))}
      </Section>

      {(p.cites.length > 0 || p.cited_by.length > 0) && (
        <>
          <h2>Citations within corpus</h2>
          <div className="grid2">
            <div>
              <div className="tag">cites ({p.cites.length})</div>
              {p.cites.map((c) => (
                <div key={c.paper_id} className="small">
                  <Link href={`/papers/${c.paper_id.split(":").pop()}/`}>{c.title ?? c.paper_id}</Link>
                </div>
              ))}
            </div>
            <div>
              <div className="tag">cited by ({p.cited_by.length})</div>
              {p.cited_by.map((c) => (
                <div key={c.paper_id} className="small">
                  <Link href={`/papers/${c.paper_id.split(":").pop()}/`}>{c.title ?? c.paper_id}</Link>
                </div>
              ))}
            </div>
          </div>
        </>
      )}
    </>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  const arr = Array.isArray(children) ? children : [children];
  return (
    <>
      <h2>{title}</h2>
      {arr.length > 0 && (arr as any[]).some(Boolean) ? (
        <div className="trail">{children}</div>
      ) : (
        <p className="small muted">None extracted.</p>
      )}
    </>
  );
}
