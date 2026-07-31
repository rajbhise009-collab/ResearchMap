import Link from "next/link";
import {
  getStats, getLanguage, getGapDocs, getPapers, getFindings,
} from "../../lib/data";
import { DevKV } from "../components/DevMode";

export default function LibraryPage() {
  const stats = getStats();
  const lang = getLanguage();
  const gaps = getGapDocs();
  const papers = getPapers();
  const findings = getFindings();

  // Counted from the gaps themselves rather than from internal yield
  // figures, so what this page claims and what the list shows can't diverge.
  const byKind = new Map<string, number>();
  for (const g of gaps) {
    byKind.set(g.consumer.kind_id, (byKind.get(g.consumer.kind_id) || 0) + 1);
  }

  const kinds = Object.values(lang.kinds);

  return (
    <>
      <div className="hero" style={{ marginBottom: "2.5rem" }}>
        <h1 style={{ fontSize: "2rem" }}>The library</h1>
        <p className="lede">
          What is in here, what we could read of it, and what the tool found
          when it looked.
        </p>
      </div>

      <section className="block">
        <h2>What it holds</h2>
        <p>
          {stats.papers} papers on {lang.ui.library_covers}.
        </p>
        <p>
          We could read {stats.full_text} of them in full. For the other{" "}
          {stats.abstract_only} we only had the summary — and that matters
          more than it sounds: {lang.abstract_only.text.toLowerCase()}
        </p>
        <p className="small">
          <Link href="/papers/">Browse all {stats.papers} papers →</Link>
        </p>
      </section>

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
                <strong style={{ color: "var(--ink)" }}>
                  {n} {n === 1 ? "result" : "results"}
                </strong>
                <span>{k.name}</span>
              </div>
              <p style={{ margin: 0 }}>{k.long}</p>
              {n > 0 && (
                <p className="small" style={{ marginTop: "0.5rem" }}>
                  <Link href="/gaps/">See them →</Link>
                </p>
              )}
            </div>
          );
        })}
      </section>

      <section className="block">
        <h2>{lang.ui.findings_heading}</h2>
        <p>{lang.ui.findings_intro}</p>
        <p className="small muted sans">{lang.ui.findings_are_technical}</p>
        {findings.map((f) => (
          <div className="paper-line" key={f.slug}>
            <span className="t">
              <Link href={`/findings/${f.slug}/`}>{f.title}</Link>
            </span>
          </div>
        ))}
      </section>

      <DevKV title={lang.dev.corpus_heading} data={{
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
      <DevKV title={lang.dev.spend_heading} data={{
        spend_to_date_usd: stats.spend_to_date_usd,
        note: "extraction + confirmation LLM calls to date; this UI adds none",
      }} />
      <DevKV title="Papers by centrality" data={{
        core: papers.filter((p) => p.domain_centrality === "core").length,
        peripheral: papers.filter((p) => p.domain_centrality === "peripheral").length,
      }} />
    </>
  );
}
