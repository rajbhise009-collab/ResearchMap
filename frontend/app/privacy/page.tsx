import { pageMeta } from "../../lib/meta";
import { site } from "../../lib/site";

export const metadata = pageMeta({
  title: "Privacy",
  description: `Exactly what ${site.siteName} collects: anonymous page-view counts only. No cookies; searches run in your browser; downloads are made on your device.`,
  path: "/privacy/",
});

export default function Privacy() {
  return (
    <article className="trust">
      <h1>Privacy</h1>
      <p className="lede">The short version: we count page views, anonymously. That is all.</p>
      <h2>What is collected</h2>
      <ul>
        <li><strong>Page views, through Vercel Web Analytics.</strong> When this site is served
          from its public host, Vercel records which pages were viewed, roughly which country
          the visit came from, and the browser and device type. It does not use cookies and does
          not identify or follow you across sites.</li>
        <li>Nothing else. There are no accounts, no forms, no advertising and no other
          trackers.</li>
      </ul>
      <h2>What stays on your device</h2>
      <ul>
        <li><strong>Searches.</strong> What you type in the search box is matched against an
          index that is downloaded to your browser. The search text is not sent to any
          server.</li>
        <li><strong>Downloads.</strong> BibTeX and CSV files are generated in your browser.</li>
        <li><strong>Your library choice.</strong> The library you picked is remembered in your
          browser&apos;s local storage so the next visit opens it. It never leaves your
          device, and the site works the same if storage is blocked.</li>
      </ul>
      <h2>Links to other sites</h2>
      <p>Paper links go to publishers, doi.org and OpenAlex. Those sites have their own
        privacy policies.</p>
    </article>
  );
}
