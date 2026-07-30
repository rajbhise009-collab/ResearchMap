import Link from "next/link";
import { getStats } from "../lib/data";

function Stat({ n, l }: { n: string | number; l: string }) {
  return (
    <div className="stat">
      <div className="n">{n}</div>
      <div className="l">{l}</div>
    </div>
  );
}

export default function Overview() {
  const s = getStats();
  const y = s.scorer_yields;
  const abstractPct = Math.round((s.abstract_only / s.papers) * 100);

  const notes: { name: string; found: string }[] = [
    {
      name: "Persistent limitations",
      found: `${y.persistent_limitations} cluster survives the 3-paper floor + same-construct gate — a generic category (e.g. task-scope). Low actionability.`,
    },
    {
      name: "Unresolved contradictions",
      found:
        `${y.unresolved_contradictions}. Candidate pairs scale ~N^1.89 while confirmed stays at 0 — bounding the rate under 0.4%. For a young, coherent field this is the CORRECT answer, not a scorer failure.`,
    },
    {
      name: "Orphaned future-work",
      found: `${y.orphaned_future_work}, but each is a WEAK, corpus-relative signal — "unaddressed" means within this ${s.papers}-paper corpus, not the field.`,
    },
    {
      name: "Structural holes",
      found: `${y.structural_holes} semantic leads; ${y.structural_holes_substantive} survive LLM confirmation as substantive method-transfer directions. The rest are trivial or topical adjacency.`,
    },
  ];

  return (
    <>
      <h1>Corpus overview</h1>
      <p className="lede">
        Deterministic literature-based discovery over {s.papers} clean papers in the LLM
        calibration / uncertainty / hallucination sub-domain. LLMs extract; code reasons.
        Every number below traces to a source paper.
      </p>

      <h2>Composition</h2>
      <div className="grid2">
        <Stat n={s.papers} l="papers (deduped, relabelled)" />
        <Stat n={`${s.full_text} / ${s.abstract_only}`} l={`full-text / abstract-only (${100 - abstractPct}% full text)`} />
        <Stat n={`${s.core} / ${s.peripheral}`} l="core / peripheral" />
        <Stat n={s.relationships} l="claim relationships" />
      </div>
      <p className="small muted" style={{ marginTop: 8 }}>
        Abstract-only papers ({abstractPct}% of the corpus) yield ~11× fewer own-work
        limitations than full text — they are flagged wherever they appear.
      </p>

      <h2>What each scorer found — and didn&rsquo;t</h2>
      {notes.map((n) => (
        <div className="card" key={n.name}>
          <div className="row">
            <strong>{n.name}</strong>
          </div>
          <div className="small" style={{ marginTop: 4 }}>{n.found}</div>
        </div>
      ))}

      <div className="empty" style={{ marginTop: 8 }}>
        <strong>0 contradictions found.</strong> Candidates scale ~N^1.89 while confirmed
        stays at 0 — see the{" "}
        <Link href="/findings/corpus-scaling-study/">corpus-scaling study</Link> and{" "}
        <Link href="/findings/RESEARCHMAP-FINDINGS/">the findings report</Link> for the
        domain-coherence precondition. This is a property of the field, not a bug.
      </div>

      <h2>Accounting</h2>
      <div className="grid2">
        <Stat n={`$${s.spend_to_date_usd.toFixed(1)}`} l="total paid spend to date (thinking-token corrected)" />
        <Stat n={s.manifest_hash?.slice(0, 10) ?? "—"} l="corpus manifest hash" />
      </div>

      <p className="small muted" style={{ marginTop: 18 }}>
        Explore <Link href="/opportunities/">opportunities</Link> (ranked by trust = score ×
        confidence), the <Link href="/papers/">corpus papers</Link>, or the{" "}
        <Link href="/findings/">methodological findings</Link>.
      </p>
    </>
  );
}
