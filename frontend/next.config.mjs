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

const nextConfig = {
  output: "export",          // static HTML export -> frontend/out (no hosting cost)
  trailingSlash: true,       // each route -> dir/index.html, works on any static host
  images: { unoptimized: true },
  reactStrictMode: true,
  basePath: BASE_PATH || undefined,
  assetPrefix: BASE_PATH || undefined,
  env: {
    // Exposed to client code as process.env.NEXT_PUBLIC_BASE_PATH.
    NEXT_PUBLIC_BASE_PATH: BASE_PATH,
  },
};
export default nextConfig;
