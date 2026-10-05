// Which library is active, and automatic switching for deep links.
//
// Order: ?lib=<slug> → stored choice → manifest default. A gap or paper
// page knows (from the build) which libraries own its id; if the active
// library does not own it, `resolveOwner` switches to the owner, rewrites
// ?lib in the address bar (so a copied URL is self-describing), stores the
// choice when storage is available, and broadcasts the change so the
// switcher and footer follow.
import type { LibrariesManifest } from "./types";
import { storageGet, storageSet, LIBRARY_KEY } from "./storage";

export const LIBRARY_EVENT = "researchmap:library";

export function libParam(): string | null {
  if (typeof window === "undefined") return null;
  try { return new URLSearchParams(window.location.search).get("lib"); }
  catch { return null; }
}

export function effectiveSlug(manifest: LibrariesManifest | null): string | null {
  return libParam() || storageGet(LIBRARY_KEY) || manifest?.default_slug || null;
}

/** Pick the owner: ?lib if it owns the id, else the default library if it
 *  owns it, else the first owner in manifest order. */
export function pickOwner(manifest: LibrariesManifest, owners: string[],
                          requested: string | null): string | null {
  if (!owners.length) return null;
  if (requested && owners.includes(requested)) return requested;
  if (owners.includes(manifest.default_slug)) return manifest.default_slug;
  const order = manifest.libraries.map((l) => l.slug);
  return [...owners].sort((a, b) => order.indexOf(a) - order.indexOf(b))[0];
}

export function resolveOwner(manifest: LibrariesManifest, owners: string[]):
    { slug: string | null; autoSwitched: boolean } {
  const requested = libParam();
  const before = effectiveSlug(manifest);
  const target = pickOwner(manifest, owners, requested);
  if (!target) return { slug: before, autoSwitched: false };
  if (requested !== target) {
    try {
      const u = new URL(window.location.href);
      u.searchParams.set("lib", target);
      window.history.replaceState(window.history.state, "", u.pathname + u.search + u.hash);
    } catch { /* address bar update is best-effort */ }
  }
  if (before !== target) storageSet(LIBRARY_KEY, target);
  try {
    window.dispatchEvent(new CustomEvent(LIBRARY_EVENT, { detail: { slug: target } }));
  } catch { /* old browsers */ }
  return { slug: target, autoSwitched: before !== target };
}
