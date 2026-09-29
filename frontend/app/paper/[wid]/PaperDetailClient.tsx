"use client";
// Library-aware client wrapper for paper detail. Reads the active
// library, fetches paper/{wid}.json from that library's snapshot; if
// missing, shows a NotInLibrary fallback naming which other libraries
// may contain this wid.

import Link from "next/link";
import { Tag } from "../../components/plain";
import { DevKV, DevJSON } from "../../components/DevMode";
import GapSidebar from "../../gap/[slug]/GapSidebar";
import { useLibraryData, NotInLibrary } from "../../components/useLibraryData";
import type { PaperDetail, LanguagePack } from "../../../lib/types";

const wid = (pid: string) => pid.split(":").pop() as string;

export default function PaperDetailClient({ wid: routeWid, lang }: {
  wid: string;
  lang: LanguagePack;
}) {
  const res = useLibraryData<PaperDetail>(`paper/${routeWid}.json`);

  if (res.state === "loading") {
    return <p className="muted">Loading the paper…</p>;
  }
  if (res.state === "missing") {
    return (
      <NotInLibrary library={res.library} manifest={res.manifest}
                     kind="paper" id={routeWid} backHref="/papers/" />
    );
  }
  if (res.state === "error") {
    return <p className="muted">Couldn&apos;t load this paper.</p>;
  }

  const p = res.data;
  const c = p.consumer;
  const ownLimits = p.limitations.filter((l) => l.source_scope === "own_work");
  const priorLimits = p.limitations.filter((l) => l.source_scope !== "own_work");
  const librarySlug = res.library.slug;
  const librarySuffix = `?lib=${encodeURIComponent(librarySlug)}`;

  const sections: [string, string][] = [
    ...(p.abstract ? [["summary", "Summary"] as [string, string]] : []),
    ["claims", c.claims_label],
    ["limitations", c.limitations_label],
    ["future", c.future_work_label],
    ["methods", c.methods_label],
    ...((p.cites.length || p.cited_by.length)
        ? [["citations", c.citations_label] as [string, string]] : []),
  ];

  return (
    <div className="detail-grid">
      <div>
        <Link href={`/papers/${librarySuffix}`} className="crumb">
          <span aria-hidden>←</span> {lang.ui.all_papers}
        </Link>

        <header className="detail-head">
          <div className="result-head">
            <span>Paper</span>
            {p.year && (<><span className="sep" aria-hidden>·</span><span className="tnum">{p.year}</span></>)}
            {p.abstract_only
              ? <Tag warn>{lang.abstract_only.label}</Tag>
              : <Tag>{lang.full_text.label}</Tag>}
            <span className="sep" aria-hidden>·</span>
            <span className="small muted">{res.library.short_name}</span>
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
                      <Link href={`/paper/${wid(x.paper_id)}/${librarySuffix}`}>
                        {x.title ?? x.paper_id}
                      </Link>
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
                      <Link href={`/paper/${wid(x.paper_id)}/${librarySuffix}`}>
                        {x.title ?? x.paper_id}
                      </Link>
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
          library: res.library.slug,
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
