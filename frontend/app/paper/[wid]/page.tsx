import Link from "next/link";
import { getPapers, getPaper, getLanguage } from "../../../lib/data";
import { Tag } from "../../components/plain";
import { DevKV, DevJSON } from "../../components/DevMode";

export function generateStaticParams() {
  return getPapers().map((p) => ({ wid: p.wid }));
}

const wid = (pid: string) => pid.split(":").pop() as string;

export default function PaperDetail({ params }: { params: { wid: string } }) {
  const p = getPaper(params.wid);
  const lang = getLanguage();
  const c = p.consumer;

  // What the authors said about their own work, kept separate from what
  // they said about everyone else's — only the former tells you where this
  // paper ran out of road.
  const ownLimits = p.limitations.filter((l) => l.source_scope === "own_work");
  const priorLimits = p.limitations.filter((l) => l.source_scope !== "own_work");

  return (
    <>
      <Link href="/papers/" className="crumb">← {lang.ui.all_papers}</Link>

      <div className="detail-head">
        <div className="result-kind">
          <span>Paper</span>
          {p.year && (<><span aria-hidden>·</span><span>{p.year}</span></>)}
          {p.abstract_only
            ? <Tag warn>{lang.abstract_only.label}</Tag>
            : <Tag>{lang.full_text.label}</Tag>}
        </div>
        <h1>{p.title}</h1>
        {p.doi && (
          <p className="small muted sans">
            <a href={`https://doi.org/${p.doi}`} target="_blank" rel="noreferrer">
              doi.org/{p.doi} ↗
            </a>
          </p>
        )}
      </div>

      {p.abstract_only && (
        <div className="caveat">
          <span className="cav-label">{c.fidelity.label}</span>
          {c.fidelity.text}
        </div>
      )}

      {p.abstract && (
        <section className="block">
          <h2>Summary</h2>
          <p>{p.abstract}</p>
        </section>
      )}

      <section className="block">
        <h2>{c.claims_label}</h2>
        {p.claims.length ? (
          <ul className="quote-list">
            {p.claims.map((x) => <li key={x.id}>{x.text}</li>)}
          </ul>
        ) : <p className="muted">{c.no_claims}</p>}
      </section>

      <section className="block">
        <h2>{c.limitations_label}</h2>
        {ownLimits.length ? (
          <ul className="quote-list">
            {ownLimits.map((x) => <li key={x.id}>{x.text}</li>)}
          </ul>
        ) : <p className="muted">{c.no_limitations}</p>}
        {priorLimits.length > 0 && (
          <>
            <p className="section-label" style={{ margin: "1.6rem 0 0.5rem" }}>
              And what they said didn&apos;t work in earlier research
            </p>
            <ul className="quote-list">
              {priorLimits.map((x) => <li key={x.id}>{x.text}</li>)}
            </ul>
          </>
        )}
      </section>

      <section className="block">
        <h2>{c.future_work_label}</h2>
        {p.future_work.length ? (
          <ul className="quote-list">
            {p.future_work.map((x) => <li key={x.id}>{x.text}</li>)}
          </ul>
        ) : <p className="muted">{c.no_future_work}</p>}
      </section>

      <section className="block">
        <h2>{c.methods_label}</h2>
        {p.methodologies.length ? (
          <ul className="quote-list">
            {p.methodologies.map((m) => (
              <li key={m.id}>
                <strong>{m.name}</strong>
                {m.description && <><br />{m.description}</>}
              </li>
            ))}
          </ul>
        ) : <p className="muted">{c.no_methods}</p>}
      </section>

      {(p.cites.length > 0 || p.cited_by.length > 0) && (
        <section className="block">
          <h2>{c.citations_label}</h2>
          {p.cites.length > 0 && (
            <>
              <p className="section-label">This paper builds on</p>
              {p.cites.map((x) => (
                <div className="paper-line" key={`c-${x.paper_id}`}>
                  <span className="t">
                    <Link href={`/paper/${wid(x.paper_id)}/`}>{x.title ?? x.paper_id}</Link>
                  </span>
                </div>
              ))}
            </>
          )}
          {p.cited_by.length > 0 && (
            <>
              <p className="section-label" style={{ marginTop: "1.6rem" }}>
                Later papers here that build on it
              </p>
              {p.cited_by.map((x) => (
                <div className="paper-line" key={`b-${x.paper_id}`}>
                  <span className="t">
                    <Link href={`/paper/${wid(x.paper_id)}/`}>{x.title ?? x.paper_id}</Link>
                  </span>
                </div>
              ))}
            </>
          )}
        </section>
      )}

      <DevKV title={lang.dev.provenance_heading} data={{
        paper_id: p.paper_id,
        input_source: p.input_source,
        abstract_only: p.abstract_only,
        domain_centrality: p.domain_centrality,
        provenance: p.provenance ?? "null",
        doi: p.doi ?? "null",
        claims: p.claims.length,
        limitations_own: ownLimits.length,
        limitations_prior: priorLimits.length,
        future_work: p.future_work.length,
        methodologies: p.methodologies.length,
      }} />
      <DevJSON title={lang.dev.json_heading} data={p} />
    </>
  );
}
