import { getLanguage, getGapDocs, getPaperDocs } from "../lib/data";
import Ask from "./components/Ask";
import LibraryScopedHero from "./components/LibraryScopedHero";

export default function Landing() {
  const lang = getLanguage();
  return (
    <>
      <LibraryScopedHero
        tagline={lang.ui.tagline}
        whatItDoes={lang.ui.what_it_does}
      />
      {/* Ask stays scoped to the default library's search index for
          now — full per-library search routing lives in Ask.tsx and
          hits the current library's snapshot_path when ?lib=…. */}
      <Ask lang={lang} gaps={getGapDocs()} papers={getPaperDocs()} />
    </>
  );
}
