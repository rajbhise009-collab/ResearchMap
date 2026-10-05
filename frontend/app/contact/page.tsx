import { pageMeta } from "../../lib/meta";
import { site, contactRoutes } from "../../lib/site";

export const metadata = pageMeta({
  title: "Contact",
  description: `How to reach the ${site.siteName} project, report a problem with a result, or suggest a subject for a new library.`,
  path: "/contact/",
});

export default function Contact() {
  const { email, issues } = contactRoutes();
  return (
    <article className="trust">
      <h1>Contact</h1>
      <p className="lede">
        Found a result that looks wrong, a broken link, or a subject you would like a library
        for? Please tell us.
      </p>
      {email || issues ? (
        <ul>
          {email && <li>Email: <a href={`mailto:${email}`}>{email}</a></li>}
          {issues && <li>Or open an issue on GitHub: <a href={issues}>{issues.replace(/^https:\/\//, "")}</a></li>}
        </ul>
      ) : (
        <p>A contact address has not been set up yet.</p>
      )}
      {(site.authorName || site.affiliation) && (
        <p className="small muted">
          {[site.authorName, site.affiliation].filter(Boolean).join(" · ")}
        </p>
      )}
      <p className="small muted">When reporting a result, the page address is the most useful
        thing to include.</p>
    </article>
  );
}
