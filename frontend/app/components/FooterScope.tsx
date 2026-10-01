"use client";
// Footer "Working prototype · currently shown: N papers on <library>."
// Follows the active library (via ?lib= or localStorage).
//
// The prefix/suffix strings come from the language pack so copy still
// lives in one place; only the dynamic middle (n_papers + name) is
// computed here from the live library manifest.

import { useLibraries, useCurrentLibrary } from "./LibrarySwitcher";

export default function FooterScope({ prefix, suffix, fallback }: {
  prefix: string;
  suffix: string;
  fallback: string;
}) {
  const libraries = useLibraries();
  const current = useCurrentLibrary(libraries);
  if (!current) {
    // Pre-hydration or missing manifest → render the server-side fallback
    // (the hardcoded 113-paper LLM-cal string) so there's no layout jump.
    return <>{fallback}</>;
  }
  const n = current.n_papers;
  const name = current.name;
  return <>{`${prefix}: ${n} papers on ${name.toLowerCase()}. ${suffix}`}</>;
}
