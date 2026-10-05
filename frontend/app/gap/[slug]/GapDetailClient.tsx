"use client";
// Library-aware client wrapper for gap detail. Fetches
// opportunity/{slug}.json from the active library; if the slug isn't
// in that library's opportunities, renders NotInLibrary instead of
// silently rendering LLM-cal content.

import { useEffect } from "react";
import Link from "next/link";
import { Strength, Caveats, Tag } from "../../components/plain";
import { DevKV, DevJSON } from "../../components/DevMode";
import GapSidebar from "./GapSidebar";
import { useLibraryData, LibrarySwitchNotice } from "../../components/useLibraryData";
import NotFoundBody from "../../components/NotFoundBody";
import { site } from "../../../lib/site";
import { GapExport } from "../../components/CiteExport";
import ContradictionTimeline from "../../components/ContradictionTimeline";
import type { LanguagePack } from "../../../lib/types";

const wid = (pid: string) => (pid || "").split(":").pop() as string;

const KIND_WORD: Record<string, string> = {
  future_work: "The authors said this should be studied next",
  limitation: "The authors said this didn't work",
  claim: "The authors reported",
  method: "The method",
  relationship: "A link between two papers",
};

// The multi-domain contradiction cards have a different shape than the
// LLM-cal opportunity cards (no evidence_trail, no supporting_papers
// records — just a and b paper ids + claim texts). Adapting.
interface OpportunityLike {
  id?: string;
  slug: string;
  gap_type?: string;
  scorer?: string;
  rank?: number;
  score?: number;
  confidence?: number;
  confidence_tier?: string;
  trust?: number;
  confirm_status?: string | null;
  component_scores?: Record<string, number>;
  caveats?: Array<{ code: string; label?: string; text?: string }>;
  supporting_papers?: Array<{
    paper_id: string; title?: string; year?: number | null;
    abstract_only?: boolean;
  }>;
  evidence_trail?: Array<{
    kind: string; id: string; paper_id?: string | null; text?: string | null;
  }>;
  schema_version?: string;
  relationship_ids?: string[];
  consumer: {
    headline: string; headline_is_quoted?: boolean;
    kind: string; kind_id?: string; kind_short?: string; kind_long?: string;
    strength: string; strength_meaning?: string; why: string;
    caveats?: Array<{ code: string; label?: string; text?: string }>;
    paper_count?: number;
    verdict?: string;
    verdict_label?: string | null;
    verdict_reason?: string;
    verdict_basis?: string;
    verdict_topic?: string;
  };
  // Multi-domain contradiction card fields
  a_paper_id?: string;
  b_paper_id?: string;
  a_text?: string;
  b_text?: string;
  similarity?: number;
  explanation?: string;
  title?: string;
  cites_both?: {
    query_date: string;
    total: number;
    top: Array<{
      wid: string; openalex_id?: string; doi?: string | null;
      title?: string | null; year?: number | null;
      cited_by_count?: number; venue?: string | null;
    }>;
  } | null;
}

