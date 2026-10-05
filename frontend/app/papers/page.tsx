import { getLanguage } from "../../lib/data";
import PapersPageClient from "./PapersPageClient";
import { pageMeta } from "../../lib/meta";

export const metadata = pageMeta({
  title: "Papers",
  description: "Every paper in the selected library, with what each one claims, the limits it states and what it suggests should be studied next.",
  path: "/papers/",
});

export default function PapersPage() {
  return <PapersPageClient lang={getLanguage()} />;
}
