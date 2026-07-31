import { getLanguage, getGapDocs, getPaperDocs } from "../lib/data";
import Ask from "./components/Ask";

export default function Landing() {
  const lang = getLanguage();
  return (
    <>
      <div className="hero">
        <h1>{lang.ui.tagline}</h1>
        <p>{lang.ui.what_it_does}</p>
        <p className="covers">{lang.ui.library_summary}</p>
      </div>

      <Ask lang={lang} gaps={getGapDocs()} papers={getPaperDocs()} />
    </>
  );
}
