import { getLanguage, getSiteFacts } from "../lib/data";
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
        kinds={Object.values(lang.kinds)}
      >
        {/* The search sits inside the hero, right under the headline: the
            one primary action. Ask fetches the active library's gaps and
            papers itself; the props are only a fallback, so nothing is
            embedded in the HTML. */}
        <Ask lang={lang} gaps={[]} papers={[]} />
      </LibraryScopedHero>
    </>
  );
}
