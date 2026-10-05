"use client";
// Library selector + client-side library-scoping hook.
//
// The static export renders LLM-cal at build time. To let a reader pick
// a different library without a full backend, we mirror the selection
// in the URL (?lib=<slug>) — client components re-fetch that library's
// snapshot at runtime. A hard reload switches the pre-rendered server
// content too, so the header/nav stays consistent.
//
// The switcher itself is a plain <select>: no dropdown library, no
// runtime CSS-in-JS, works keyboard-first.

import { useEffect, useMemo, useState, useCallback } from "react";
import { asset } from "../../lib/basePath";
import type { LibrariesManifest, LibraryManifest } from "../../lib/types";
import { storageGet, storageSet, LIBRARY_KEY } from "../../lib/storage";
import { LIBRARY_EVENT } from "../../lib/activeLibrary";

const LS_KEY = LIBRARY_KEY;

export function useLibraries(): LibrariesManifest | null {
  const [m, setM] = useState<LibrariesManifest | null>(null);
  useEffect(() => {
    let live = true;
    fetch(asset("/data/libraries.json"))
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(String(r.status)))))
      .then((j: LibrariesManifest) => { if (live) setM(j); })
      .catch(() => { /* library manifest is optional — old deploys */ });
    return () => { live = false; };
  }, []);
  return m;
}

/** Read the currently-active library from the URL (?lib=…), fall back
 *  to the default. Client-only. */
export function useCurrentLibrary(libraries: LibrariesManifest | null): LibraryManifest | null {
  const [slug, setSlug] = useState<string | null>(null);
  useEffect(() => {
    if (typeof window === "undefined") return;
    const url = new URLSearchParams(window.location.search).get("lib");
    if (url) { setSlug(url); return; }
    const remembered = storageGet(LS_KEY);
    if (remembered) { setSlug(remembered); return; }
    setSlug(libraries?.default_slug ?? null);
  }, [libraries]);
  // A deep link may switch library after load (lib/activeLibrary.ts).
  useEffect(() => {
    const on = (e: Event) => {
      const next = (e as CustomEvent<{ slug: string }>).detail?.slug;
      if (next) setSlug(next);
    };
    window.addEventListener(LIBRARY_EVENT, on);
    return () => window.removeEventListener(LIBRARY_EVENT, on);
  }, []);
  return useMemo(() => {
    if (!libraries || !slug) return libraries?.libraries[0] ?? null;
    return libraries.libraries.find((l) => l.slug === slug) ?? libraries.libraries[0];
  }, [libraries, slug]);
}

/** URL for the given library — preserves whatever path the user is on
 *  and updates ?lib=. `null` clears the param. */
function libraryUrl(slug: string | null): string {
  if (typeof window === "undefined") return "/";
  const url = new URL(window.location.href);
  if (slug) url.searchParams.set("lib", slug);
  else url.searchParams.delete("lib");
  return url.pathname + url.search + url.hash;
}

export function LibrarySwitcher() {
  const libraries = useLibraries();
  const current = useCurrentLibrary(libraries);
  const onChange = useCallback((e: React.ChangeEvent<HTMLSelectElement>) => {
    const s = e.target.value;
    storageSet(LS_KEY, s);
    // Hard reload so server-rendered content re-hydrates with the new
    // library's data (client-side data-fetch handles the sections that
    // are already client components).
    window.location.href = libraryUrl(s);
  }, []);

  if (!libraries || libraries.libraries.length < 2) return null;
  return (
    <label className="lib-switcher">
      <span className="lib-switcher-label">Library:</span>
      <select
        value={current?.slug ?? libraries.default_slug}
        onChange={onChange}
        aria-label="Select which library to browse"
      >
        {libraries.libraries.map((l) => (
          <option key={l.slug} value={l.slug}>{l.short_name}</option>
        ))}
      </select>
    </label>
  );
}

export function LibraryBadge() {
  const libraries = useLibraries();
  const current = useCurrentLibrary(libraries);
  if (!current || !libraries) return null;
  return (
    <span className="lib-badge" title={current.blurb}>
      {current.short_name}
      <span className="lib-badge-count"> · {current.n_papers} papers</span>
    </span>
  );
}
