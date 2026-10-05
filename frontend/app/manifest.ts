import type { MetadataRoute } from "next";
import { site } from "../lib/site";
import { getLanguage } from "../lib/data";

export const dynamic = "force-static";

export default function manifest(): MetadataRoute.Manifest {
  return {
    name: site.siteName,
    short_name: site.siteName,
    description: getLanguage().ui.what_it_does,
    start_url: "/",
    display: "standalone",
    background_color: "#f7f5ef",
    theme_color: "#f7f5ef",
    icons: [
      { src: "/favicon.svg", type: "image/svg+xml", sizes: "any" },
      { src: "/icon-192.png", type: "image/png", sizes: "192x192" },
      { src: "/icon-512.png", type: "image/png", sizes: "512x512" },
      { src: "/apple-touch-icon.png", type: "image/png", sizes: "180x180" },
    ],
  };
}
