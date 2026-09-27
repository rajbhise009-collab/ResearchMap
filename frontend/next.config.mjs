/**
 * Two deployment paths from one build:
 *
 *   npm run build                       → served at the domain root
 *                                         (localhost via the launcher, or
 *                                          the root of a custom domain)
 *
 *   BASE_PATH=/ResearchMap npm run build → served under a subpath
 *                                         (e.g. GitHub Pages project sites:
 *                                          username.github.io/ResearchMap/)
 *
 * basePath and assetPrefix are set together so Next rewrites every URL —
 * navigation, static assets — through the prefix. Fetches for data files
 * in /public/ are NOT auto-prefixed by Next; they're read at runtime, so
 * lib/basePath.ts exposes the same value there and every fetch prefixes
 * it. The two knobs stay in lockstep via NEXT_PUBLIC_BASE_PATH below.
 *
 * @type {import('next').NextConfig}
 */
const BASE_PATH = (process.env.BASE_PATH || "").replace(/\/$/, "");

// Developer mode (?dev=1) is a build-time capability, off by default.
// Local launchers (.command / .app / rm-lib.sh) set ENABLE_DEV=1 before
// building so ?dev=1 works there. Public deploys (Vercel, GitHub Pages)
// do NOT set this env var, so ?dev=1 is inert in the shipped bundle.
const ENABLE_DEV = process.env.ENABLE_DEV === "1" ? "1" : "";

const nextConfig = {
  output: "export",          // static HTML export -> frontend/out (no hosting cost)
  trailingSlash: true,       // each route -> dir/index.html, works on any static host
  images: { unoptimized: true },
  reactStrictMode: true,
  basePath: BASE_PATH || undefined,
  assetPrefix: BASE_PATH || undefined,
  env: {
    // Exposed to client code as process.env.NEXT_PUBLIC_*.
    NEXT_PUBLIC_BASE_PATH: BASE_PATH,
    NEXT_PUBLIC_ENABLE_DEV: ENABLE_DEV,
  },
};
export default nextConfig;
