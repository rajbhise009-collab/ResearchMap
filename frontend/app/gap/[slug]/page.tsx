import { allOpportunitySlugsAcrossLibraries, getLanguage } from "../../../lib/data";
import GapDetailClient from "./GapDetailClient";

export function generateStaticParams() {
  return allOpportunitySlugsAcrossLibraries().map((slug) => ({ slug }));
}

export default function GapDetail({ params }: { params: { slug: string } }) {
  return <GapDetailClient slug={params.slug} lang={getLanguage()} />;
}
