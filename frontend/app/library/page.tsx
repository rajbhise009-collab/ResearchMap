import { getLanguage, getSiteFacts } from "../../lib/data";
import LibraryPageClient from "./LibraryPageClient";
import { pageMeta } from "../../lib/meta";

export const metadata = pageMeta({
  title: "The library",
  description: "What is in each library, how much of each paper was read, and how we checked our own work.",
  path: "/library/",
});

export default function LibraryPage() {
  return <LibraryPageClient lang={getLanguage()} facts={getSiteFacts().libraries} />;
}
