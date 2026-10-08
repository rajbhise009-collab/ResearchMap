// Cross-surface consistency gate. Every count and title the site shows for a
// library must agree wherever it appears. Runs before `next build` (data)
// and after it (--built: sitemap, page titles, /method). Exit 1 on any
// mismatch, which fails `npm run build` and the test suite.
//
//   node scripts/consistency.mjs           # data checks
//   node scripts/consistency.mjs --built   # data + built-output checks
//
// Surfaces covered: site-facts.json (home card, toggle, /method, library
// page, /gaps header all render from it), opportunities.json (/gaps),
// per-card files (gap pages), search-index.json (search results), stats,
// papers.json, libraries.json + language.json (footer), findings docs
// (multi-domain.md generated tables), share images (og/manifest.json), and
// after the build: sitemap.xml, gap page <title>s, /method.
import fs from "fs";
import path from "path";

const FE = path.resolve(path.dirname(new URL(import.meta.url).pathname), "..");
const DATA = path.join(FE, "public", "data");
const OUT = path.join(FE, "out");
const built = process.argv.includes("--built");
const errors = [];
const fail = (m) => errors.push(m);
const read = (p) => JSON.parse(fs.readFileSync(p, "utf8"));
const VISIBLE = (it) => {
  const v = it.verdict ?? it.consumer?.verdict ?? null;
  return v === null || v === "genuine";
};
const KIND_TO_TYPE = {
  disagreement: "unresolved_contradictions", unaddressed_limitation: "persistent_limitations",
  method_transfer: "structural_holes", unfollowed_future_work: "orphaned_future_work",
};

const manifest = read(path.join(DATA, "libraries.json"));
const facts = Object.fromEntries(read(path.join(DATA, "site-facts.json")).libraries.map((l) => [l.slug, l]));
const lang = read(path.join(DATA, "language.json"));
const og = fs.existsSync(path.join(FE, "public", "og", "manifest.json"))
  ? read(path.join(FE, "public", "og", "manifest.json")) : null;
const findings = read(path.join(DATA, "findings.json")).items;
const md = (findings.find((f) => f.slug === "multi-domain") || {}).markdown || "";
const allGapSlugs = new Set();
const allPaperWids = new Set();

