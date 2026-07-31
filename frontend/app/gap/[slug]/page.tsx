import Link from "next/link";
import { getOpportunities, getOpportunity, getLanguage } from "../../../lib/data";
import { Strength, Caveats, Tag } from "../../components/plain";
import { DevKV, DevJSON } from "../../components/DevMode";

export function generateStaticParams() {
  return getOpportunities().map((o) => ({ slug: o.slug }));
}

const wid = (pid: string) => pid.split(":").pop() as string;

export default function GapDetail({ params }: { params: { slug: string } }) {
  const o = getOpportunity(params.slug);
  const lang = getLanguage();
  const c = o.consumer;

  // The papers behind this, and what each of them actually said.
  const said = o.evidence_trail.filter((e) => e.text && e.kind !== "paper");

  return (
    <>
      <Link href="/gaps/" className="crumb">← {lang.ui.all_opportunities}</Link>

      <div className="detail-head">
        <div className="result-kind">
          <span>{c.kind}</span>
          <span aria-hidden>·</span>
          <Strength label={c.strength} />
        </div>

        <h1 className={c.headline_is_quoted ? "quoted" : undefined}>
          {c.headline_is_quoted ? `“${c.headline}”` : c.headline}
        </h1>

        <p className="muted small sans">{c.kind_short}.</p>
      </div>

      <section className="block">
        <h2>Why this came up</h2>
        <p>{c.why}</p>
      </section>

      <section className="block">
        <h2>{lang.ui.strength_explainer}</h2>
        <Strength label={c.strength} meaning={c.strength_meaning} showMeaning />
      </section>

      {c.caveats.length > 0 && (
        <section className="block">
          <h2>{lang.ui.uncertain_heading}</h2>
          <Caveats items={c.caveats} />
        </section>
      )}

      <section className="block">
        <h2>{lang.ui.papers_behind}</h2>
        {o.supporting_papers.map((p) => (
          <div className="paper-line" key={p.paper_id}>
            <span className="t">
              <Link href={`/paper/${wid(p.paper_id)}/`}>{p.title ?? p.paper_id}</Link>
            </span>
            {p.abstract_only && (
              <Tag warn title={lang.abstract_only.text}>{lang.abstract_only.label}</Tag>
            )}
            {p.year && <span className="y">{p.year}</span>}
          </div>
        ))}
      </section>

      {said.length > 0 && (
        <section className="block">
          <h2>{lang.ui.what_they_said}</h2>
          <p className="small muted sans" style={{ marginTop: "-0.4rem" }}>
            {lang.ui.evidence_intro}
          </p>
          {said.map((e, i) => {
            const w = e.paper_id ? wid(e.paper_id) : null;
            return (
              <div className="evidence-item" key={`${e.id}-${i}`}>
                <div className="src">
                  <span>{KIND_WORD[e.kind] ?? "From a paper"}</span>
                  {w && <Link href={`/paper/${w}/`}>see the paper →</Link>}
                </div>
                <blockquote>{e.text}</blockquote>
              </div>
            );
          })}
        </section>
      )}

      <section className="block">
        <h2>What kind of gap this is</h2>
        <p>{c.kind_long}</p>
      </section>

      <DevKV title={lang.dev.raw_values} data={{
        id: o.id, scorer: o.scorer, gap_type: o.gap_type, rank: o.rank,
        score: o.score, confidence: o.confidence,
        confidence_tier: o.confidence_tier, trust: o.trust,
        confirm_status: o.confirm_status ?? "null",
        caveat_codes: o.caveats.map((x) => x.code),
        relationship_ids: o.relationship_ids,
        schema_version: o.schema_version,
      }} />
      <DevKV title={lang.dev.components_heading} data={o.component_scores} />
      <DevJSON title={lang.dev.json_heading} data={o} />
    </>
  );
}

// Internal record types, said in words. Kept minimal: these label a quote's
// provenance, so the reader knows whether they are reading a finding, a
// stated limitation, or a proposed next step.
const KIND_WORD: Record<string, string> = {
  future_work: "The authors said this should be studied next",
  limitation: "The authors said this didn't work",
  claim: "The authors reported",
  method: "The method",
  relationship: "A link between two papers",
};
