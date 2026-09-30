"use client";
import Link from "next/link";
import { useLibraryData } from "../components/useLibraryData";
import type { GapDoc, LanguagePack, Stats } from "../../lib/types";
import GapsClient from "./GapsClient";

interface OpportunitiesFile {
  total: number;
  audit?: {
    raw_flagged: number; genuine: number; artifact: number;
    duplicate: number; unaudited: number; confirmed: number;
  };
  items: Array<{
    slug: string;
    rank?: number;
    gap_type?: string;
    verdict?: string;
    consumer: GapDoc["consumer"];
  }>;
}

const VERDICT_HEADLINE: Record<string, string> = {
  artifact: "Flagged but set aside — different conditions",
  duplicate: "Flagged but set aside — duplicate of another pair",
  unaudited: "Flagged, no hand-audit recorded yet",
};

export default function GapsPageClient({ lang }: { lang: LanguagePack }) {
  const res = useLibraryData<OpportunitiesFile>("opportunities.json");
  const stats = useLibraryData<Stats>("stats.json");
  const items = res.state === "ready" ? res.data.items : [];
  // Split by verdict. If the library has no audit (e.g. LLM-cal),
  // everything is treated as ready-to-show (verdict undefined ⇒ genuine).
  const genuine = items.filter(
    (o) => !o.verdict || o.verdict === "genuine"
  );
  const setAside = items.filter(
    (o) => o.verdict === "artifact" || o.verdict === "duplicate"
  );
  const genuineGaps: GapDoc[] = genuine.map((o) => ({
    slug: o.slug, consumer: o.consumer,
    dev: { rank: o.rank ?? 0, gap_type: o.gap_type ?? "" },
  }));

  const libName = res.state === "ready" ? res.library.name : "this library";
  const librarySlug = res.state === "ready" ? res.library.slug : null;
  const suffix = librarySlug ? `?lib=${encodeURIComponent(librarySlug)}` : "";

  const coverageNote =
    stats.state === "ready" && stats.data.extraction_coverage_note
      ? stats.data.extraction_coverage_note
      : null;

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
        {coverageNote && (
          <p className="coverage-note small muted">{coverageNote}</p>
        )}
      </div>

      {res.state === "ready" && (
        <>
          <GapsClient gaps={genuineGaps} lang={lang} />

          {setAside.length > 0 && (
            <section className="block set-aside">
              <h2>Flagged but set aside ({setAside.length})</h2>
              <p className="block-lede">
                These were flagged by the classifier but excluded from the
                headline count by hand-audit. They stay visible so nothing
                is silently dropped.
              </p>
              {setAside.map((o) => (
                <div className="evidence-item" key={o.slug}>
                  <div className="src">
                    <span>{VERDICT_HEADLINE[o.verdict ?? "unaudited"]}</span>
                    <Link href={`/gap/${o.slug}/${suffix}`}>see the flagged pair →</Link>
                  </div>
                  <p style={{ margin: 0 }}>
                    <strong>Why set aside:</strong>{" "}
                    {o.consumer.verdict_reason || "See detail page."}
                  </p>
                </div>
              ))}
            </section>
          )}
        </>
      )}
    </>
  );
}
