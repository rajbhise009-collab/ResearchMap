import { pageMeta } from "../../lib/meta";
import { site } from "../../lib/site";

export const metadata = pageMeta({
  title: "Terms",
  description: `${site.siteName} is a research aid, not advice. No warranty. Paper data comes from open sources with attribution; the code is MIT-licensed.`,
  path: "/terms/",
});

export default function Terms() {
  const licence = site.repoUrl ? `${site.repoUrl.replace(/\/+$/, "")}/blob/main/LICENSE` : null;
  return (
    <article className="trust">
      <h1>Terms</h1>
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
        <li><strong>Code licence.</strong> The source code is released under the MIT
          licence{licence && site.repoIsPublic ? <> (<a href={licence}>read it</a>)</> : null}.</li>
      </ul>
    </article>
  );
}
