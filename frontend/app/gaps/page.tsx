import { getLanguage } from "../../lib/data";
import GapsPageClient from "./GapsPageClient";
import { pageMeta } from "../../lib/meta";

export const metadata = pageMeta({
  title: "What we found",
  description: "Every open question, recurring limit and apparent disagreement found in the selected library, each with the papers behind it and how much evidence there is.",
  path: "/gaps/",
});

export default function GapsPage() {
  return <GapsPageClient lang={getLanguage()} />;
}
