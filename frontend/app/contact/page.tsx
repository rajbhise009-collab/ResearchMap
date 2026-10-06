import { pageMeta } from "../../lib/meta";
import { site } from "../../lib/site";
import { contactContent } from "../../lib/contact";

export const metadata = pageMeta({
  title: "Contact",
  description: `How to reach the ${site.siteName} project, report a problem with a result, or suggest a subject for a new library.`,
  path: "/contact/",
});

export default function Contact() {
  const { lines, none } = contactContent(site);
  return (
    <article className="trust">
      <h1>Contact</h1>
      <p className="lede">
        Found a result that looks wrong, a broken link, or a subject you would like a library
        for? Please tell us.
      </p>
      {none ? (
        <p>{none}</p>
      ) : (
        <ul>
          {lines.map((l) => (
            <li key={l.href}>{l.lead} <a href={l.href}>{l.label}</a></li>
          ))}
        </ul>
      )}
      {(site.authorName || site.affiliation) && (
        <p className="small muted">
          {[site.authorName, site.affiliation].filter(Boolean).join(" · ")}
        </p>
      )}
      {!none && (
        <p className="small muted">When reporting a result, the page address is the most useful
          thing to include.</p>
      )}
    </article>
  );
}
