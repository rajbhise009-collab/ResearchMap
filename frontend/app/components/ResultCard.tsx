"use client";
// One result, in the reader's language. Progressive disclosure: the
// headline says what it is, one paragraph says why it surfaced, the
// caveats are always visible, and the evidence is one click away.

import Link from "next/link";
import type { GapDoc, PaperDoc } from "../../lib/types";
import { Strength, Caveats, Tag } from "./plain";
import { DevKV } from "./DevMode";

export function GapResult({ gap, readMore }: { gap: GapDoc; readMore: string }) {
  const c = gap.consumer;
  const weak = c.strength === "Unverified lead";
  const href = `/gap/${gap.slug}/`;
  return (
    <article className={weak ? "result is-weak" : "result"}>
      <div className="result-head">
        <span>{c.kind}</span>
        <span className="sep" aria-hidden>·</span>
        <Strength label={c.strength} />
      </div>

      <h3>
        <Link href={href} className={c.headline_is_quoted ? "quoted" : undefined}>
          {c.headline_is_quoted ? `“${c.headline}”` : c.headline}
        </Link>
      </h3>

      <p className="why">{c.why}</p>

      <Caveats items={c.caveats} />

      <div className="result-foot">
        <Link href={href} className="read-more">
          {readMore} <span aria-hidden>→</span>
        </Link>
        <span>
          {c.paper_count} {c.paper_count === 1 ? "paper" : "papers"} behind this
        </span>
      </div>

      <DevKV title="Raw values" data={gap.dev} />
    </article>
  );
}

export function PaperResult({ paper, fidelityLabel, fidelityNote }: {
  paper: PaperDoc;
  fidelityLabel: string;
  fidelityNote: string;
}) {
  return (
    <article className="result">
      <div className="result-head">
        <span>Paper</span>
        {paper.year && (<><span className="sep" aria-hidden>·</span><span>{paper.year}</span></>)}
        {paper.abstract_only && (
          <Tag warn title={fidelityNote}>{fidelityLabel}</Tag>
        )}
      </div>
      <h3><Link href={`/paper/${paper.wid}/`}>{paper.title}</Link></h3>
      <DevKV title="Raw values" data={paper.dev} />
    </article>
  );
}
