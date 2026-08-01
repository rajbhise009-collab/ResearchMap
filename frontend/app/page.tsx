import { getLanguage, getGapDocs, getPaperDocs, getStats } from "../lib/data";
import Ask from "./components/Ask";

export default function Landing() {
  const lang = getLanguage();
  const stats = getStats();
  return (
    <>
      <div className="hero-grid">
        <div className="hero">
          <div className="eyebrow">A literature-based discovery tool</div>
          <h1>{lang.ui.tagline}</h1>
          <p className="lede">{lang.ui.what_it_does}</p>
          <p className="covers">{lang.ui.library_summary}</p>
        </div>

        <aside className="about-card" aria-label="About this library">
          <div className="kicker">This library</div>
          <dl>
            <div>
              <dt>Subject</dt>
              <dd>{lang.ui.library_name}</dd>
            </div>
            <div>
              <dt>Papers</dt>
              <dd><span className="num tnum">{stats.papers}</span></dd>
            </div>
            <div>
              <dt>Read in full</dt>
              <dd>
                <span className="num tnum">{stats.full_text}</span>{" "}
                <span className="small muted">of {stats.papers}</span>
              </dd>
            </div>
            <div>
              <dt>Gaps found</dt>
              <dd><span className="num tnum">{Object.values(stats.scorer_yields).reduce((a: number, b: number) => a + (b as number), 0) - (stats.scorer_yields.structural_holes_substantive ?? 0)}</span></dd>
            </div>
          </dl>
        </aside>
      </div>

      <Ask lang={lang} gaps={getGapDocs()} papers={getPaperDocs()} />
    </>
  );
}
