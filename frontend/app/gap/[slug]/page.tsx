import Link from "next/link";
import { getOpportunities, getOpportunity, getLanguage } from "../../../lib/data";
import { Strength, Caveats, Tag } from "../../components/plain";
import { DevKV, DevJSON } from "../../components/DevMode";
import GapSidebar from "./GapSidebar";

export function generateStaticParams() {
  return getOpportunities().map((o) => ({ slug: o.slug }));
}

const wid = (pid: string) => pid.split(":").pop() as string;

export default function GapDetail({ params }: { params: { slug: string } }) {
  const o = getOpportunity(params.slug);
  const lang = getLanguage();
  const c = o.consumer;

  // What the authors themselves said about the underlying claims — quoted,
  // never paraphrased. Titles alone go in the sidebar section list.
  const said = o.evidence_trail.filter((e) => e.text && e.kind !== "paper");

  const sections: [string, string][] = [
    ["why", "Why this came up"],
    ["how-sure", lang.ui.strength_explainer],
    ...(c.caveats.length ? [["uncertain", lang.ui.uncertain_heading] as [string, string]] : []),
    ["papers", lang.ui.papers_behind],
    ...(said.length ? [["said", lang.ui.what_they_said] as [string, string]] : []),
    ["kind", "What kind of gap this is"],
  ];

  return (
    <div className="detail-grid">
      <div>
        <Link href="/gaps/" className="crumb">
          <span aria-hidden>←</span> {lang.ui.all_opportunities}
        </Link>

        <header className="detail-head">
          <div className="result-head">
            <span>{c.kind}</span>
            <span className="sep" aria-hidden>·</span>
            <Strength label={c.strength} />
          </div>
          <h1 className={c.headline_is_quoted ? "quoted" : undefined}>
            {c.headline_is_quoted ? `“${c.headline}”` : c.headline}
          </h1>
          <p className="subtitle">{c.kind_short}.</p>
        </header>

        <section id="why" className="block">
          <h2>Why this came up</h2>
          <p>{c.why}</p>
        </section>

        <section id="how-sure" className="block">
          <h2>{lang.ui.strength_explainer}</h2>
          <Strength label={c.strength} meaning={c.strength_meaning} showMeaning />
        </section>

        {c.caveats.length > 0 && (
          <section id="uncertain" className="block">
            <h2>{lang.ui.uncertain_heading}</h2>
            <Caveats items={c.caveats} />
          </section>
        )}

        <section id="papers" className="block">
          <h2>{lang.ui.papers_behind}</h2>
          {o.supporting_papers.map((p) => (
            <div className="paper-line" key={p.paper_id}>
              <span className="t">
                <Link href={`/paper/${wid(p.paper_id)}/`}>{p.title ?? p.paper_id}</Link>
              </span>
              {p.abstract_only && (
                <Tag warn title={lang.abstract_only.text}>{lang.abstract_only.label}</Tag>
              )}
              {p.year && <span className="y tnum">{p.year}</span>}
            </div>
          ))}
        </section>

        {said.length > 0 && (
          <section id="said" className="block">
            <h2>{lang.ui.what_they_said}</h2>
            <p className="block-lede">{lang.ui.evidence_intro}</p>
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

        <section id="kind" className="block">
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
      </div>

      <GapSidebar sections={sections} />
    </div>
  );
}

// Internal record types, said in words. These label a quote's provenance
// so the reader knows whether they are reading a finding, a stated
// limitation, or a proposed next step.
const KIND_WORD: Record<string, string> = {
  future_work: "The authors said this should be studied next",
  limitation: "The authors said this didn't work",
  claim: "The authors reported",
  method: "The method",
  relationship: "A link between two papers",
};