for (const lib of manifest.libraries) {
  const s = lib.slug;
  const dir = lib.snapshot_path === "/data" ? DATA : path.join(DATA, lib.snapshot_path.replace(/^\/data\//, ""));
  const f = facts[s];
  if (!f) { fail(`${s}: missing from site-facts.json`); continue; }
  const opps = read(path.join(dir, "opportunities.json"));
  const items = opps.items;
  const visible = items.filter(VISIBLE);
  const stats = read(path.join(dir, "stats.json"));
  const papers = read(path.join(dir, "papers.json"));
  const idx = read(path.join(dir, "search-index.json"));

  // results: facts total == visible cards == search-index result docs
  if (f.results_total !== visible.length) fail(`${s}: facts results ${f.results_total} != visible cards ${visible.length}`);
  const typed = f.results.reduce((a, r) => a + (r.count ?? 0), 0);
  if (typed !== f.results_total) fail(`${s}: facts per-type sum ${typed} != total ${f.results_total}`);
  for (const r of f.results) {
    if (r.count === null) continue;
    const n = visible.filter((it) => KIND_TO_TYPE[it.consumer.kind_id] === r.type).length;
    if (n !== r.count) fail(`${s}: ${r.type} facts ${r.count} != cards ${n}`);
  }
  if ((f.set_aside_total ?? 0) !== items.length - visible.length)
    fail(`${s}: facts set-aside ${f.set_aside_total} != cards ${items.length - visible.length}`);
  const idxOpp = idx.docs.filter((d) => d.type === "opportunity");
  if (idxOpp.length !== visible.length) fail(`${s}: search index has ${idxOpp.length} result docs, ${visible.length} visible`);
  const headBySlug = new Map(visible.map((it) => [it.slug, it.consumer.headline]));
  for (const d of idxOpp) {
    if (headBySlug.get(d.ref) !== d.title) fail(`${s}: search title for ${d.ref} differs from card headline`);
  }
  // titles unique among visible results; card files agree with the list
  const heads = visible.map((it) => it.consumer.headline);
  if (new Set(heads).size !== heads.length) fail(`${s}: duplicate result titles`);
  for (const it of items) {
    allGapSlugs.add(it.slug);
    const fp = path.join(dir, "opportunity", `${it.slug}.json`);
    if (!fs.existsSync(fp)) { fail(`${s}: no card file for ${it.slug}`); continue; }
    if (read(fp).consumer.headline !== it.consumer.headline) fail(`${s}: card file headline differs for ${it.slug}`);
  }
  // papers: facts == papers.json == stats == manifest == footer
  const nPapers = papers.total ?? papers.items.length;
  for (const [label, v] of [["papers.json", nPapers], ["stats", stats.papers], ["libraries.json", lib.n_papers]]) {
    if (v !== f.papers) fail(`${s}: ${label} papers ${v} != facts ${f.papers}`);
  }
  const foot = lang.libraries_note.items.find((x) => x.slug === s);
  if (!foot || foot.n_papers !== f.papers) fail(`${s}: footer papers ${foot?.n_papers} != facts ${f.papers}`);
  for (const p of papers.items) allPaperWids.add(p.wid);
  // share image says what the data says
  const o = og?.libraries?.[s];
  if (!o) fail(`${s}: share image not generated`);
  else for (const k of ["papers", "claims_read", "built"]) {
    if (o[k] !== f[k]) fail(`${s}: share image ${k} ${o[k]} != facts ${f[k]} (re-run tools/og/make_og_images.py)`);
  }
  // findings doc: the generated results table row
  const name = { "llm-calibration": "LLM calibration", "diet-and-mortality": "Diet & mortality",
                 "ml-fairness": "ML fairness" }[s];
  const lines = md.split("\n");
  const hdr = lines.findIndex((l) => l.startsWith("| library |") && l.includes("| total results |"));
  let row = null;
  for (let k = hdr + 2; hdr >= 0 && k < lines.length && lines[k].startsWith("|"); k++) {
    if (lines[k].startsWith(`| ${name} |`)) row = lines[k];
  }
  if (!row) fail(`${s}: no results row in multi-domain.md scorer table`);
  else {
    const total = Number(row.trim().split("|").filter(Boolean).pop().trim());
    if (total !== f.results_total) fail(`${s}: findings doc total ${total} != facts ${f.results_total}`);
  }
}

if (og) {
  const total = Object.values(facts).reduce((a, l) => a + l.papers, 0);
  if (og.total_papers !== total) fail(`default share image total papers ${og.total_papers} != ${total}`);
}

if (built) {
  if (!fs.existsSync(path.join(OUT, "sitemap.xml"))) fail("built: no sitemap.xml");
  else {
    const sm = fs.readFileSync(path.join(OUT, "sitemap.xml"), "utf8");
    const gaps = new Set([...sm.matchAll(/\/gap\/([^/<]+)\/<\/loc>/g)].map((m) => m[1]));
    const pap = new Set([...sm.matchAll(/\/paper\/([^/<]+)\/<\/loc>/g)].map((m) => m[1]));
    for (const g of allGapSlugs) if (!gaps.has(g)) fail(`built: sitemap missing gap ${g}`);
    for (const g of gaps) if (!allGapSlugs.has(g)) fail(`built: sitemap has unknown gap ${g}`);
    for (const w of allPaperWids) if (!pap.has(w)) fail(`built: sitemap missing paper ${w}`);
    if (pap.size !== allPaperWids.size) fail(`built: sitemap papers ${pap.size} != ${allPaperWids.size}`);
  }
  const unescape = (t) => t.replace(/&amp;/g, "&").replace(/&#x27;/g, "'").replace(/&quot;/g, '"')
    .replace(/&lt;/g, "<").replace(/&gt;/g, ">");
  for (const lib of manifest.libraries) {
    const dir = lib.snapshot_path === "/data" ? DATA : path.join(DATA, lib.snapshot_path.replace(/^\/data\//, ""));
    for (const it of read(path.join(dir, "opportunities.json")).items) {
      const p = path.join(OUT, "gap", it.slug, "index.html");
      if (!fs.existsSync(p)) { fail(`built: no page for ${it.slug}`); continue; }
      const title = unescape((fs.readFileSync(p, "utf8").match(/<title>([^<]*)<\/title>/) || [])[1] || "");
      const head = it.consumer.headline;
      const stem = head.slice(0, 40).replace(/…$/, "");
      if (!title.startsWith(stem)) fail(`built: page title for ${it.slug} does not start with its headline`);
    }
  }
  const method = fs.readFileSync(path.join(OUT, "method", "index.html"), "utf8");
  for (const f of Object.values(facts)) {
    if (!method.includes(`<td>${f.name}</td><td>${f.results_total}</td>`))
      fail(`built: /method results for ${f.slug} != ${f.results_total}`);
  }
}

if (errors.length) {
  console.error(`consistency: ${errors.length} mismatch(es)`);
  for (const e of errors) console.error("  - " + e);
  process.exit(1);
}
console.log(`consistency: OK (${manifest.libraries.length} libraries${built ? ", built output" : ""})`);
