// Passing a search query to the next page WITHOUT putting it in the URL.
//
// A query in the URL (?q=…) leaves the browser: it is in the page request the
// server receives, in the Referer header of every request that page makes
// (including the analytics script), and in what page-view analytics records.
// So the query travels in sessionStorage instead:
//   - same tab only (sessionStorage is per tab), never the URL or fragment;
//   - read once and cleared at once (takeHandedOffQuery);
//   - stale hand-offs (older than HANDOFF_TTL_MS) are discarded unread.
// The library choice stays in the URL as ?lib=, which is not private.

import { cleanQuery } from "./query";

const KEY = "rm.handoff.query";
const HANDOFF_TTL_MS = 60_000;
export const HANDOFF_EVENT = "rm:handoff";

// `samePage`: the hand-off is for the page already showing (the palette
// navigating client-side to "/" while it is open), whose search box will not
// remount, so it is told to take the query now. For a link that loads a new
// page this must stay false: otherwise the page being left would take (and
// clear) the hand-off before the browser navigates away.
export function handOffQuery(q: string, { samePage = false }: { samePage?: boolean } = {}): void {
  const query = cleanQuery(q);
  if (!query.trim()) return;
  try {
    sessionStorage.setItem(KEY, JSON.stringify({ q: query, t: Date.now() }));
  } catch { /* storage blocked: the next page simply opens without the query */ }
  if (samePage) {
    try { window.dispatchEvent(new Event(HANDOFF_EVENT)); } catch { /* no window */ }
  }
}

export function takeHandedOffQuery(): string {
  try {
    const raw = sessionStorage.getItem(KEY);
    sessionStorage.removeItem(KEY);              // read once, cleared at once
    if (!raw) return "";
    const { q, t } = JSON.parse(raw) as { q?: string; t?: number };
    if (!q || typeof t !== "number" || Date.now() - t > HANDOFF_TTL_MS) return "";
    return cleanQuery(q);
  } catch {
    return "";
  }
}
