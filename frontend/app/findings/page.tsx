import Link from "next/link";
import { getFindings } from "../../lib/data";

export default function FindingsPage() {
  const items = getFindings();
  return (
    <>
      <h1>Methodological findings</h1>
      <p className="lede">
        The reports behind the numbers — why 0 contradictions is a real result, how
        abstract-only fidelity was measured, what each scorer did and didn&apos;t find.
      </p>
      {items.length === 0 && <div className="empty">No findings reports yet.</div>}
      {items.map((f) => (
        <div className="card" key={f.slug}>
          <Link href={`/findings/${f.slug}/`}>{f.title}</Link>
        </div>
      ))}
    </>
  );
}
