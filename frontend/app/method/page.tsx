import Link from "next/link";
import { getSiteFacts, getValidation } from "../../lib/data";
import { pageMeta } from "../../lib/meta";
import { site } from "../../lib/site";

export const metadata = pageMeta({
  title: "Method",
  description: `How ${site.siteName} reads papers, what was checked by hand and by whom, and the known limits of each library.`,
  path: "/method/",
});

const nm = (v: number | null | undefined) => (v === null || v === undefined ? "not measured" : String(v));

export default function Method() {
  const facts = getSiteFacts();
  return (
    <article className="trust">
      <h1>Method</h1>
      <p className="lede">
        The rule behind the whole project: a language model only turns paper text into
        structured notes, and (for possible disagreements) answers one narrow question about
        one pair of claims at a time. Everything that counts, ranks or decides what to show is
        ordinary code that anyone can read in the public source.
      </p>

      <h2>The pipeline</h2>
      <ol>
        <li><strong>Collect.</strong> Papers on one subject are gathered from OpenAlex and
          sorted into on-topic, borderline and off-topic by fixed keyword rules (venue, field,
          and whether the subject&apos;s key terms appear together). Off-topic papers are
          dropped.</li>
        <li><strong>Read.</strong> A Google Gemini model reads each paper — the full text where
          an open-access copy could be found, otherwise the abstract — and records its claims,
          stated limits, methods and suggested next steps.</li>
        <li><strong>Compare.</strong> Code looks for questions a paper raised that no later
          paper in the library took up, and for limits that recur. For disagreements, code
          picks out pairs of claims whose wording is very similar; only those pairs are
          ever checked, and the model is asked about each pair on its own.</li>
        <li><strong>Order.</strong> Code ranks results by fixed rules. The model&apos;s own
          confidence is never used in a score.</li>
        <li><strong>Check.</strong> Flagged disagreements are checked by hand (below). Doubts
          about our own checks are published, not hidden.</li>
      </ol>

      <h2>What each library contains</h2>
      <table>
        <thead><tr><th>Library</th><th>Papers</th><th>Claims read from</th><th>Full text</th><th>Abstract only</th><th>Built</th></tr></thead>
        <tbody>
          {facts.libraries.map((l) => (
            <tr key={l.slug}>
              <td>{l.name}</td><td>{l.papers}</td>
              <td>{l.claims_read === null ? "not measured" : `${l.claims_read} of ${l.papers}`}</td>
              <td>{l.full_text}</td><td>{l.abstract_only}</td>
              <td>{l.built ?? "not measured"}</td>
            </tr>
          ))}
        </tbody>
      </table>

      <h2>How the libraries grow</h2>
      <p>
        {facts.libraries.filter((l) => l.growth.grows).map((l) => l.name).join(" and ")} are set up
        to grow once a week. An automated run looks in OpenAlex for three kinds of new paper: papers that cite
        both sides of a checked disagreement, papers that cite a paper whose open question is
        unanswered, and recent papers that cite the library. It keeps the papers the library&apos;s
        labelling rules accept, removes duplicates, and has a language model take notes on them as
        above. Code then runs the same checks again. A run changes the site only if every automated
        test passes; otherwise nothing is published.
      </p>
      <ul>
        <li>A newly found disagreement is shown as &ldquo;Flagged by the system, not yet
          checked&rdquo; and is not counted anywhere on this site until it has been checked by
          hand.</li>
        <li>A method-transfer lead is shown only after the language-model check has looked at
          it.</li>
        <li>Spending on the language model is capped per week and in total, in code, before any
          call is made.</li>
      </ul>
      <table>
        <thead><tr><th>Library</th><th>Papers added by weekly runs</th><th>Last added</th></tr></thead>
        <tbody>
          {facts.libraries.filter((l) => l.growth.grows).map((l) => (
            <tr key={l.slug}>
              <td>{l.name}</td><td>{l.growth.added}</td>
              <td>{l.growth.last_added ?? "none yet"}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="small">
        {facts.libraries.filter((l) => !l.growth.grows).map((l) => l.name).join(" and ")} does
        not grow: it is kept fixed so that a planned test (whether its results pointed to research
        that was later done) has a fixed starting point.
      </p>

      <h2>What was found in each library</h2>
      <table>
        <thead><tr><th>Library</th><th>Results</th><th>By type</th></tr></thead>
        <tbody>
          {facts.libraries.map((l) => (
            <tr key={l.slug}>
              <td>{l.name}</td>
              <td>{l.results_total}</td>
              <td>
                {l.results.map((r) => (
                  <div key={r.type}>
                    {r.count === null
                      ? <>{r.label.charAt(0).toUpperCase() + r.label.slice(1)}: {r.note}.</>
                      : <>{r.count} {r.label}{r.count === 0 ? ` (${r.note})` : ""}</>}
                  </div>
                ))}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="small">
        Every library goes through the same four checks with the same thresholds. For the
        method-transfer check, the number of topic groups grows with the size of the library,
        and the strongest leads (at most 15 per library) are checked one by one by a language
        model, which labels each as substantive, trivial or not addressing the problem. {" "}
        {facts.libraries[0]?.not_run}
      </p>

      <h2>What was checked by hand, and by whom</h2>
      <table>
        <thead><tr><th>Library</th><th>Similar claim pairs checked</th><th>Flagged as disagreeing</th><th>Kept after checking</th><th>Set aside</th><th>How</th></tr></thead>
        <tbody>
          {facts.libraries.map((l) => {
            const d = l.disagreement_check;
            return (
              <tr key={l.slug}>
                <td>{l.name}</td>
                <td>{d ? `${d.classified} of ${d.shortlisted}` : "not measured"}</td>
                <td>{nm(d?.flagged)}</td>
                <td>{nm(d?.confirmed)}</td>
                <td>{nm(d?.set_aside)}</td>
                <td>{d?.checked_how ?? (d && d.flagged === 0 ? "nothing was flagged" : "not measured")}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
      <p className="small">
        All hand checks so far were done by the person who built the project, not by
        independent experts. A blind review packet for the diet disagreements has been prepared
        for outside experts but has not been sent.
      </p>
      {facts.libraries.some((l) => l.audit_doubts.length) && (
        <>
          <h2>Verdicts we now doubt</h2>
          <ul>
            {facts.libraries.flatMap((l) => l.audit_doubts.map((d, i) => (
              <li key={`${l.slug}-${i}`}><strong>{l.short_name}:</strong> {d}</li>
            )))}
          </ul>
        </>
      )}

      <h2>Has this been tested?</h2>
      {(() => {
        const v = getValidation();
        if (!v) return <p>Not yet. No test of whether the results anticipate later research has been run.</p>;
        return (
          <>
            <p><strong>{v.plain}</strong></p>
            <p>
              The test was written down before it was run: freeze each library at an earlier year,
              let the tool rank the questions it finds open, then check whether papers citing each
              question&apos;s source paper took it up in the next two years. {v.n} questions were
              tested and {v.addressed} were taken up; a test able to tell a useful ranking from
              chance would need at least {v.n_required}.
            </p>
            <table>
              <thead><tr><th>Ranking</th><th>How well it picked the questions later taken up (0.5 = chance)</th></tr></thead>
              <tbody>
                <tr><td>This tool</td><td>{v.engine_auc} (95% range {v.engine_auc_ci[0]}–{v.engine_auc_ci[1]})</td></tr>
                <tr><td>Most-cited source paper first</td><td>{v.citation_auc} (95% range {v.citation_auc_ci[0]}–{v.citation_auc_ci[1]})</td></tr>
                <tr><td>Newest source paper first</td><td>{v.recency_auc}</td></tr>
                <tr><td>Random order</td><td>{v.random_auc}</td></tr>
              </tbody>
            </table>
            <p className="small">
              &ldquo;Taken up&rdquo; is a proxy: a citing paper whose summary is close in meaning to
              the question. Citing is not the same as answering. Full report:{" "}
              <Link href="/findings/validation-v1/">Validation v1</Link> (protocol committed before the
              run, {v.protocol_commit}).
            </p>
          </>
        );
      })()}

      <h2>Known limits</h2>
      <ul>
        <li><strong>Partial reading.</strong>{" "}
          {facts.libraries.map((l, i) => (
            <span key={l.slug}>{i ? "; " : ""}{l.name}: {l.abstract_only} of {l.papers} papers read
              from the abstract only</span>
          ))}. A limit or next step mentioned only in the body of a paper can be missed.</li>
        <li><strong>Only what is in the library.</strong> A question can look unanswered here
          because the paper that answered it is not in the collection.</li>
        <li><strong>Only similar pairs are compared.</strong> Two findings that disagree but
          are worded differently are never picked out, so they are never checked. Zero
          disagreements means none were found among the pairs checked, not that none exist.</li>
        <li><strong>The model can misread.</strong> Notes are extracted by a language model and
          can drop a condition or overstate a finding. Each result links to the paper so you
          can check.</li>
        <li><strong>Not yet validated.</strong> Whether the listed questions predict later
          research has not been tested.</li>
      </ul>
      <p className="small muted">
        The detailed working notes are on the <Link href="/library/">library page</Link>.
        Numbers on this page are generated from the project&apos;s data files by a script in the
        source code.
      </p>
    </article>
  );
}
