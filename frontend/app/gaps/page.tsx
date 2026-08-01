import { getGapDocs, getLanguage } from "../../lib/data";
import GapsClient from "./GapsClient";

export default function GapsPage() {
  const gaps = getGapDocs();
  const lang = getLanguage();
  return (
    <>
      <div className="hero" style={{ marginBottom: "var(--s-7)" }}>
        <div className="eyebrow">The library · Everything we found</div>
        <h1 style={{ fontSize: "clamp(1.9rem, 3.6vw, 2.6rem)" }}>
          {lang.ui.all_opportunities}
        </h1>
        <p className="lede">
          Everything the tool found in this library, strongest first. Each one
          says how sure we are and what would undermine it.
        </p>
      </div>
      <GapsClient gaps={gaps} lang={lang} />
    </>
  );
}
