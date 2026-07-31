// The consumer-facing primitives. Every string these render comes from the
// translation layer (public/data/language.json, authored in Python) or from
// a paper's own words — never invented here.

import type { PlainCaveat } from "../../lib/types";

/** Strength as a word, with the sentence that says what the word means.
 *  No bar, no percentage, no colour that implies a score. */
export function Strength({ label, meaning, showMeaning = false }: {
  label: string;
  meaning?: string;
  showMeaning?: boolean;
}) {
  const cls = label === "Strong" ? "strong"
    : label === "Worth a look" ? "look"
    : "unverified";
  return (
    <>
      <span className={`strength ${cls}`}>{label}</span>
      {showMeaning && meaning && <p className="strength-meaning">{meaning}</p>}
    </>
  );
}

/** Caveats are never a footnote and never collapsed — if a result is weak,
 *  the reason sits directly under it at full size. */
export function Caveats({ items }: { items: PlainCaveat[] }) {
  if (!items?.length) return null;
  return (
    <>
      {items.map((c) => (
        <div className="caveat" key={c.code}>
          <span className="cav-label">{c.label}</span>
          {c.text}
        </div>
      ))}
    </>
  );
}

export function Tag({ children, warn = false, title }: {
  children: React.ReactNode; warn?: boolean; title?: string;
}) {
  return <span className={warn ? "tag warn" : "tag"} title={title}>{children}</span>;
}
