import type { Metadata } from "next";
import {
  allPaperWidsAcrossLibraries, getLanguage, ownersOf, primaryOwner, readFromLibrary,
} from "../../../lib/data";
import { pageMeta, clip } from "../../../lib/meta";
import PaperDetailClient from "./PaperDetailClient";

export function generateStaticParams() {
  return allPaperWidsAcrossLibraries().map((wid) => ({ wid }));
}

interface PaperRecord {
  title?: string | null; year?: number | string | null; venue?: string | null;
  abstract_only?: boolean;
}

// Built from data at build time: the owning library's own record.
export function generateMetadata({ params }: { params: { wid: string } }): Metadata {
  const lib = primaryOwner("paper", params.wid);
  if (!lib) return {};
  const p = readFromLibrary<PaperRecord>(lib, `paper/${params.wid}.json`);
  const title = p.title || params.wid;
  const where = [p.year, p.venue].filter(Boolean).join(", ");
  const tail = lib.not_advice_note
    ? " Research-literature analysis, not dietary or medical advice." : "";
  return pageMeta({
    title: clip(title, 90),
    // The not-advice tail is never clipped; only the body is.
    description: clip(
      `${title}${where ? ` (${where})` : ""}. What the paper claims, the limits it states and ` +
      `what it suggests next, read from the ${p.abstract_only ? "abstract" : "full text"}, ` +
      `in the ${lib.name} library.`, 158 - tail.length) + tail,
    path: `/paper/${params.wid}/`,
    librarySlug: lib.slug,
  });
}

export default function PaperDetail({ params }: { params: { wid: string } }) {
  return <PaperDetailClient wid={params.wid} lang={getLanguage()}
                            owners={ownersOf("paper", params.wid)} />;
}
