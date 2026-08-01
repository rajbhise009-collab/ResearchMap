import Link from "next/link";
import { getPapers, getPaper, getLanguage } from "../../../lib/data";
import { Tag } from "../../components/plain";
import { DevKV, DevJSON } from "../../components/DevMode";
import GapSidebar from "../../gap/[slug]/GapSidebar";

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

  const sections: [string, string][] = [
    ...(p.abstract ? [["summary", "Summary"] as [string, string]] : []),
    ["claims", c.claims_label],
    ["limitations", c.limitations_label],
    ["future", c.future_work_label],
    ["methods", c.methods_label],
    ...((p.cites.length || p.cited_by.length) ? [["citations", c.citations_label] as [string, string]] : []),
  ];

  return (
    <div className="detail-grid">
      <div>
        <Link href="/papers/" className="crumb">
          <span aria-hidden>←</span> {lang.ui.all_papers}
        </Link>

        <header className="detail-head">
          <div className="result-head">
            <span>Paper</span>
            {p.year && (<><span className="sep" aria-hidden>·</span><span className="tnum">{p.year}</span></>)}
            {p.abstract_only
              ? <Tag warn>{lang.abstract_only.label}</Tag>
              : <Tag>{lang.full_text.label}</Tag>}
          </div>
          <h1>{p.title}</h1>
          {p.doi && (
            <p className="subtitle">
              <a href={`https://doi.org/${p.doi}`} target="_blank" rel="noreferrer">
                doi.org/{p.doi} ↗
              </a>
            </p>
          )}
        </header>

        {p.abstract_only && (
          <div className="caveat">
            <span className="cav-label">{c.fidelity.label}</span>
            {c.fidelity.text}
          </div>
        )}

        {p.abstract && (
          <section id="summary" className="block">
            <h2>Summary</h2>
            <p>{p.abstract}</p>
          </section>
        )}

        <section id="claims" className="block">
          <h2>{c.claims_label}</h2>
          {p.claims.length ? (
            <ul className="quote-list">
              {p.claims.map((x) => <li key={x.id}>{x.text}</li>)}
            </ul>
          ) : <p className="muted">{c.no_claims}</p>}
        </section>

        <section id="limitations" className="block">
          <h2>{c.limitations_label}</h2>
          {ownLimits.length ? (
            <ul className="quote-list">
              {ownLimits.map((x) => <li key={x.id}>{x.text}</li>)}
            </ul>
          ) : <p className="muted">{c.no_limitations}</p>}
          {priorLimits.length > 0 && (
            <>
              <p className="section-eyebrow" style={{ marginTop: "var(--s-6)" }}>
                And what they said didn&apos;t work in earlier research
              </p>
              <ul className="quote-list">
                {priorLimits.map((x) => <li key={x.id}>{x.text}</li>)}
              </ul>
            </>
          )}
        </section>

        <section id="future" className="block">
          <h2>{c.future_work_label}</h2>
          {p.future_work.length ? (
            <ul className="quote-list">
              {p.future_work.map((x) => <li key={x.id}>{x.text}</li>)}
            </ul>
          ) : <p className="muted">{c.no_future_work}</p>}
        </section>

        <section id="methods" className="block">
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
          <section id="citations" className="block">
            <h2>{c.citations_label}</h2>
            {p.cites.length > 0 && (
              <>
                <p className="section-eyebrow">This paper builds on</p>
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
                <p className="section-eyebrow" style={{ marginTop: "var(--s-6)" }}>
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
      </div>

      <GapSidebar sections={sections} />
    </div>
  );
}
