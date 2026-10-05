// sitemap.xml, generated at build from the snapshots: every library's gap
// and paper pages (by canonical URL, no ?lib duplicates), the listing
// pages, the trust pages and the findings notes. Trailing slashes match the
// static export.
import type { MetadataRoute } from "next";
import {
  allOpportunitySlugsAcrossLibraries, allPaperWidsAcrossLibraries, getFindings,
  getSiteFacts, primaryOwner,
} from "../lib/data";
import { absUrl } from "../lib/site";

export const dynamic = "force-static";

export default function sitemap(): MetadataRoute.Sitemap {
  const built = new Map(getSiteFacts().libraries.map((l) => [l.slug, l.built]));
  const when = (slug?: string | null) => {
    const d = slug ? built.get(slug) : null;
    return d ? new Date(`${d}T00:00:00Z`) : undefined;
  };
  const statics = ["/", "/gaps/", "/papers/", "/library/", "/about/", "/method/",
                   "/privacy/", "/terms/", "/contact/"];
  return [
    ...statics.map((p) => ({ url: absUrl(p) })),
    ...getFindings().map((f) => ({ url: absUrl(`/findings/${f.slug}/`) })),
    ...allOpportunitySlugsAcrossLibraries().map((s) => ({
      url: absUrl(`/gap/${s}/`), lastModified: when(primaryOwner("opportunity", s)?.slug) })),
    ...allPaperWidsAcrossLibraries().map((w) => ({
      url: absUrl(`/paper/${w}/`), lastModified: when(primaryOwner("paper", w)?.slug) })),
  ];
}
