// Query scrubber for refused / borderline / out-of-domain searches.
//
// UNWIRED IN THIS BUILD. Vercel Hobby doesn't currently include custom
// events; the wiring will land only when a Pro upgrade (or a different
// analytics backend) is authorised. Keeping the scrubber and its tests
// so the discipline is documented and testable even before the wire.
//
// Rules (from the run brief):
//   - Truncate to 80 characters.
//   - Drop anything containing '@' (email fragment) or 6+ consecutive digits
//     (phone / order / paper id).
//   - Never include identifiers.

const EMAIL_LIKE = /@/;
const LONG_DIGIT_RUN = /\d{6,}/;

/** Returns the scrubbed query string, or null if the query must be dropped
 *  entirely. Never returns an empty string — that maps to null too. */
export function scrubQuery(raw: string): string | null {
  if (typeof raw !== "string") return null;
  const trimmed = raw.trim();
  if (!trimmed) return null;
  if (EMAIL_LIKE.test(trimmed)) return null;
  if (LONG_DIGIT_RUN.test(trimmed)) return null;
  return trimmed.slice(0, 80);
}

/** For unit tests — the classifier we'd use if custom events were wired. */
export type Verdict = "in_domain" | "borderline" | "out_of_domain" | "empty";
export function shouldLog(verdict: Verdict): boolean {
  // In-domain queries are NOT logged (they're the successful case; the
  // signal we want is what the library refuses).
  return verdict === "borderline" || verdict === "out_of_domain";
}
