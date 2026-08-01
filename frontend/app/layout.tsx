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

// Small script that runs before paint: if the URL says ?theme=light|dark,
// stamp it on <html> so the CSS palette matches. Kept inline so there's
// no FOUC on first paint. Zero effect otherwise.
const themeScript = `try{var t=new URLSearchParams(location.search).get('theme');if(t==='light'||t==='dark')document.documentElement.setAttribute('data-theme',t)}catch(e){}`;

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <head>
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
                <span>{lang.ui.library_summary}</span>
              </div>
            </footer>
          </DevModeProvider>
        </div>
      </body>
    </html>
  );
}