export default function GapDetailClient({ slug, lang, owners }: {
  slug: string;
  lang: LanguagePack;
  owners: string[];
}) {
  const res = useLibraryData<OpportunityLike>(`opportunity/${slug}.json`, owners);

  // Set a topic-specific document.title so the browser tab reads
  // "Red meat and stroke: ..." instead of the shared app title. The
  // page's <title> is set at build time to the app name; we overwrite
  // it per gap once the JSON arrives.
  const docTitle =
    res.state === "ready" ? res.data.consumer.headline : null;
  useEffect(() => {
    if (!docTitle) return;
    const prev = document.title;
    document.title = `${docTitle} — ${site.siteName}`;
    return () => { document.title = prev; };
  }, [docTitle]);

  if (res.state === "loading") {
    return <p className="muted">Loading the gap…</p>;
  }
  if (res.state === "missing") {
    return (
      <NotFoundBody what="gap" libraries={res.manifest.libraries} />
    );
  }
  if (res.state === "error") {
    return <p className="muted">Couldn&apos;t load this gap.</p>;
  }

  const o = res.data;
  const c = o.consumer;
  const librarySlug = res.library.slug;
  const librarySuffix = `?lib=${encodeURIComponent(librarySlug)}`;

  // Support both LLM-cal-shape (evidence_trail + supporting_papers) and
  // multi-domain contradiction-shape (a/b paper + text).
  const said = (o.evidence_trail || []).filter((e) => e.text && e.kind !== "paper");
  const supporters: Array<{ paper_id: string; title?: string;
                            year?: number | null; abstract_only?: boolean }> =
    o.supporting_papers && o.supporting_papers.length > 0
      ? o.supporting_papers
      : (o.a_paper_id && o.b_paper_id
          ? [
              { paper_id: o.a_paper_id, title: undefined },
              { paper_id: o.b_paper_id, title: undefined },
            ]
          : []);
  const contradictionPair = o.a_text && o.b_text;

  const sections: [string, string][] = [
    ["why", "Why this came up"],
    ["how-sure", lang.ui.strength_explainer],
    ...((c.caveats && c.caveats.length)
        ? [["uncertain", lang.ui.uncertain_heading] as [string, string]] : []),
    ["papers", lang.ui.papers_behind],
    ...(said.length ? [["said", lang.ui.what_they_said] as [string, string]] : []),
    ...(contradictionPair
        ? [["disagreement", "The two claims"] as [string, string]] : []),
    ["kind", "What kind of gap this is"],
  ];

  return (
    <div className="detail-grid">
      <div>
        <Link href={`/gaps/${librarySuffix}`} className="crumb">
          <span aria-hidden>←</span> {lang.ui.all_opportunities}
        </Link>

        {res.autoSwitched && <LibrarySwitchNotice library={res.library} />}
        {res.library.not_advice_note && (
          <p className="not-advice" role="note">
            <strong>Note:</strong> {res.library.not_advice_note}
          </p>
        )}
        <header className="detail-head">
          <div className="result-head">
            <span>{c.kind}</span>
            <span className="sep" aria-hidden>·</span>
            <Strength label={c.strength} />
            <span className="sep" aria-hidden>·</span>
            <span className="small muted">{res.library.short_name}</span>
          </div>
          <h1 className={c.headline_is_quoted ? "quoted" : undefined}>
            {c.headline_is_quoted ? `“${c.headline}”` : c.headline}
          </h1>
          {c.kind_short && <p className="subtitle">{c.kind_short}.</p>}
          {c.verdict_label && (
            <p className="verdict-chip small sans"
               data-verdict={c.verdict || "unaudited"}
               style={{ marginTop: "var(--s-3)" }}>
              {c.verdict_label}
            </p>
          )}
          {c.verdict && c.verdict !== "genuine" && (
            <div className="not-advice" role="note" style={{ marginTop: "var(--s-4)" }}>
              {c.verdict_reason && <span>{c.verdict_reason}</span>}
              {c.verdict_basis && (
                <><br /><span className="small muted">Basis: {c.verdict_basis}</span></>
              )}
            </div>
          )}
        </header>

        <section id="why" className="block">
          <h2>Why this came up</h2>
          <p>{c.why}</p>
        </section>

        <section id="how-sure" className="block">
          <h2>{lang.ui.strength_explainer}</h2>
          <Strength label={c.strength} meaning={c.strength_meaning} showMeaning />
        </section>

        {c.caveats && c.caveats.length > 0 && (
          <section id="uncertain" className="block">
            <h2>{lang.ui.uncertain_heading}</h2>
            <Caveats items={c.caveats.map((x) => ({
              code: x.code,
              label: x.label ?? x.code,
              text: x.text ?? "",
            }))} />
          </section>
        )}

        <section id="papers" className="block">
          <h2>{lang.ui.papers_behind}</h2>
          {supporters.map((p) => (
            <div className="paper-line" key={p.paper_id}>
              <span className="t">
                <Link href={`/paper/${wid(p.paper_id)}/${librarySuffix}`}>
                  {p.title ?? p.paper_id}
                </Link>
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
                    {w && <Link href={`/paper/${w}/${librarySuffix}`}>see the paper →</Link>}
                  </div>
                  <blockquote>{e.text}</blockquote>
                </div>
              );
            })}
          </section>
        )}

        {o.cites_both && contradictionPair && (
          <ContradictionTimeline
            a={{
              year: supporters[0]?.year ?? null,
              short: o.a_paper_id ? wid(o.a_paper_id) : "A",
            }}
            b={{
              year: supporters[1]?.year ?? null,
              short: o.b_paper_id ? wid(o.b_paper_id) : "B",
            }}
            citesBoth={o.cites_both.top.map((w) => ({
              year: w.year, title: w.title,
            }))}
            queryDate={o.cites_both.query_date}
          />
        )}

        {o.cites_both && (
          <section id="cites-both" className="block">
            <h2>Later papers that cite both sides</h2>
            <p className="block-lede">
              These are papers that cite BOTH of the two disagreeing
              papers above. That means they discuss the disagreement —
              not that they resolved or settled it.
              {o.cites_both.total > o.cites_both.top.length && (
                <> Top {o.cites_both.top.length} by citation count; {o.cites_both.total} in total (OpenAlex, queried {o.cites_both.query_date}).</>
              )}
              {o.cites_both.total <= o.cites_both.top.length && (
                <> {o.cites_both.total} in total (OpenAlex, queried {o.cites_both.query_date}).</>
              )}
            </p>
            {o.cites_both.top.length === 0 ? (
              <p className="muted">
                No later papers in OpenAlex cite both sides. This is
                what an unaddressed disagreement looks like — not a
                signal that either side is correct.
              </p>
            ) : (
              o.cites_both.top.map((w) => (
                <div className="paper-line" key={w.wid}>
                  <span className="t">
                    {w.doi ? (
                      <a href={`https://doi.org/${w.doi}`}
                          target="_blank" rel="noreferrer">
                        {w.title ?? w.wid}
                      </a>
                    ) : (w.title ?? w.wid)}
                  </span>
                  {w.year && <span className="y tnum">{w.year}</span>}
                  {w.venue && (
                    <span className="small muted"> {w.venue}</span>
                  )}
                </div>
              ))
            )}
          </section>
        )}

        {contradictionPair && (
          <section id="disagreement" className="block">
            <h2>The two claims</h2>
            <p className="block-lede">{o.explanation}</p>
            <div className="evidence-item">
              <div className="src">
                <span>Paper A</span>
                {o.a_paper_id && (
                  <Link href={`/paper/${wid(o.a_paper_id)}/${librarySuffix}`}>see the paper →</Link>
                )}
              </div>
              <blockquote>{o.a_text}</blockquote>
            </div>
            <div className="evidence-item">
              <div className="src">
                <span>Paper B</span>
                {o.b_paper_id && (
                  <Link href={`/paper/${wid(o.b_paper_id)}/${librarySuffix}`}>see the paper →</Link>
                )}
              </div>
              <blockquote>{o.b_text}</blockquote>
            </div>
          </section>
        )}

        <section id="kind" className="block">
          <h2>What kind of gap this is</h2>
          <p>{c.kind_long ?? ""}</p>
        </section>

        <GapExport
          gapSlug={slug}
          contradictionExplanation={c.headline}
          verdict={c.verdict}
          papers={supporters.map((sp) => ({
            paper_id: sp.paper_id,
            title: sp.title ?? null,
            year: sp.year ?? null,
            doi: (sp as any).doi ?? null,
            short_text:
              sp.paper_id === o.a_paper_id ? (o.a_text ?? "")
              : sp.paper_id === o.b_paper_id ? (o.b_text ?? "") : "",
          }))}
        />

        <DevKV title={lang.dev.raw_values} data={{
          id: o.id ?? "", scorer: o.scorer ?? "", gap_type: o.gap_type ?? "",
          rank: o.rank ?? 0, score: o.score ?? 0, confidence: o.confidence ?? 0,
          confidence_tier: o.confidence_tier ?? "",
          trust: o.trust ?? 0,
          confirm_status: o.confirm_status ?? "null",
          caveat_codes: (o.caveats ?? []).map((x) => x.code),
          relationship_ids: o.relationship_ids ?? [],
          schema_version: o.schema_version ?? "",
          library: res.library.slug,
          similarity: o.similarity ?? "",
        }} />
        {o.component_scores && (
          <DevKV title={lang.dev.components_heading} data={o.component_scores} />
        )}
        <DevJSON title={lang.dev.json_heading} data={o} />
      </div>

      <GapSidebar sections={sections} />
    </div>
  );
}
