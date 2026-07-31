import "./globals.css";
import type { Metadata } from "next";
import { getLanguage } from "../lib/data";
import { DevModeProvider, DevToggle, DevBanner } from "./components/DevMode";
import Nav from "./components/Nav";

const lang = getLanguage();

export const metadata: Metadata = {
  title: `${lang.ui.product_name} — ${lang.ui.tagline}`,
  description: lang.ui.what_it_does,
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <div className="shell">
          <DevModeProvider>
            <header className="masthead">
              <div className="masthead-in">
                <a className="wordmark" href="/">{lang.ui.product_name}</a>
                <Nav />
              </div>
            </header>

            <main>
              <DevBanner note={lang.dev.on_note} />
              {children}
            </main>

            <footer className="foot">
              <div className="foot-in">
                <span>
                  One library: {lang.ui.library_name.toLowerCase()} — 113 papers.
                </span>
                <span className="grow" />
                <DevToggle label={lang.dev.toggle} />
              </div>
            </footer>
          </DevModeProvider>
        </div>
      </body>
    </html>
  );
}
