// Launch gate: inspects the production build in out/ and site.config.json
// and prints a pass/fail checklist. It is a gate, not part of the build:
// `npm run build` still succeeds when these fail. Exit code 1 if any fail.
//
//   NEXT_PUBLIC_SITE_URL=https://example.org VERCEL_ENV=production npm run build
//   npm run launch-check
import fs from "fs";
import path from "path";

const root = path.dirname(new URL(import.meta.url).pathname);
const FE = path.resolve(root, "..");
const OUT = path.join(FE, "out");
// SITE_CONFIG overrides the config path (used by tests).
const cfg = JSON.parse(fs.readFileSync(process.env.SITE_CONFIG || path.join(FE, "site.config.json"), "utf8"));
const results = [];
const check = (ok, label, detail = "") => results.push({ ok, label, detail });

function walk(dir, pred, acc = []) {
  for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
    const p = path.join(dir, e.name);
    if (e.isDirectory()) walk(p, pred, acc);
    else if (pred(p)) acc.push(p);
  }
  return acc;
}

if (!fs.existsSync(OUT)) {
  console.log("FAIL  no build output: run `npm run build` first");
  process.exit(1);
}
const html = walk(OUT, (p) => p.endsWith(".html"));
const pages = html.filter((p) => !/(^|\/)404(\.html|\/index\.html)$/.test(path.relative(OUT, p)));
const read = (p) => fs.readFileSync(p, "utf8");
const attr = (h, re) => { const m = h.match(re); return m ? m[1] : null; };

// 1. Contact route
check(Boolean(cfg.contactEmail?.trim()) || cfg.repoIsPublic === true,
  "contact route configured (contactEmail or repoIsPublic)",
  `contactEmail=${cfg.contactEmail ? "set" : "empty"}, repoIsPublic=${cfg.repoIsPublic}`);

// 2. Site URL: a custom https domain, as baked into the build's canonical tags
const envUrl = process.env.NEXT_PUBLIC_SITE_URL || "";
const home = read(path.join(OUT, "index.html"));
const builtCanon = attr(home, /<link rel="canonical" href="([^"]+)"/) || "";
let builtHost = "";
try { builtHost = new URL(builtCanon).host; } catch {}
const customUrl = /^https:\/\//.test(builtCanon) && builtHost && !builtHost.endsWith("vercel.app");
check(customUrl,
  "build uses a custom https NEXT_PUBLIC_SITE_URL (not *.vercel.app)",
  `canonical host in build: ${builtHost || "none"}${envUrl ? `; env now: ${envUrl}` : "; env not set now"}`);

// 3. No unfinished text in visible page text
const bad = [];
for (const p of pages) {
  const text = read(p).replace(/<script[\s\S]*?<\/script>/g, " ").replace(/<style[\s\S]*?<\/style>/g, " ")
    .replace(/<[^>]+>/g, " ");
  const m = text.match(/\b(TODO|placeholder|lorem ipsum|lorem)\b/i);
  if (m) bad.push(`${path.relative(OUT, p)}: "${m[0]}"`);
}
check(bad.length === 0, 'no "TODO" / "placeholder" / "lorem" in page text', bad.slice(0, 5).join("; "));

// 4. No localhost / vercel.app in canonical or share tags when a custom URL is set
const leaks = [];
for (const p of pages) {
  const h = read(p);
  const tags = h.match(/<(?:link rel="canonical"|meta (?:property|name)="(?:og|twitter):[^"]+")[^>]*>/g) || [];
  for (const t of tags) {
    if (/localhost|127\.0\.0\.1/.test(t) || (customUrl && /vercel\.app/.test(t))) {
      leaks.push(`${path.relative(OUT, p)}: ${t.slice(0, 90)}`);
      break;
    }
  }
}
check(leaks.length === 0, "no localhost (or vercel.app, once a custom URL is set) in canonical/OG tags",
  leaks.slice(0, 3).join("; "));

// 5. Sitemap and robots
const robots = fs.existsSync(path.join(OUT, "robots.txt")) ? read(path.join(OUT, "robots.txt")) : null;
const sitemap = fs.existsSync(path.join(OUT, "sitemap.xml")) ? read(path.join(OUT, "sitemap.xml")) : null;
check(Boolean(sitemap && robots), "sitemap.xml and robots.txt present",
  sitemap ? `${(sitemap.match(/<url>/g) || []).length} URLs` : "missing");
check(Boolean(robots) && !/Disallow:\s*\/\s*$/m.test(robots) && !/noindex/.test(home),
  "built as production: crawlable robots.txt and no noindex",
  robots && /Disallow:\s*\/\s*$/m.test(robots) ? "robots.txt disallows everything (non-production build)" : "");

// 6. Analytics
const chunks = walk(path.join(OUT, "_next"), (p) => p.endsWith(".js"));
const analytics = chunks.some((p) => read(p).includes("/_vercel/insights"));
check(analytics, "analytics script present (Vercel Web Analytics)");

// 7. Unique titles
const seen = new Map();
for (const p of pages) {
  const t = attr(read(p), /<title>([^<]*)<\/title>/) || "";
  seen.set(t, [...(seen.get(t) || []), path.relative(OUT, p)]);
}
const dup = [...seen.entries()].filter(([, v]) => v.length > 1);
check(dup.length === 0, `every page title unique (${pages.length} pages)`,
  dup.slice(0, 3).map(([t, v]) => `"${t}" ×${v.length}`).join("; "));

let failed = 0;
for (const r of results) {
  if (!r.ok) failed++;
  console.log(`${r.ok ? "PASS" : "FAIL"}  ${r.label}${r.detail ? `  — ${r.detail}` : ""}`);
}
console.log(`\n${results.length - failed}/${results.length} passed`);
process.exit(failed ? 1 : 0);
