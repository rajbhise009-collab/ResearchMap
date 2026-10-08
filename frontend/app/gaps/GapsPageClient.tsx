"use client";
import Link from "next/link";
import { useLibraryData } from "../components/useLibraryData";
import type { GapDoc, LanguagePack, SiteFactsLibrary } from "../../lib/types";
import LibrarySummary from "../components/LibrarySummary";
import GapsClient from "./GapsClient";
import { DevKV } from "../components/DevMode";

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

export default function GapsPageClient({ lang, facts }: {
  lang: LanguagePack; facts: SiteFactsLibrary[];
}) {
  const res = useLibraryData<OpportunitiesFile>("opportunities.json");
  const items = res.state === "ready" ? res.data.items : [];
  // Split by verdict. If the library has no audit (e.g. LLM-cal),
  // everything is treated as ready-to-show (verdict undefined ⇒ genuine).
  const genuine = items.filter(
    (o) => !o.verdict || o.verdict === "genuine"
  );
  const setAside = items.filter(
    (o) => o.verdict === "artifact" || o.verdict === "duplicate" || o.verdict === "set_aside"
  );
  // Flagged by the classifier but not hand-checked yet: shown, never
  // counted in the headline, never mixed in with checked disagreements.
  const unchecked = items.filter((o) => o.verdict === "unaudited");
  const genuineGaps: GapDoc[] = genuine.map((o) => ({
    slug: o.slug, consumer: o.consumer,
    dev: { rank: o.rank ?? 0, gap_type: o.gap_type ?? "" },
  }));

  const libName = res.state === "ready" ? res.library.name : "this library";
  const librarySlug = res.state === "ready" ? res.library.slug : null;
  const suffix = librarySlug ? `?lib=${encodeURIComponent(librarySlug)}` : "";

  const fact = librarySlug ? facts.find((f) => f.slug === librarySlug) : undefined;

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
        {fact && <LibrarySummary fact={fact} />}
        {res.state === "ready" && res.data.audit && (
          <DevKV title="Raw counts (classifier flags vs hand audit)"
                 data={res.data.audit} />
        )}
      </div>

      {res.state === "ready" && (
        <>
          <GapsClient gaps={genuineGaps} lang={lang} />

          {unchecked.length > 0 && (
            <section className="block set-aside">
              <h2>Flagged by the system, not yet checked ({unchecked.length})</h2>
              <p className="block-lede">
                The classifier flagged these as possible disagreements, but
                nobody has checked them against the source papers yet. They
                are not counted in the headline.
              </p>
              {unchecked.map((o) => (
                <div className="evidence-item" key={o.slug}>
                  <div className="src">
                    <strong>{o.consumer.headline}</strong>
                    <Link href={`/gap/${o.slug}/${suffix}`}>see the flagged pair →</Link>
                  </div>
                  <p className="verdict-chip small sans" data-verdict="unaudited"
                     style={{ margin: "var(--s-2) 0 0" }}>
                    Flagged by the system, not yet checked
                  </p>
                </div>
              ))}
            </section>
          )}

          {setAside.length > 0 && (
            <section className="block set-aside">
              <h2>Set aside after checking ({setAside.length})</h2>
              <p className="block-lede">
                These came up but were set aside after a check: disagreements by
                hand against the papers, method-transfer leads by a language-model
                check. They are not counted as results, and they stay visible so
                nothing is silently dropped.
              </p>
              {setAside.map((o) => (
                <div className="evidence-item" key={o.slug}>
                  <div className="src">
                    <strong>{o.consumer.headline}</strong>
                    <Link href={`/gap/${o.slug}/${suffix}`}>see the flagged pair →</Link>
                  </div>
                  {o.consumer.verdict_label && (
                    <p className="verdict-chip small sans"
                       data-verdict={o.verdict || "unaudited"}
                       style={{ margin: "var(--s-2) 0 0" }}>
                      {o.consumer.verdict_label}
                    </p>
                  )}
                  <p style={{ margin: "var(--s-2) 0 0" }}>
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
