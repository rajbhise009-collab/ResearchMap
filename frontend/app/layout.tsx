import "./globals.css";
import type { Metadata } from "next";
import { getLanguage, getGapDocs, getPaperDocs } from "../lib/data";
import { DevModeProvider, DevBanner } from "./components/DevMode";
import Nav from "./components/Nav";
import CommandPalette, { PaletteHint } from "./components/CommandPalette";

const lang = getLanguage();

export const metadata: Metadata = {
  title: `${lang.ui.product_name} — ${lang.ui.tagline}`,
  description: lang.ui.what_it_does,
};
// Next's metadata.icons doesn't apply basePath — it emits the raw URL as
// given. For a subpath deploy that would 404. Compose the correct URL
// once from the build-time env vars and emit the tags in <head> ourselves.
// Read BASE_PATH first (what's actually set during the build); fall back
// to NEXT_PUBLIC_BASE_PATH for anyone who set only that.
const BASE = (
  process.env.BASE_PATH ||
  process.env.NEXT_PUBLIC_BASE_PATH ||
  ""
).replace(/\/$/, "");

// Small script that runs before paint: if the URL says ?theme=light|dark,
// stamp it on <html> so the CSS palette matches. Kept inline so there's
// no FOUC on first paint. Zero effect otherwise.
const themeScript = `try{var t=new URLSearchParams(location.search).get('theme');if(t==='light'||t==='dark')document.documentElement.setAttribute('data-theme',t)}catch(e){}`;

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <head>
        <link rel="icon" type="image/svg+xml" href={`${BASE}/favicon.svg`} />
        <link rel="icon" type="image/png" sizes="32x32" href={`${BASE}/favicon-32.png`} />
        <script dangerouslySetInnerHTML={{ __html: themeScript }} />
      </head>
      <body>
        <a href="#main" className="skip">Skip to content</a>
        <div className="shell">
          <DevModeProvider>
            {/* The command palette needs the whole library resident on the
                page so ⌘K works from every route without a round trip. It
                stays hidden until the user hits ⌘K or focuses the masthead
                hint. */}
            <CommandPalette
              lang={lang}
              gaps={getGapDocs()}
              papers={getPaperDocs()}
            />
            <header className="masthead" role="banner">
              <div className="masthead-in">
                <a className="wordmark" href="/">{lang.ui.product_name}</a>
                <Nav />
                <span className="grow" />
                <PaletteHint />
              </div>
            </header>

            <main id="main">
              <DevBanner note={lang.dev.on_note} />
              {children}
            </main>

            <footer className="foot" role="contentinfo">
              <div className="foot-in">
                <span className="foot-brand">{lang.ui.product_name}</span>
                <span className="foot-dot" aria-hidden>·</span>
                <span>{lang.ui.footer_scope}</span>
              </div>
              <div className="foot-sources">
                <span className="foot-sources-label">{lang.libraries_note.label}:</span>{" "}
                <span className="foot-sources-intro">{lang.libraries_note.intro}</span>
                <ul className="foot-sources-list">
                  {lang.libraries_note.items.map((lib) => (
                    <li key={lib.slug}>
                      <strong>{lib.name}</strong>{" "}
                      <span className="foot-sources-note">
                        ({lib.n_papers} papers) — {lib.note}
                      </span>
                    </li>
                  ))}
                </ul>
              </div>
              <div className="foot-sources">
                <span className="foot-sources-label">{lang.attribution.label}:</span>{" "}
                <span className="foot-sources-intro">{lang.attribution.intro}</span>
                <ul className="foot-sources-list">
                  {lang.attribution.items.map(([name, url, note]) => (
                    <li key={name}>
                      <a href={url} target="_blank" rel="noopener noreferrer">{name}</a>
                      <span className="foot-sources-note"> — {note}</span>
                    </li>
                  ))}
                </ul>
              </div>
            </footer>
          </DevModeProvider>
        </div>
      </body>
    </html>
  );
}
