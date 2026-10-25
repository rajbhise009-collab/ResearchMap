// Site identity and canonical URLs — the one place a host or the site
// name lives: site.config.json (siteUrl is the production domain; the
// weekly run, the daily health check and tools/live-check.py read the same
// file). NEXT_PUBLIC_SITE_URL at build time overrides it.
import config from "../site.config.json";

export interface SiteConfig {
  siteName: string;
  authorName: string;
  /** Copyright holder named in the footer, /terms and LICENSE. */
  copyrightOwner: string;
  copyrightYear: number;
  contactEmail: string;
  affiliation: string;
  repoUrl: string;
  repoIsPublic: boolean;
  siteUrl: string;
  vercelHost: string;
}

export const site: SiteConfig = config as SiteConfig;

/** Fallback when NEXT_PUBLIC_SITE_URL is not set at build time. */
export const DEFAULT_SITE_URL = site.siteUrl;

export const SITE_URL: string = (process.env.NEXT_PUBLIC_SITE_URL || DEFAULT_SITE_URL)
  .replace(/\/+$/, "");

/** True only for Vercel production builds; every other build is noindex. */
export const IS_PRODUCTION: boolean = process.env.VERCEL_ENV === "production";

/** Absolute URL for a site path (always trailing-slash, like the export). */
export function absUrl(path: string, lib?: string | null): string {
  let p = path.startsWith("/") ? path : `/${path}`;
  if (!/\.[a-z0-9]+$/i.test(p) && !p.endsWith("/")) p += "/";
  const q = lib ? `?lib=${encodeURIComponent(lib)}` : "";
  return `${SITE_URL}${p}${q}`;
}
