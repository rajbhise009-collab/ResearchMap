import { getOpportunities } from "../../lib/data";
import OpportunitiesClient from "./OpportunitiesClient";

export default function OpportunitiesPage() {
  const items = getOpportunities();
  return (
    <>
      <h1>Opportunities</h1>
      <p className="lede">
        Ranked by <strong>trust = score × confidence</strong>. A high score with low
        confidence (a corpus-relative orphan) is ranked below a confirmed lead — and
        <em> looks</em> weaker. Every card shows its caveats inline.
      </p>
      <OpportunitiesClient items={items} />
    </>
  );
}
