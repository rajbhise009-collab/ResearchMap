import { getLanguage } from "../../lib/data";
import PapersPageClient from "./PapersPageClient";

export default function PapersPage() {
  return <PapersPageClient lang={getLanguage()} />;
}
