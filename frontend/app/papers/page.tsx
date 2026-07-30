import { getPapers } from "../../lib/data";
import PapersClient from "./PapersClient";

export default function PapersPage() {
  const items = getPapers();
  return (
    <>
      <h1>Corpus papers</h1>
      <p className="lede">
        {items.length} papers after dedup + relabel. Abstract-only papers are flagged —
        they yield ~11× fewer own-work limitations than full text.
      </p>
      <PapersClient items={items} />
    </>
  );
}
