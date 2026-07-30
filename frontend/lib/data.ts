// Build-time data readers (server components / generateStaticParams).
// Reads the static snapshot in public/data — no network, no API server.
import fs from "fs";
import path from "path";
import type { Opportunity, PaperSummary, PaperDetail, Stats, Finding } from "./types";

const DATA = path.join(process.cwd(), "public", "data");
function read<T>(rel: string): T {
  return JSON.parse(fs.readFileSync(path.join(DATA, rel), "utf8")) as T;
}

export function getOpportunities(): Opportunity[] {
  return read<{ items: Opportunity[] }>("opportunities.json").items;
}
export function getOpportunity(slug: string): Opportunity {
  return read<Opportunity>(`opportunity/${slug}.json`);
}
export function getPapers(): PaperSummary[] {
  return read<{ items: PaperSummary[] }>("papers.json").items;
}
export function getPaper(wid: string): PaperDetail {
  return read<PaperDetail>(`paper/${wid}.json`);
}
export function getStats(): Stats {
  return read<Stats>("stats.json");
}
export function getFindings(): Finding[] {
  return read<{ items: Finding[] }>("findings.json").items;
}
export function getFinding(slug: string): Finding {
  const f = getFindings().find((x) => x.slug === slug);
  if (!f) throw new Error(`finding not found: ${slug}`);
  return f;
}
