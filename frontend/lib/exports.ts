// Client-side exports: BibTeX + CSV.
//
// - BibTeX cite keys are stable, collision-safe (paper id fallback for
//   any name/year collision), and never emit "undefined"/"null".
// - Values with LaTeX-sensitive characters (%, &, #, $, {, }, ~, ^, \, _)
//   are escaped. Non-ASCII characters pass through verbatim (BibTeX +
//   biber handles UTF-8 natively).
// - CSV escaping wraps every cell in double-quotes and doubles internal
//   double-quotes, per RFC 4180.
import { bareDoi } from "./doi";

export interface PaperLike {
  paper_id?: string;
  wid?: string;
  title?: string | null;
  year?: number | null;
  doi?: string | null;
  venue?: string | null;
  authors?: string[] | null;
  first_author_family?: string | null;
}

// ---- BibTeX ------------------------------------------------------------

// Placeholder strings that can't collide with any other escape output —
// we substitute backslash/tilde/caret first, do the other escapes, then
// substitute the placeholders for their final \textbackslash{} etc. forms.
// Otherwise the { and } that appear inside \textbackslash{} would get
// re-escaped to \{ \}, corrupting the output.
const BS = "";
const TIL = "";
const CAR = "";

export function escapeLatex(s: string): string {
  return s
    .replace(/\\/g, BS)
    .replace(/~/g, TIL)
    .replace(/\^/g, CAR)
    .replace(/&/g, "\\&")
    .replace(/%/g, "\\%")
    .replace(/\$/g, "\\$")
    .replace(/#/g, "\\#")
    .replace(/_/g, "\\_")
    .replace(/{/g, "\\{")
    .replace(/}/g, "\\}")
    .replace(new RegExp(BS, "g"), "\\textbackslash{}")
    .replace(new RegExp(TIL, "g"), "\\textasciitilde{}")
    .replace(new RegExp(CAR, "g"), "\\textasciicircum{}");
}

/** Fold common Latin accents so citekeys stay readable for names like
 *  Müller / Éloïse. Not exhaustive — good enough for author families. */
function asciiFold(s: string): string {
  if (typeof (s as any).normalize === "function") {
    // NFKD → strip combining marks
    return s.normalize("NFKD").replace(/[̀-ͯ]/g, "")
            .replace(/ß/g, "ss").replace(/æ/g, "ae").replace(/œ/g, "oe")
            .replace(/Æ/g, "AE").replace(/Œ/g, "OE")
            .replace(/ø/g, "o").replace(/Ø/g, "O")
            .replace(/đ/g, "d").replace(/Đ/g, "D")
            .replace(/ł/g, "l").replace(/Ł/g, "L");
  }
  return s;
}

/** Stable cite key. First-author-family + year, else "researchmap<wid>".
 *  On collision (same family+year for two papers in the same export),
 *  the caller can suffix by wid; `citeKey` here returns the base and
 *  the collision resolver is `dedupeCiteKeys` below. Never returns a
 *  string containing "undefined"/"null"/"NaN". Handles accents so
 *  "Müller" → "mueller" not "mller". */
export function citeKey(p: PaperLike): string {
  const rawFam = p.first_author_family
    || (p.authors && p.authors[0] && p.authors[0].split(/\s+/).pop())
    || "";
  // Order matters: German conventions ü→ue, ö→oe, ä→ae BEFORE the
  // NFKD-strip fold (which would drop the umlaut and give "muller").
  const german = rawFam
    .replace(/ü/g, "ue").replace(/Ü/g, "Ue")
    .replace(/ö/g, "oe").replace(/Ö/g, "Oe")
    .replace(/ä/g, "ae").replace(/Ä/g, "Ae");
  const fam = asciiFold(german).replace(/[^A-Za-z]/g, "");
  const year = Number.isFinite(p.year as number) ? String(p.year) : "";
  const wid = (p.wid || (p.paper_id || "").split(":").pop() || "").replace(/[^A-Za-z0-9]/g, "");
  if (fam && year) return `${fam.toLowerCase()}${year}`;
  if (year && wid) return `researchmap${wid}${year}`;
  return `researchmap${wid || "paper"}`;
}

/** Deduplicate cite keys within an export by appending a-z on collisions.
 *  Preserves input order. */
export function dedupeCiteKeys(papers: PaperLike[]): string[] {
  const counts = new Map<string, number>();
  const out: string[] = [];
  for (const p of papers) {
    const base = citeKey(p);
    const n = counts.get(base) ?? 0;
    counts.set(base, n + 1);
    out.push(n === 0 ? base : `${base}${String.fromCharCode(96 + n)}`);
  }
  return out;
}

function bibField(name: string, value: string | null | undefined): string | null {
  if (value == null || value === "" || value === "undefined" || value === "null") return null;
  return `  ${name} = {${escapeLatex(String(value))}}`;
}

export function paperToBibtex(p: PaperLike, key: string): string {
  const authors = (p.authors || []).filter(
    (a) => a && a !== "undefined" && a !== "null"
  );
  const authorField = authors.length
    ? bibField("author", authors.join(" and "))
    : null;
  const fields = [
    bibField("title", p.title || null),
    authorField,
    bibField("year", Number.isFinite(p.year as number) ? String(p.year) : null),
    bibField("journal", p.venue || null),
    bibField("doi", bareDoi(p.doi)),
  ].filter((x): x is string => x !== null);
  const type = p.venue ? "article" : "misc";
  return `@${type}{${key},\n${fields.join(",\n")}\n}`;
}

export function papersToBibtex(papers: PaperLike[]): string {
  const keys = dedupeCiteKeys(papers);
  return papers.map((p, i) => paperToBibtex(p, keys[i])).join("\n\n");
}

// ---- CSV --------------------------------------------------------------

export function csvCell(v: unknown): string {
  if (v == null || v === "undefined" || v === "null") return '""';
  const s = String(v).replace(/"/g, '""');
  return `"${s}"`;
}

export function toCsv(headers: string[], rows: Array<Array<unknown>>): string {
  const lines = [headers.map(csvCell).join(",")];
  for (const r of rows) lines.push(r.map(csvCell).join(","));
  return lines.join("\r\n") + "\r\n";
}

// ---- Trigger a browser download ----------------------------------------

export function downloadText(filename: string, mime: string, text: string) {
  if (typeof window === "undefined") return;
  const blob = new Blob([text], { type: `${mime};charset=utf-8` });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}
