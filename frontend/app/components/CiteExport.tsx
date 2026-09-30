"use client";
// Cite / export controls for a gap or paper page. Client-side only —
// works on the static export without a backend.
//
// - "Copy BibTeX" / "Download .bib" for the paper(s) behind this page.
// - "Download .csv" for a gap's evidence (paper metadata + short
//   extracted claim/limitation/future-work text + verdict).
// - "How to cite this page" line — ResearchMap analysis-tool citation
//   with URL + access date, states output is unvalidated prototype.

import { useState } from "react";
import {
  PaperLike, papersToBibtex, paperToBibtex, citeKey, dedupeCiteKeys,
  toCsv, downloadText,
} from "../../lib/exports";

async function copy(text: string): Promise<boolean> {
  try {
    if (navigator.clipboard) {
      await navigator.clipboard.writeText(text);
      return true;
    }
  } catch {}
  return false;
}

interface EvidenceRow {
  paper_id: string;
  title: string | null;
  year: number | null;
  doi: string | null;
  short_text: string;
  verdict?: string;
}

export function BibtexButtons({ papers, filename }: {
  papers: PaperLike[]; filename: string;
}) {
  const [copied, setCopied] = useState(false);
  if (papers.length === 0) return null;
  const bib = papersToBibtex(papers);
  return (
    <div className="cite-actions">
      <button
        type="button"
        className="cite-btn"
        onClick={async () => {
          const ok = await copy(bib);
          if (ok) { setCopied(true); setTimeout(() => setCopied(false), 1400); }
        }}
      >
        {copied ? "Copied ✓" : "Copy BibTeX"}
      </button>
      <button
        type="button"
        className="cite-btn"
        onClick={() => downloadText(filename, "application/x-bibtex", bib)}
      >
        Download .bib
      </button>
    </div>
  );
}

export function CsvDownload({ headers, rows, filename }: {
  headers: string[]; rows: Array<Array<unknown>>; filename: string;
}) {
  if (rows.length === 0) return null;
  return (
    <button
      type="button"
      className="cite-btn"
      onClick={() => downloadText(filename, "text/csv", toCsv(headers, rows))}
    >
      Download .csv
    </button>
  );
}

/** "How to cite THIS page" — ResearchMap-as-analysis-tool + URL + date.
 *  Always states the output is unvalidated prototype. */
export function HowToCite({ pageName, note }: {
  pageName: string;
  note?: string;
}) {
  const url = typeof window !== "undefined" ? window.location.href : "";
  const today = new Date().toISOString().slice(0, 10);
  const cite =
    `ResearchMap. "${pageName}." Prototype literature-analysis tool. ` +
    `Retrieved ${today} from ${url}. ` +
    `Output is an unvalidated prototype and should not be cited as a ` +
    `primary research finding.`;
  return (
    <div className="how-to-cite">
      <details>
        <summary>How to cite this page</summary>
        <p className="small">{cite}</p>
        {note && <p className="small muted">{note}</p>}
        <button
          type="button"
          className="cite-btn"
          onClick={async () => { await copy(cite); }}
        >
          Copy citation
        </button>
      </details>
    </div>
  );
}

export function GapExport({
  gapSlug, contradictionExplanation, verdict, papers,
}: {
  gapSlug: string;
  contradictionExplanation?: string;
  verdict?: string;
  papers: Array<{
    paper_id?: string; title?: string | null;
    year?: number | null; doi?: string | null; venue?: string | null;
    authors?: string[] | null; short_text?: string;
  }>;
}) {
  const bibPapers = papers.map((p) => ({
    paper_id: p.paper_id, title: p.title, year: p.year,
    doi: p.doi, venue: p.venue, authors: p.authors ?? undefined,
  } as PaperLike));
  const csvHeaders = [
    "paper_id", "title", "year", "doi", "short_text", "verdict",
  ];
  const csvRows = papers.map((p) => [
    p.paper_id ?? "", p.title ?? "", p.year ?? "",
    p.doi ?? "", p.short_text ?? "", verdict ?? "",
  ]);
  return (
    <section className="block cite-block">
      <h2>Cite this gap</h2>
      <p className="block-lede">
        Export the papers behind this gap as BibTeX, or the evidence table
        as CSV. Files are generated in your browser — no server round-trip.
      </p>
      <div className="cite-row">
        <BibtexButtons papers={bibPapers} filename={`${gapSlug}.bib`} />
        <CsvDownload headers={csvHeaders} rows={csvRows}
                     filename={`${gapSlug}-evidence.csv`} />
      </div>
      <HowToCite
        pageName={contradictionExplanation
          ? `Flagged contradiction: ${contradictionExplanation.slice(0, 80)}`
          : `Gap ${gapSlug}`}
        note="Contradiction flags are automated shortlist output; the hand-audit verdict is the pipeline builder's own read, not expert review."
      />
    </section>
  );
}

export function PaperExport({ paper }: { paper: PaperLike }) {
  const key = citeKey(paper);
  const bib = paperToBibtex(paper, key);
  return (
    <section className="block cite-block">
      <h2>Cite this paper</h2>
      <p className="block-lede">
        Single-entry BibTeX below. Cite key <code>{key}</code>.
      </p>
      <pre className="bib-preview"><code>{bib}</code></pre>
      <BibtexButtons papers={[paper]} filename={`${key}.bib`} />
      <HowToCite pageName={paper.title || (paper.wid ?? "paper")} />
    </section>
  );
}
