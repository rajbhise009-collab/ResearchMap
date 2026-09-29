import { getLanguage } from "../../lib/data";
import GapsPageClient from "./GapsPageClient";

export default function GapsPage() {
  return <GapsPageClient lang={getLanguage()} />;
}
