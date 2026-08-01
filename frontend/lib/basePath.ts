// Runtime helper for /public/ asset URLs.
//
// Next auto-prefixes routes and imported static assets with basePath, but
// files fetched from /public/ at runtime are on the caller. This helper is
// how the whole client codebase agrees on the prefix — one function, one
// source of truth (next.config.mjs → NEXT_PUBLIC_BASE_PATH).

const BASE = (process.env.NEXT_PUBLIC_BASE_PATH || "").replace(/\/$/, "");

/**
 * Build a URL for something in /public/. Accepts either a leading-slash
 * absolute path or a bare filename; both resolve to the deployment's
 * correct location whether that's the domain root or a subpath.
 *
 *   asset("data/search-index.json")   → "/ResearchMap/data/search-index.json"
 *   asset("/data/search-index.json")  → same
 */
export function asset(path: string): string {
  const trimmed = path.startsWith("/") ? path : `/${path}`;
  return `${BASE}${trimmed}`;
}
