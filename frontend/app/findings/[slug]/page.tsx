import Link from "next/link";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { getFindings, getFinding } from "../../../lib/data";

export function generateStaticParams() {
  return getFindings().map((f) => ({ slug: f.slug }));
}

export default function FindingDetail({ params }: { params: { slug: string } }) {
  const f = getFinding(params.slug);
  return (
    <>
      <p className="small"><Link href="/findings/">← all findings</Link></p>
      <article className="md">
        <ReactMarkdown remarkPlugins={[remarkGfm]}>{f.markdown}</ReactMarkdown>
      </article>
    </>
  );
}
