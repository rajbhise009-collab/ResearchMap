import Link from "next/link";
import { getLanguage } from "../lib/data";

export default function NotFound() {
  const lang = getLanguage();
  return (
    <div className="notfound">
      <div className="eyebrow">404 · Not in this library</div>
      <h1>That page isn&apos;t here.</h1>
      <p>
        Either the address is wrong, or you followed a link that no longer
        points anywhere in this library. Nothing has been deleted — every
        result and every paper still resolves to the same URL as before.
      </p>
      <p className="muted small" style={{ marginTop: "var(--s-4)" }}>
        This tool covers {lang.ui.library_covers}.
      </p>
      <Link href="/" className="go-back">
        <span aria-hidden>←</span> Back to search
      </Link>
    </div>
  );
}
