"use client";
import Link from "next/link";
import { DevKV } from "../components/DevMode";
import { useLibraryData } from "../components/useLibraryData";
import type { Stats, LanguagePack, SiteFactsLibrary } from "../../lib/types";

interface OpportunitiesFile {
  total: number;
  items: Array<{ slug: string; consumer: { kind_id: string } }>;
}
interface FindingsFile { items: Array<{ slug: string; title: string }>; }

export default function LibraryPageClient({ lang, facts }: {
  lang: LanguagePack; facts: SiteFactsLibrary[];
}) {
  const statsRes = useLibraryData<Stats>("stats.json");
  const oppsRes = useLibraryData<OpportunitiesFile>("opportunities.json");
  const findingsRes = useLibraryData<FindingsFile>("findings.json");

  const stats = statsRes.state === "ready" ? statsRes.data : null;
  const opps = oppsRes.state === "ready" ? oppsRes.data.items : [];
  const findings = findingsRes.state === "ready" ? findingsRes.data.items : [];
  const library = statsRes.state === "ready" ? statsRes.library
                    : oppsRes.state === "ready" ? oppsRes.library : null;
  const suffix = library ? `?lib=${encodeURIComponent(library.slug)}` : "";

  const byKind = new Map<string, number>();
  for (const o of opps) {
    byKind.set(o.consumer.kind_id,
                (byKind.get(o.consumer.kind_id) || 0) + 1);
  }
  const kinds = Object.values(lang.kinds);

  if (statsRes.state === "loading") {
    return <p className="muted">Loading library composition…</p>;
  }

  return (
    <>
      <div className="hero" style={{ marginBottom: "var(--s-7)" }}>
        <div className="eyebrow">The library · Composition and findings</div>
        <h1 style={{ fontSize: "clamp(1.9rem, 3.6vw, 2.6rem)" }}>
          {library?.name ?? "The library"}
        </h1>
        <p className="lede">
          What is in the {library?.short_name ?? "this"} library, what we could
          read of it, and what the tool found when it looked.
        </p>
        {(() => {
          const f = library ? facts.find((x) => x.slug === library.slug) : undefined;
          return f ? (
            <p className="library-built">
              Library built {f.built ?? "(date not measured)"} · {f.papers} papers ·
              {" "}claims read from {f.claims_read ?? "not measured"} of {f.papers}
            </p>
          ) : null;
        })()}
        {library?.not_advice_note && (
          <p className="not-advice" role="note">
            <strong>Note:</strong> {library.not_advice_note}
          </p>
        )}
      </div>

      {stats && (
        <section className="block">
          <h2>What it holds</h2>
          <p>{stats.papers} papers on {library?.blurb ?? "this subject"}.</p>
          <p>
            We could read {stats.full_text} of them in full. For the other{" "}
            {stats.abstract_only} we only had the summary — and that matters
            more than it sounds: {lang.abstract_only.text.toLowerCase()}
          </p>
          {stats.extraction_coverage_note && (
            <p className="small muted">{stats.extraction_coverage_note}</p>
          )}
          {stats.disagreement_check_note && (
            <p className="small muted">{stats.disagreement_check_note}</p>
          )}
          <p className="small">
            <Link href={`/papers/${suffix}`}>Browse all {stats.papers} papers →</Link>
          </p>
        </section>
      )}

      <section className="block">
        <h2>What the tool found</h2>
        {kinds.map((k) => {
          const n = byKind.get(k.id) || 0;
          if (n === 0 && k.id === "disagreement") {
            return (
              <div className="empty" key={k.id}>
                <h3>{lang.no_disagreements.headline}</h3>
                <p>{lang.no_disagreements.body}</p>
                {findings.length > 0 && (
                  <p className="small">
                    <Link href={`/findings/${findings[0].slug}/`}>
                      {lang.no_disagreements.link_label} →
                    </Link>
                  </p>
                )}
              </div>
            );
          }
          return (
            <div className="evidence-item" key={k.id}>
              <div className="src">
                <strong className="tnum" style={{
                  color: "var(--ink-strong)",
                  fontFamily: "var(--font-sans)",
                  fontSize: "var(--step-1)",
                }}>{n}</strong>
                <span>{k.name.toLowerCase()}</span>
              </div>
              <p style={{ margin: 0 }}>{k.long}</p>
              {n > 0 && (
                <p className="small" style={{ marginTop: "var(--s-3)" }}>
                  <Link href={`/gaps/${suffix}`}>See them →</Link>
                </p>
              )}
            </div>
          );
        })}
      </section>

      <section className="block">
        <h2>{lang.ui.findings_heading}</h2>
        <p>{lang.ui.findings_intro}</p>
        {lang.ui.budget_note && <p className="small muted">{lang.ui.budget_note}</p>}
        {stats?.audit_doubts && stats.audit_doubts.length > 0 && (
          <div className="audit-doubts">
            <p className="small"><strong>{lang.ui.audit_doubts_heading}</strong></p>
            <ul className="small">
              {stats.audit_doubts.map((d, i) => <li key={i}>{d}</li>)}
            </ul>
          </div>
        )}
        <p className="small muted sans">{lang.ui.findings_are_technical}</p>
        {findings.map((f) => (
          <div className="paper-line" key={f.slug}>
            <span className="t">
              <Link href={`/findings/${f.slug}/`}>{f.title}</Link>
            </span>
          </div>
        ))}
      </section>

      {stats && (
        <>
          <DevKV title={lang.dev.corpus_heading} data={{
            library: library?.slug ?? "",
            papers: stats.papers,
            full_text: stats.full_text,
            abstract_only: stats.abstract_only,
            core: stats.core,
            peripheral: stats.peripheral,
            relationships: stats.relationships,
            manifest_hash: stats.manifest_hash ?? "null",
            note: stats.note,
          }} />
          <DevKV title="Per-scorer yields" data={stats.scorer_yields} />
        </>
      )}
    </>
  );
}
