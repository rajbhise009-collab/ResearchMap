// Query hygiene for anything a visitor types or puts in ?q=. React already
// escapes text, so nothing here is about script injection; this is about
// what gets stored, searched and echoed back:
//   - control characters, NULs, zero-width and bidi-override characters are
//     removed (they can hide or reorder text in an echo);
//   - runs of whitespace collapse, but a trailing space is kept (the search
//     uses it to tell "still typing a word" from "word finished");
//   - length is capped.
export const MAX_QUERY = 200;
export const MAX_ECHO = 80;

// C0/C1 controls (except tab/newline handled as whitespace), zero-width,
// bidi embeddings/overrides/isolates, BOM.
const STRIP = /[\u0000-\u0008\u000B\u000C\u000E-\u001F\u007F-\u009F​-‏‪-‮⁠-⁩﻿]/g;

export function cleanQuery(raw: string | null | undefined): string {
  if (!raw) return "";
  const s = raw.replace(STRIP, "").replace(/\s+/g, " ");
  return s.replace(/^ /, "").slice(0, MAX_QUERY);
}

/** What we show back to the reader: cleaned, trimmed, capped. */
export function echoQuery(raw: string | null | undefined, max = MAX_ECHO): string {
  const s = cleanQuery(raw).trim();
  return s.length > max ? `${s.slice(0, max - 1)}…` : s;
}
