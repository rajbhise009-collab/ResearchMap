import { getPaperDocs, getLanguage } from "../../lib/data";
import PapersClient from "./PapersClient";

export default function PapersPage() {
  const papers = getPaperDocs();
  const lang = getLanguage();
  const abstractOnly = papers.filter((p) => p.abstract_only).length;
  return (
    <>
      <div className="hero" style={{ marginBottom: "var(--s-7)" }}>
        <div className="eyebrow">The library · Every paper</div>
        <h1 style={{ fontSize: "clamp(1.9rem, 3.6vw, 2.6rem)" }}>
          {lang.ui.all_papers}
        </h1>
        <p className="lede">
          The {papers.length} papers this library is built from. For {abstractOnly} of
          them we only had the summary — those are marked, because we know
          less about them than the rest.
        </p>
      </div>
      <PapersClient papers={papers} lang={lang} />
    </>
  );
}
