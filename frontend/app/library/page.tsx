import { getLanguage } from "../../lib/data";
import LibraryPageClient from "./LibraryPageClient";

export default function LibraryPage() {
  return <LibraryPageClient lang={getLanguage()} />;
}
