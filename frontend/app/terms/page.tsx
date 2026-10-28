import "../components/pages.css";   // styles for every page except home (first paint)
import { pageMeta } from "../../lib/meta";
import { site, NON_AFFILIATION } from "../../lib/site";
import DocLayout from "../components/DocLayout";

export const metadata = pageMeta({
  title: "Terms",
  description: `${site.siteName} is a research aid, not advice. No warranty. The code and original text are all rights reserved; paper data comes from open sources with attribution.`,
  path: "/terms/",
});

// DRAFT, flagged for legal review (2026-10-26): not final until a lawyer has
// read it. The status line below says so on the page; remove it only after
// that review.
export default function Terms() {
  const licence = site.repoUrl ? `${site.repoUrl.replace(/\/+$/, "")}/blob/main/LICENSE` : null;
  return (
    <DocLayout><article className="trust">
      <h1>Terms</h1>
      <p className="trust-status">Draft, last updated 26 October 2026. These terms have not yet been
        reviewed by a lawyer.</p>
      <ul>
        <li><strong>A research aid, not advice.</strong> Nothing here is medical, dietary,
          legal, financial or any other professional advice. Results are a starting point for
          reading the papers, not a conclusion.</li>
        <li><strong>No warranty.</strong> The site and its results are provided as they are,
          without any guarantee that they are complete, correct or fit for a purpose.</li>
        <li><strong>Check the sources.</strong> Every result links to the papers behind it.
          Read them before relying on anything shown here.</li>
        <li><strong>Data.</strong> Paper metadata comes from OpenAlex (CC0), with further
          sources credited in the footer of every page. Paper text belongs to its authors and
          publishers; this site shows short extracted claims and links, never full text.</li>
        <li><strong>Copyright.</strong> The site&rsquo;s code and the original text written for it
          are &copy; {site.copyrightYear} {site.copyrightOwner}, all rights reserved; they are not
          licensed for reuse{licence && site.repoIsPublic ? <> (<a href={licence}>licence</a>)</> : null}.
          This does not extend to material that belongs to others: paper metadata comes from
          OpenAlex (CC0), and paper titles, abstracts and quoted text belong to their authors and
          publishers.</li>
        <li><strong>Not affiliated.</strong> {NON_AFFILIATION}</li>
        <li><strong>Using the site.</strong> You are welcome to read, link to and share individual
          pages. Automated scraping, bulk downloading or copying of the site&rsquo;s compiled content
          (its results, summaries and data files) is not permitted without written permission.
          Search engines may index the pages.</li>
      </ul>
    </article></DocLayout>
  );
}
