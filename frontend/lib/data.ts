// Build-time data readers (server components / generateStaticParams).
// Reads the static snapshot in public/data — no network, no API server.
import fs from "fs";
import path from "path";
import type {
  Opportunity, PaperSummary, PaperDetail, Stats, Finding, LanguagePack,
  GapDoc, PaperDoc, LibrariesManifest, LibraryManifest, SiteFacts,
} from "./types";

const DATA = path.join(process.cwd(), "public", "data");
function read<T>(rel: string): T {
  return JSON.parse(fs.readFileSync(path.join(DATA, rel), "utf8")) as T;
}

/** The 3-library manifest — read at build time so the switcher, the
 *  hero and the language pack can all agree on what's available. */
export function getLibraries(): LibrariesManifest {
  return read<LibrariesManifest>("libraries.json");
}

/** Union of every paper id / opportunity slug across every library —
 *  used by generateStaticParams so each detail URL exists in the static
 *  export regardless of which library owns it. The client component at
 *  the route then fetches from the active library's snapshot; if the
 *  id doesn't exist there, it renders the NotInLibrary fallback. */
export function allPaperWidsAcrossLibraries(): string[] {
  const wids = new Set<string>();
  const manifest = getLibraries();
  for (const lib of manifest.libraries) {
    // snapshot_path is /data or /data/library/<slug>; on disk it's
    // public/data/... — strip the leading /data/ or use root.
    const relBase = lib.snapshot_path === "/data"
      ? "" : lib.snapshot_path.replace(/^\/data\//, "");
    try {
      const paperDir = path.join(DATA, relBase, "paper");
      for (const f of fs.readdirSync(paperDir)) {
        if (f.endsWith(".json")) wids.add(f.slice(0, -5));
      }
    } catch { /* library may not have paper/ yet */ }
  }
  return Array.from(wids).sort();
}

export function allOpportunitySlugsAcrossLibraries(): string[] {
  const slugs = new Set<string>();
  const manifest = getLibraries();
  for (const lib of manifest.libraries) {
    const relBase = lib.snapshot_path === "/data"
      ? "" : lib.snapshot_path.replace(/^\/data\//, "");
    try {
      const oppDir = path.join(DATA, relBase, "opportunity");
      for (const f of fs.readdirSync(oppDir)) {
        if (f.endsWith(".json")) slugs.add(f.slice(0, -5));
      }
    } catch { /* library may not have opportunity/ yet */ }
  }
  return Array.from(slugs).sort();
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

// The single translation layer, authored in Python and read here. The
// frontend must never hard-code consumer copy of its own.
export function getLanguage(): LanguagePack {
  return read<LanguagePack>("language.json");
}

// Trimmed payloads for client components: the plain-English face plus the
// raw values developer mode reveals, without the evidence trails.
export function getGapDocs(): GapDoc[] {
  return getOpportunities().map((o) => ({
    slug: o.slug,
    consumer: o.consumer,
    dev: {
      id: o.id,
      scorer: o.scorer,
      gap_type: o.gap_type,
      rank: o.rank,
      score: o.score,
      confidence: o.confidence,
      confidence_tier: o.confidence_tier,
      trust: o.trust,
      confirm_status: o.confirm_status ?? "null",
      caveat_codes: o.caveats.map((c) => c.code),
      supporting_paper_ids: o.supporting_papers.map((p) => p.paper_id),
      relationship_ids: o.relationship_ids,
      component_scores: o.component_scores,
    },
  }));
}

export function getPaperDocs(): PaperDoc[] {
  return getPapers().map((p) => ({
    wid: p.wid,
    title: p.title ?? p.wid,
    year: p.year,
    abstract_only: p.abstract_only,
    domain_centrality: p.domain_centrality,
    input_source: p.input_source,
    dev: {
      paper_id: p.paper_id,
      input_source: p.input_source,
      abstract_only: p.abstract_only,
      domain_centrality: p.domain_centrality,
      provenance: p.provenance ?? "null",
      doi: p.doi ?? "null",
      year: p.year ?? "null",
    },
  }));
}

// ---- Library ownership (build time) --------------------------------------

function relBase(snapshotPath: string): string {
  return snapshotPath === "/data" ? "" : snapshotPath.replace(/^\/data\//, "");
}

/** Libraries (manifest order) whose snapshot contains this id. A deep link
 *  uses this to open in the owning library (lib/activeLibrary.ts). */
export function ownersOf(kind: "paper" | "opportunity", id: string): string[] {
  const out: string[] = [];
  for (const lib of getLibraries().libraries) {
    if (fs.existsSync(path.join(DATA, relBase(lib.snapshot_path), kind, `${id}.json`))) {
      out.push(lib.slug);
    }
  }
  return out;
}

/** The owning library (default among owners, else first) — what a link
 *  without ?lib opens, and therefore what the page's metadata describes. */
export function primaryOwner(kind: "paper" | "opportunity", id: string): LibraryManifest | null {
  const m = getLibraries();
  const owners = ownersOf(kind, id);
  const slug = owners.includes(m.default_slug) ? m.default_slug : owners[0];
  return m.libraries.find((l) => l.slug === slug) ?? null;
}

export function readFromLibrary<T>(lib: LibraryManifest, rel: string): T {
  return read<T>(path.join(relBase(lib.snapshot_path), rel));
}

/** The pre-registered validation result (backend/app/validation/report_v1.py). */
export interface ValidationSummary {
  verdict: string; plain: string; protocol_commit: string; n: number; addressed: number;
  n_required: number; power: number; engine_auc: number; engine_auc_ci: [number, number];
  citation_auc: number; citation_auc_ci: [number, number]; recency_auc: number; random_auc: number;
}
export function getValidation(): ValidationSummary | null {
  try { return read<ValidationSummary>("validation.json"); } catch { return null; }
}

/** Facts for the trust pages and library headers (backend/app/api/site_facts.py). */
export function getSiteFacts(): SiteFacts {
  return read<SiteFacts>("site-facts.json");
}

/** Gap headlines that appear on more than one card (across all libraries).
 *  Their page titles get a distinguishing suffix so every title is unique. */
let _dupHeadlines: Set<string> | null = null;
export function duplicateGapHeadlines(): Set<string> {
  if (_dupHeadlines) return _dupHeadlines;
  const count = new Map<string, number>();
  for (const lib of getLibraries().libraries) {
    const items = readFromLibrary<{ items: Array<{ consumer: { headline: string } }> }>(
      lib, "opportunities.json").items;
    for (const it of items) count.set(it.consumer.headline, (count.get(it.consumer.headline) || 0) + 1);
  }
  _dupHeadlines = new Set([...count.entries()].filter(([, n]) => n > 1).map(([h]) => h));
  return _dupHeadlines;
}
