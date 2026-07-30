"use client";
import { useState } from "react";
import Link from "next/link";
import type { PaperSummary } from "../../lib/types";
import { AbstractBadge } from "../components/badges";

export default function PapersClient({ items }: { items: PaperSummary[] }) {
  const [cent, setCent] = useState("all");
  const [src, setSrc] = useState("all");
  const shown = items.filter(
    (p) =>
      (cent === "all" || p.domain_centrality === cent) &&
      (src === "all" ||
        (src === "fulltext" ? p.input_source === "fulltext" : p.abstract_only))
  );
  return (
    <>
      <div className="filters">
        <label className="small muted">centrality</label>
        <select value={cent} onChange={(e) => setCent(e.target.value)}>
          <option value="all">all</option>
          <option value="core">core</option>
          <option value="peripheral">peripheral</option>
        </select>
        <label className="small muted">source</label>
        <select value={src} onChange={(e) => setSrc(e.target.value)}>
          <option value="all">all</option>
          <option value="fulltext">full text</option>
          <option value="abstract">abstract-only</option>
        </select>
        <span className="spacer" />
        <span className="small muted">{shown.length} of {items.length}</span>
      </div>
      {shown.map((p) => (
        <div className="card" key={p.paper_id}>
          <div className="row">
            <Link href={`/papers/${p.wid}/`}>{p.title ?? p.paper_id}</Link>
            {p.abstract_only && <AbstractBadge />}
            <span className="pill">{p.domain_centrality}</span>
            <span className="spacer" />
            <span className="small muted">{p.year ?? "—"}</span>
          </div>
        </div>
      ))}
    </>
  );
}
