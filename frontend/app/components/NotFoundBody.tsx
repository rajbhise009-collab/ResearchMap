// On-brand "not found" body shared by the 404 page and by detail pages
// whose id cannot be found in any library. No hooks: usable from server
// and client components alike.
import Link from "next/link";

export default function NotFoundBody({ libraries, what = "page" }: {
  libraries: Array<{ slug: string; name: string; n_papers?: number }>;
  what?: string;
}) {
  return (
    <div className="notfound">
      <div className="eyebrow">404 · Not found</div>
      <h1>That {what} isn&apos;t here.</h1>
      <p>
        The address doesn&apos;t match anything in any of our libraries. It may
        be mistyped, or it may be from an older version of the site.
      </p>
      <p>
        <Link href="/" className="go-back"><span aria-hidden>←</span> Search a library</Link>
      </p>
      {libraries.length > 0 && (
        <>
          <p className="small muted" style={{ marginTop: "var(--s-5)" }}>Or open a library:</p>
          <ul className="small">
            {libraries.map((l) => (
              <li key={l.slug}>
                <Link href={`/?lib=${encodeURIComponent(l.slug)}`}>{l.name}</Link>
                {typeof l.n_papers === "number" && <span className="muted"> ({l.n_papers} papers)</span>}
              </li>
            ))}
          </ul>
        </>
      )}
    </div>
  );
}
