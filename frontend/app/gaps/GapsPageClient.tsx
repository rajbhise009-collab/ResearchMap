"use client";
import { useLibraryData } from "../components/useLibraryData";
import type { GapDoc, LanguagePack } from "../../lib/types";
import GapsClient from "./GapsClient";

interface OpportunitiesFile {
  total: number;
  items: Array<{
    slug: string;
    rank?: number;
    gap_type?: string;
    consumer: GapDoc["consumer"];
  }>;
}

export default function GapsPageClient({ lang }: { lang: LanguagePack }) {
  const res = useLibraryData<OpportunitiesFile>("opportunities.json");

  const gaps: GapDoc[] = res.state === "ready"
    ? res.data.items.map((o) => ({
        slug: o.slug,
        consumer: o.consumer,
        dev: { rank: o.rank ?? 0, gap_type: o.gap_type ?? "" },
      }))
    : [];
  const libName = res.state === "ready" ? res.library.name : "this library";

  return (
    <>
      <div className="hero" style={{ marginBottom: "var(--s-7)" }}>
        <div className="eyebrow">The library · Everything we found</div>
        <h1 style={{ fontSize: "clamp(1.9rem, 3.6vw, 2.6rem)" }}>
          {lang.ui.all_opportunities}
        </h1>
        <p className="lede">
          {res.state === "loading" && "Loading the gap list…"}
          {res.state === "ready" && (
            <>Everything the tool found in the <em>{libName}</em> library, strongest first. Each one says how sure we are and what would undermine it.</>
          )}
          {res.state === "error" && "Couldn't load the gap list."}
        </p>
      </div>
      {res.state === "ready" && <GapsClient gaps={gaps} lang={lang} />}
    </>
  );
}
