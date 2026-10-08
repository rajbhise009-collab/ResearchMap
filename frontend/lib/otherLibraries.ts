// "This looks like it's about <library>": checks a query against every
// other library's search index, in parallel, and returns the library whose
// index matches it most strongly (in_domain only). Indexes are fetched once
// per page load. Scales to any number of libraries.
import { asset } from "./basePath";
import { search } from "./search";

export interface OtherLib { slug: string; name: string; snapshot_path: string; blurb?: string }

const cache = new Map<string, Promise<any | null>>();

function loadIndex(path: string): Promise<any | null> {
  let p = cache.get(path);
  if (!p) {
    p = fetch(asset(`${path}/search-index.json`))
      .then((r) => (r.ok ? r.json() : null))
      .catch(() => null);
    cache.set(path, p);
  }
  return p;
}

/** Libraries whose index says in_domain for `query`, strongest first. */
export async function matchingLibraries(others: OtherLib[], query: string): Promise<OtherLib[]> {
  const scored = await Promise.all(others.map(async (o) => {
    const idx = await loadIndex(o.snapshot_path);
    if (!idx) return null;
    const r = search(idx, query, 1);
    return r.verdict === "in_domain" ? { o, s: r.best + r.coverage } : null;
  }));
  return scored.filter((x): x is { o: OtherLib; s: number } => x !== null)
    .sort((a, b) => b.s - a.s || a.o.slug.localeCompare(b.o.slug))
    .map((x) => x.o);
}
