import { getLanguage, getGapDocs, getPaperDocs, getSiteFacts } from "../lib/data";
import Ask from "./components/Ask";
import LibraryScopedHero from "./components/LibraryScopedHero";
import { pageMeta } from "../lib/meta";
import { site } from "../lib/site";

export const metadata = pageMeta({
  title: `${site.siteName} — ${getLanguage().ui.tagline}`,
  fullTitle: true,
  description: `${site.siteName} reads one subject's research papers and lists questions they leave open, recurring limits and apparent disagreements, each linked to the papers behind it. A starting point, not a verdict.`,
  path: "/",
});

export default function Landing() {
  const lang = getLanguage();
  return (
    <>
      <LibraryScopedHero
        tagline={lang.ui.tagline}
        whatItDoes={lang.ui.what_it_does}
        qualifier={lang.ui.headline_qualifier}
        facts={getSiteFacts().libraries}
      />
      {/* Ask stays scoped to the default library's search index for
          now — full per-library search routing lives in Ask.tsx and
          hits the current library's snapshot_path when ?lib=…. */}
      <Ask lang={lang} gaps={getGapDocs()} papers={getPaperDocs()} />
    </>
  );
}
