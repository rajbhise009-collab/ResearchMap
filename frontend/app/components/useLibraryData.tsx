"use client";
// Client hook that fetches a snapshot file scoped to the currently-
// active library (?lib=<slug> or localStorage → default_slug from
// libraries.json). Returns { state: 'loading'|'ready'|'missing'|'error',
// data, library } so callers can show a proper "not in this library"
// state instead of silently rendering wrong-library content.

import { useEffect, useState } from "react";
import { asset } from "../../lib/basePath";
import type { LibrariesManifest, LibraryManifest } from "../../lib/types";
import { storageGet, LIBRARY_KEY } from "../../lib/storage";
import { resolveOwner } from "../../lib/activeLibrary";

const LS_KEY = LIBRARY_KEY;

export type LibraryDataState<T> =
  | { state: "loading"; data: null; library: LibraryManifest | null }
  | { state: "ready"; data: T; library: LibraryManifest; autoSwitched?: boolean }
  | { state: "missing"; data: null; library: LibraryManifest;
      manifest: LibrariesManifest }
  | { state: "error"; data: null; library: LibraryManifest | null;
      reason: string };

async function loadManifest(): Promise<LibrariesManifest | null> {
  try {
    const r = await fetch(asset("/data/libraries.json"));
    if (!r.ok) return null;
    return (await r.json()) as LibrariesManifest;
  } catch { return null; }
}

function currentSlug(manifest: LibrariesManifest | null): string | null {
  if (typeof window === "undefined") return null;
  const urlLib = new URLSearchParams(window.location.search).get("lib");
  if (urlLib) return urlLib;
  const remembered = storageGet(LS_KEY);
  if (remembered) return remembered;
  return manifest?.default_slug ?? null;
}

/**
 * Fetch a file that lives inside every library's snapshot (e.g.
 * "papers.json", "opportunities.json", "stats.json"). The path is
 * appended to the current library's `snapshot_path`.
 *
 * On a 404 the state is `missing` (paper/opp not in this library) —
 * callers render a "not in this library" fallback instead of silently
 * showing default-library content.
 */
export function useLibraryData<T>(relPath: string, owners?: string[]): LibraryDataState<T> {
  const [s, setS] = useState<LibraryDataState<T>>({
    state: "loading", data: null, library: null,
  });
  useEffect(() => {
    let live = true;
    (async () => {
      const manifest = await loadManifest();
      // Deep links: switch to the library that owns this id (built-time
      // owners list), so a shared URL opens correctly in a fresh browser.
      let slug = currentSlug(manifest);
      let autoSwitched = false;
      if (manifest && owners && owners.length) {
        const r = resolveOwner(manifest, owners);
        slug = r.slug;
        autoSwitched = r.autoSwitched;
      }
      const library = (manifest?.libraries || []).find((l) => l.slug === slug)
                        || manifest?.libraries?.[0];
      if (!library) {
        // Legacy deploy — no manifest. Fall back to root snapshot.
        try {
          const r = await fetch(asset(`/data/${relPath}`));
          if (!r.ok) throw new Error(String(r.status));
          const j = (await r.json()) as T;
          if (live) setS({ state: "ready", data: j,
                            library: {
                              slug: "llm-calibration",
                              name: "Language-model reliability",
                              short_name: "LLM calibration",
                              blurb: "", n_papers: 113,
                              is_default: true, not_advice_note: null,
                              snapshot_path: "/data",
                            } });
        } catch (e) {
          if (live) setS({ state: "error", data: null, library: null,
                            reason: String(e) });
        }
        return;
      }
      const url = asset(`${library.snapshot_path}/${relPath.replace(/^\/+/, "")}`);
      try {
        const r = await fetch(url);
        if (r.status === 404) {
          if (live) setS({ state: "missing", data: null,
                            library, manifest: manifest! });
          return;
        }
        if (!r.ok) throw new Error(String(r.status));
        const j = (await r.json()) as T;
        if (live) setS({ state: "ready", data: j, library, autoSwitched });
      } catch (e) {
        if (live) setS({ state: "error", data: null, library, reason: String(e) });
      }
    })();
    return () => { live = false; };
  }, [relPath, owners ? owners.join(",") : ""]); // eslint-disable-line react-hooks/exhaustive-deps
  return s;
}

/** Small notice shown when a shared link opened a different library than
 *  the one the reader had selected. */
export function LibrarySwitchNotice({ library }: { library: LibraryManifest }) {
  return (
    <p className="lib-switch-notice small sans" role="status">
      Opened in the <strong>{library.name}</strong> library.
    </p>
  );
}
