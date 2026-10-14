// One request for the library manifest per page, and the search index
// started before the app's JavaScript has loaded.
//
// app/layout.tsx puts a tiny inline script in <head> (prefetchScript). It
// starts fetching /data/libraries.json at once and, on the home page only and
// just after the first paint (so it never competes with the page's own CSS),
// the active library's search-index.json at low priority (chosen the same way
// as everywhere else: ?lib=, then the remembered library, then the default). Both are
// same-origin static files; nothing about the visitor or any query is sent.
// The app then reuses those requests instead of starting its own after
// hydration, which is what made the first search wait.

import { asset } from "./basePath";
import { LIBRARY_KEY } from "./storage";
import type { LibrariesManifest, SearchIndex } from "./types";

type W = Window & {
  __rmLibs?: Promise<LibrariesManifest | null>;
  __rmIndex?: Promise<SearchIndex | null> | null;
  __rmIndexPath?: string;
};

let libs: Promise<LibrariesManifest | null> | null = null;

/** The library manifest, fetched once per page (shared by every caller). */
export function getLibraries(): Promise<LibrariesManifest | null> {
  if (libs) return libs;
  const w = window as W;
  libs = w.__rmLibs ?? fetch(asset("/data/libraries.json"))
    .then((r) => (r.ok ? r.json() : null))
    .catch(() => null);
  return libs;
}

/** The search index the head script already started for `snapshotPath`,
 *  or null (then the caller fetches it). Handed out once. */
export function takeIndexPrefetch(snapshotPath: string): Promise<SearchIndex | null> | null {
  const w = window as W;
  if (w.__rmIndex && w.__rmIndexPath === snapshotPath) {
    const p = w.__rmIndex;
    w.__rmIndex = null;
    return p;
  }
  return null;
}

/** A question typed and submitted before the app took over the page: the
 *  head script stops the browser's own form submit (which would reload the
 *  page and lose the text) and keeps the text here, in memory only. */
export function takeEarlyQuery(): string {
  const w = window as W & { __rmEarly?: string; __rmHydrated?: boolean };
  w.__rmHydrated = true;
  const q = w.__rmEarly || "";
  w.__rmEarly = "";
  return q;
}

/** The inline <head> script. `base` is the deployment's base path. */
export function prefetchScript(base: string): string {
  const b = JSON.stringify(base);
  const key = JSON.stringify(LIBRARY_KEY);
  return `try{var w=window,B=${b};`
    + `document.addEventListener('submit',function(e){var f=e.target;if(f&&f.classList&&f.classList.contains('ask')){e.preventDefault();`
    + `if(!w.__rmHydrated){var i=f.querySelector('#ask-input');if(i)w.__rmEarly=i.value}}},true);`
    + `w.__rmLibs=fetch(B+'/data/libraries.json').then(function(r){return r.ok?r.json():null}).catch(function(){return null});`
    + `var p=location.pathname.replace(B,'');if(p==='/'||p===''){w.__rmIndex=new Promise(function(go){requestAnimationFrame(function(){setTimeout(go,0)})}).then(function(){return w.__rmLibs}).then(function(m){if(!m)return null;`
    + `var s=new URLSearchParams(location.search).get('lib');if(!s){try{s=localStorage.getItem(${key})}catch(e){}}s=s||m.default_slug;`
    + `var L=m.libraries||[],l=null;for(var i=0;i<L.length;i++)if(L[i].slug===s)l=L[i];l=l||L[0];if(!l)return null;`
    + `w.__rmIndexPath=l.snapshot_path;return fetch(B+l.snapshot_path+'/search-index.json',{priority:'low'}).then(function(r){return r.ok?r.json():null})})`
    + `.catch(function(){return null})}}catch(e){}`;
}
