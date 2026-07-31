import { getPaperDocs, getLanguage } from "../../lib/data";
import PapersClient from "./PapersClient";

export default function PapersPage() {
  const papers = getPaperDocs();
  const lang = getLanguage();
  const abstractOnly = papers.filter((p) => p.abstract_only).length;
  return (
    <>
      <div className="hero" style={{ marginBottom: "2.5rem" }}>
        <h1 style={{ fontSize: "2rem" }}>{lang.ui.all_papers}</h1>
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
