"use client";
// Client hook that fetches a snapshot file scoped to the currently-
// active library (?lib=<slug> or localStorage → default_slug from
// libraries.json). Returns { state: 'loading'|'ready'|'missing'|'error',
// data, library } so callers can show a proper "not in this library"
// state instead of silently rendering wrong-library content.

import { useEffect, useState } from "react";
import { asset } from "../../lib/basePath";
import type { LibrariesManifest, LibraryManifest } from "../../lib/types";

const LS_KEY = "researchmap.library";

export type LibraryDataState<T> =
  | { state: "loading"; data: null; library: LibraryManifest | null }
  | { state: "ready"; data: T; library: LibraryManifest }
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
  try {
    const remembered = window.localStorage.getItem(LS_KEY);
    if (remembered) return remembered;
  } catch {}
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
export function useLibraryData<T>(relPath: string): LibraryDataState<T> {
  const [s, setS] = useState<LibraryDataState<T>>({
    state: "loading", data: null, library: null,
  });
  useEffect(() => {
    let live = true;
    (async () => {
      const manifest = await loadManifest();
      const slug = currentSlug(manifest);
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
        if (live) setS({ state: "ready", data: j, library });
      } catch (e) {
        if (live) setS({ state: "error", data: null, library, reason: String(e) });
      }
    })();
    return () => { live = false; };
  }, [relPath]);
  return s;
}

/**
 * "Not in this library" fallback: names the current library and, when
 * the manifest is available, tells the reader which other libraries
 * might contain the requested item. Deliberately blunt — silence would
 * be dishonest.
 */
export function NotInLibrary({ library, manifest, kind, id, backHref }: {
  library: LibraryManifest;
  manifest: LibrariesManifest;
  kind: "paper" | "gap";
  id: string;
  backHref: string;
}) {
  const others = manifest.libraries.filter((l) => l.slug !== library.slug);
  return (
    <div className="not-in-library">
      <h1 style={{ fontSize: "clamp(1.5rem, 3vw, 2rem)" }}>
        This {kind} isn&apos;t in <em>{library.name}</em>.
      </h1>
      <p className="lede">
        The <code>{id}</code> URL exists, but the {library.short_name} library
        doesn&apos;t include it. Switching libraries via the selector on the
        landing page may find it.
      </p>
      <p>Other libraries in this project:</p>
      <ul>
        {others.map((l) => (
          <li key={l.slug}>
            <a href={`/?lib=${encodeURIComponent(l.slug)}`}>{l.name}</a>{" "}
            <span className="small muted">({l.n_papers} papers)</span>
          </li>
        ))}
      </ul>
      <p><a href={backHref} className="crumb">← back to this library&apos;s list</a></p>
    </div>
  );
}
