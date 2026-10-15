import "../components/pages.css";   // styles for every page except home (first paint)
import { getLanguage, getSiteFacts } from "../../lib/data";
import LibraryPageClient from "./LibraryPageClient";
import { pageMeta } from "../../lib/meta";
import DocLayout from "../components/DocLayout";

export const metadata = pageMeta({
  title: "The library",
  description: "What is in each library, how much of each paper was read, and how we checked our own work.",
  path: "/library/",
});

export default function LibraryPage() {
  return (
    <DocLayout>
      <LibraryPageClient lang={getLanguage()} facts={getSiteFacts().libraries} />
    </DocLayout>
  );
}
