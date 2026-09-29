"use client";
import Link from "next/link";
import type { LanguagePack, PaperSummary } from "../../lib/types";
import { Tag } from "../components/plain";
import { DevKV } from "../components/DevMode";
import { useLibraryData } from "../components/useLibraryData";
import { useState } from "react";

export default function PapersPageClient({ lang }: { lang: LanguagePack }) {
  const res = useLibraryData<{ total: number; items: PaperSummary[] }>(
    "papers.json"
  );
  const [source, setSource] = useState("all");

  const papers = res.state === "ready" ? res.data.items : [];
  const shown = papers.filter(
    (p) => source === "all" ||
      (source === "full" ? !p.abstract_only : p.abstract_only)
  );
  const abstractOnly = papers.filter((p) => p.abstract_only).length;
  const libName = res.state === "ready" ? res.library.name : "this library";
  const librarySlug = res.state === "ready" ? res.library.slug : null;
  const suffix = librarySlug ? `?lib=${encodeURIComponent(librarySlug)}` : "";

  return (
    <>
      <div className="hero" style={{ marginBottom: "var(--s-7)" }}>
        <div className="eyebrow">The library · Every paper</div>
        <h1 style={{ fontSize: "clamp(1.9rem, 3.6vw, 2.6rem)" }}>
          {lang.ui.all_papers}
        </h1>
        <p className="lede">
          {res.state === "loading" && "Loading the paper list…"}
          {res.state === "ready" && (
            <>The {papers.length} papers in the <em>{libName}</em> library. For {abstractOnly} of them we only had the summary — those are marked, because we know less about them than the rest.</>
          )}
          {res.state === "error" && "Couldn't load the paper list."}
        </p>
      </div>

      {res.state === "ready" && (
        <>
          <div className="filters">
            <label>
              what we had
              <select value={source} onChange={(e) => setSource(e.target.value)}>
                <option value="all">everything</option>
                <option value="full">{lang.full_text.label}</option>
                <option value="abstract">{lang.abstract_only.label}</option>
              </select>
            </label>
            <span className="count">{shown.length} of {papers.length}</span>
          </div>

          {shown.map((p) => (
            <div className="paper-line" key={p.wid}>
              <span className="t">
                <Link href={`/paper/${p.wid}/${suffix}`}>{p.title}</Link>
              </span>
              {p.abstract_only && (
                <Tag warn title={lang.abstract_only.text}>{lang.abstract_only.label}</Tag>
              )}
              {p.year && <span className="y">{p.year}</span>}
              <DevKV title="" data={p as any} />
            </div>
          ))}
        </>
      )}
    </>
  );
}
