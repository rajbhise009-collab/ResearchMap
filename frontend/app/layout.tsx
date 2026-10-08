import "./globals.css";
import type { Metadata, Viewport } from "next";
import Link from "next/link";
import { site, SITE_URL, IS_PRODUCTION } from "../lib/site";
import { ogImageFor } from "../lib/meta";
import { getLanguage } from "../lib/data";
import { DevModeProvider, DevBanner } from "./components/DevMode";
import Nav from "./components/Nav";
import CommandPalette, { PaletteHint } from "./components/CommandPalette";
import OptionalAnalytics from "./components/OptionalAnalytics";
import FooterScope from "./components/FooterScope";

const lang = getLanguage();

const HOME_TITLE = `${site.siteName} — ${lang.ui.tagline}`;

// Defaults every page inherits; each page sets its own title, description,
// canonical URL and share tags (lib/meta.ts). Non-production builds
// (VERCEL_ENV !== "production") are noindex.
export const metadata: Metadata = {
  metadataBase: new URL(SITE_URL),
  title: HOME_TITLE,
  description: lang.ui.what_it_does,
  applicationName: site.siteName,
  robots: IS_PRODUCTION ? { index: true, follow: true } : { index: false, follow: false },
  openGraph: {
    title: HOME_TITLE, description: lang.ui.what_it_does, siteName: site.siteName,
    type: "website", url: SITE_URL + "/",
    images: [{ url: ogImageFor(null), width: 1200, height: 630, alt: site.siteName }],
  },
  twitter: { card: "summary_large_image", title: HOME_TITLE, description: lang.ui.what_it_does,
             images: [ogImageFor(null)] },
};

export const viewport: Viewport = {
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#f7f5ef" },
    { media: "(prefers-color-scheme: dark)", color: "#0f0f0b" },
  ],
};

const TRUST_LINKS: Array<[string, string]> = [
  ["/about/", "About"], ["/method/", "Method"], ["/privacy/", "Privacy"],
  ["/terms/", "Terms"], ["/contact/", "Contact · report a problem"],
];
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
        <link rel="apple-touch-icon" sizes="180x180" href={`${BASE}/apple-touch-icon.png`} />
        <script dangerouslySetInnerHTML={{ __html: themeScript }} />
      </head>
      <body>
        <a href="#main" className="skip">Skip to content</a>
        <noscript>
          <div className="noscript">
            <strong>This site needs JavaScript.</strong> Search, results and paper pages
            are loaded in your browser. Please turn JavaScript on, or use a browser that
            supports it. Nothing is tracked or sent anywhere when you do.
          </div>
        </noscript>
        <div className="shell">
          <DevModeProvider>
            {/* The command palette needs the whole library resident on the
                page so ⌘K works from every route without a round trip. It
                stays hidden until the user hits ⌘K or focuses the masthead
                hint. */}
            {/* The palette fetches the active library's gaps and papers when
                it opens; embedding every library's documents here would ship
                them inside every page's HTML (measured ~1 MB per page). */}
            <CommandPalette lang={lang} gaps={[]} papers={[]} />
            <header className="masthead" role="banner">
              <div className="masthead-in">
                <a className="wordmark" href="/">{site.siteName}</a>
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
                <span className="foot-brand">{site.siteName}</span>
                <span className="foot-dot" aria-hidden>·</span>
                <span>
                  <FooterScope
                    prefix={lang.ui.footer_scope_prefix ?? "Working prototype · currently shown"}
                    suffix={lang.ui.footer_scope_suffix ?? "Not a comprehensive research tool."}
                    fallback={lang.ui.footer_scope}
                  />
                </span>
              </div>
              <nav className="foot-links" aria-label="About this site">
                {TRUST_LINKS.map(([href, label]) => (
                  <Link key={href} href={href}>{label}</Link>
                ))}
              </nav>
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
              <div className="foot-sources">
                <span className="foot-sources-label">{lang.privacy_note.label}:</span>{" "}
                <span className="foot-sources-intro">{lang.privacy_note.body}</span>
              </div>
            </footer>
            <OptionalAnalytics />
          </DevModeProvider>
        </div>
      </body>
    </html>
  );
}
