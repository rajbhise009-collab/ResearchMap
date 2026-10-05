import Link from "next/link";
import { getSiteFacts } from "../../lib/data";
import { pageMeta } from "../../lib/meta";
import { site } from "../../lib/site";

export const metadata = pageMeta({
  title: "About",
  description: `What ${site.siteName} is and is not, how it works in five steps, and what each library covers.`,
  path: "/about/",
});

export default function About() {
  const facts = getSiteFacts();
  return (
    <article className="trust">
      <h1>About {site.siteName}</h1>
      <p className="lede">
        {site.siteName} reads the research papers on one subject and lists questions those
        papers leave open: things a paper said should be studied next that no later paper in
        the collection took up, limits that keep coming back, and pairs of findings that
        appear to disagree. Each result links to the papers and sentences behind it.
      </p>

      <h2>What it is not</h2>
      <ul>
        <li>It is not complete. It only knows the papers in the library you have selected, so
          “nobody has answered this” means “no paper in this library answered it”.</li>
        <li>It is not peer review and not advice — medical, dietary or otherwise.</li>
        <li>It is not validated. We have not yet tested whether the questions it lists turn out
          to be ones researchers later worked on.</li>
        <li>It does not read every paper in full. Where no open copy exists, it reads the
          abstract only, and says so on the paper&apos;s page.</li>
      </ul>

      <h2>How it works, in five steps</h2>
      <ol>
        <li>We pick one subject and collect papers on it from OpenAlex, an open catalogue of
          research.</li>
        <li>A language model reads each paper (the full text where an open copy exists,
          otherwise the abstract) and writes down, in a fixed format, what the paper claims,
          the limits it admits and what it says should be studied next. It does not rank or
          judge anything.</li>
        <li>Plain code compares those notes across papers to find unfollowed questions and
          recurring limits. For possible disagreements, code picks pairs of similar claims and
          a language model is asked, one pair at a time, whether the two conflict.</li>
        <li>Code orders the results by fixed rules that are published with the source code,
          and every result keeps a trail back to the papers.</li>
        <li>We check results by hand where we can and write down what we found — including
          the verdicts we now doubt. See <Link href="/method/">Method</Link>.</li>
      </ol>

      <h2>The libraries</h2>
      <table>
        <thead><tr><th>Library</th><th>What it covers</th><th>Papers</th><th>Built</th></tr></thead>
        <tbody>
          {facts.libraries.map((l) => (
            <tr key={l.slug}>
              <td><Link href={`/?lib=${encodeURIComponent(l.slug)}`}>{l.name}</Link></td>
              <td>{l.blurb}</td>
              <td>{l.papers}</td>
              <td>{l.built ?? "not measured"}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="small muted">
        Libraries are built one subject at a time. They do not update themselves.
      </p>
    </article>
  );
}
