import Link from "next/link";
import type { Metadata } from "next";
import { pageMeta, clip } from "../../../lib/meta";
import { site } from "../../../lib/site";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { getFindings, getFinding, getLanguage } from "../../../lib/data";

export function generateStaticParams() {
  return getFindings().map((f) => ({ slug: f.slug }));
}

export function generateMetadata({ params }: { params: { slug: string } }): Metadata {
  const f = getFinding(params.slug);
  return pageMeta({
    title: clip(f.title, 90),
    description: clip(`A technical working note from the ${site.siteName} project: ${f.title}.`),
    path: `/findings/${params.slug}/`,
  });
}

export default function FindingPage({ params }: { params: { slug: string } }) {
  const f = getFinding(params.slug);
  const lang = getLanguage();
  return (
    <>
      <Link href="/library/" className="crumb">← The library</Link>
      {/* These reports are raw working notes and read like it. Saying so is
          more honest than paraphrasing them into something they are not. */}
      <div className="caveat" style={{ marginBottom: "2rem" }}>
        <span className="cav-label">A technical note</span>
        {lang.ui.findings_are_technical}
      </div>
      <article className="md">
        <ReactMarkdown remarkPlugins={[remarkGfm]}>{f.markdown}</ReactMarkdown>
      </article>
    </>
  );
}
