// robots.txt: production builds allow crawling and point at the sitemap;
// every other build (previews, local) disallows everything.
import type { MetadataRoute } from "next";
import { absUrl, IS_PRODUCTION } from "../lib/site";

export const dynamic = "force-static";

export default function robots(): MetadataRoute.Robots {
  if (!IS_PRODUCTION) return { rules: [{ userAgent: "*", disallow: "/" }] };
  return { rules: [{ userAgent: "*", allow: "/" }], sitemap: absUrl("/sitemap.xml") };
}
