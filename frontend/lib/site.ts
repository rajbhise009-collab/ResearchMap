// Site identity and canonical URLs — the one place a host or the site
// name lives. Rename the site by editing site.config.json; point it at a
// domain by setting NEXT_PUBLIC_SITE_URL at build time.
import config from "../site.config.json";

export interface SiteConfig {
  siteName: string;
  authorName: string;
  contactEmail: string;
  affiliation: string;
  repoUrl: string;
  repoIsPublic: boolean;
}

export const site: SiteConfig = config as SiteConfig;

/** Fallback when NEXT_PUBLIC_SITE_URL is not set at build time. */
export const DEFAULT_SITE_URL = "https://researchmap-one.vercel.app";

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
