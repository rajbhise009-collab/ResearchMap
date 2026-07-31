"use client";
import { useState } from "react";
import Link from "next/link";
import type { PaperDoc, LanguagePack } from "../../lib/types";
import { Tag } from "../components/plain";
import { DevKV } from "../components/DevMode";

export default function PapersClient({ papers, lang }: {
  papers: PaperDoc[];
  lang: LanguagePack;
}) {
  const [source, setSource] = useState("all");
  const shown = papers.filter(
    (p) => source === "all" ||
      (source === "full" ? !p.abstract_only : p.abstract_only)
  );
  return (
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
          <span className="t"><Link href={`/paper/${p.wid}/`}>{p.title}</Link></span>
          {p.abstract_only && (
            <Tag warn title={lang.abstract_only.text}>{lang.abstract_only.label}</Tag>
          )}
          {p.year && <span className="y">{p.year}</span>}
          <DevKV title="" data={p.dev} />
        </div>
      ))}
    </>
  );
}
