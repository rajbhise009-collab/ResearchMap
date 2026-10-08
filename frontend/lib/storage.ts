// Every Web Storage access goes through here. Safari private mode,
// blocked site data and some embedded browsers THROW on access; the site
// must keep working (via ?lib= and id resolution) when storage is gone.
export const LIBRARY_KEY = "researchmap.library";

export function storageGet(key: string): string | null {
  try { return window.localStorage.getItem(key); } catch { return null; }
}

export function storageSet(key: string, value: string): void {
  try { window.localStorage.setItem(key, value); } catch { /* unavailable */ }
}

/** True when the user is typing somewhere (keyboard shortcuts stay off). */
export function typingInField(): boolean {
  const el = typeof document !== "undefined" ? document.activeElement : null;
  if (!(el instanceof HTMLElement)) return false;
  return ["INPUT", "TEXTAREA", "SELECT"].includes(el.tagName) || el.isContentEditable;
}
