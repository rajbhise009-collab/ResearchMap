import { allPaperWidsAcrossLibraries, getLanguage } from "../../../lib/data";
import PaperDetailClient from "./PaperDetailClient";

export function generateStaticParams() {
  return allPaperWidsAcrossLibraries().map((wid) => ({ wid }));
}

export default function PaperDetail({ params }: { params: { wid: string } }) {
  return <PaperDetailClient wid={params.wid} lang={getLanguage()} />;
}
