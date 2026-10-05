import type { Metadata } from "next";
import {
  allOpportunitySlugsAcrossLibraries, duplicateGapHeadlines, getLanguage, ownersOf,
  primaryOwner, readFromLibrary,
} from "../../../lib/data";
import { pageMeta, clip } from "../../../lib/meta";
import GapDetailClient from "./GapDetailClient";

export function generateStaticParams() {
  return allOpportunitySlugsAcrossLibraries().map((slug) => ({ slug }));
}

interface GapRecord {
  consumer: { headline: string; kind: string; paper_count?: number };
  supporting_papers?: unknown[];
  a_paper_id?: string;
  evidence_trail?: Array<{ kind: string; paper_id?: string | null; text?: string | null }>;
}

/** For a headline shared by several cards: the title of the paper whose
 *  reported problem this card is about (from the card's own evidence trail). */
function distinguisher(o: GapRecord, slug: string): string {
  const trail = o.evidence_trail || [];
  const lim = trail.find((e) => e.kind === "limitation" || e.kind === "future_work");
  const paper = lim && trail.find((e) => e.kind === "paper" && e.paper_id === lim.paper_id);
  return paper?.text ? clip(paper.text, 60) : slug;
}

// Built from data at build time: the owning library's own record.
export function generateMetadata({ params }: { params: { slug: string } }): Metadata {
  const lib = primaryOwner("opportunity", params.slug);
  if (!lib) return {};
  const o = readFromLibrary<GapRecord>(lib, `opportunity/${params.slug}.json`);
  const n = o.consumer.paper_count ?? o.supporting_papers?.length ?? (o.a_paper_id ? 2 : 0);
  const tail = lib.not_advice_note
    ? "Research-literature analysis, not dietary or medical advice."
    : "A starting point to check against the papers, not a verdict.";
  const head = duplicateGapHeadlines().has(o.consumer.headline)
    ? `${clip(o.consumer.headline, 70)} (problem in: ${distinguisher(o, params.slug)})`
    : clip(o.consumer.headline, 90);
  return pageMeta({
    title: head,
    // The advice/verdict tail is never clipped; only the body is.
    description: `${clip(`${o.consumer.kind} in the ${lib.name} library, drawn from ${n} paper${n === 1 ? "" : "s"}.`, 158 - tail.length - 1)} ${tail}`,
    path: `/gap/${params.slug}/`,
    librarySlug: lib.slug,
  });
}

export default function GapDetail({ params }: { params: { slug: string } }) {
  return <GapDetailClient slug={params.slug} lang={getLanguage()}
                          owners={ownersOf("opportunity", params.slug)} />;
}
