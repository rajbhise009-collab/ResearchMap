"use client";
// Text pages (About, Method, Privacy, Terms, Contact, the library page,
// findings) in the same two-column layout as the rest of the site: the text
// in the reading column, an "On this page" list in the aside, built from the
// page's own h2 headings. Nothing is invented: if a page has fewer than two
// headings the aside stays empty. Hidden on narrow screens.

import { useEffect, useRef, useState, type ReactNode } from "react";

type Heading = { id: string; text: string };

const slug = (t: string) =>
  t.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "").slice(0, 60) || "section";

export default function DocLayout({ children }: { children: ReactNode }) {
  const main = useRef<HTMLDivElement>(null);
  const [headings, setHeadings] = useState<Heading[]>([]);
  const [active, setActive] = useState<string | null>(null);

  useEffect(() => {
    const root = main.current;
    if (!root) return;
    const read = () => {
      const seen = new Set<string>();
      const hs = [...root.querySelectorAll<HTMLHeadingElement>("h2")].map((h) => {
        if (!h.id) {
          let id = slug(h.textContent || "");
          while (seen.has(id) || document.getElementById(id)) id += "-x";
          h.id = id;
        }
        seen.add(h.id);
        return { id: h.id, text: (h.textContent || "").trim() };
      }).filter((h) => h.text);
      setHeadings(hs.length >= 2 ? hs : []);
    };
    read();
    // Client-loaded pages (the library page) add their headings later.
    const mo = new MutationObserver(read);
    mo.observe(root, { childList: true, subtree: true });
    return () => mo.disconnect();
  }, []);

  useEffect(() => {
    if (!headings.length) return;
    const io = new IntersectionObserver((entries) => {
      const vis = entries.filter((e) => e.isIntersecting).sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top);
      if (vis[0]) setActive(vis[0].target.id);
    }, { rootMargin: "-80px 0px -60% 0px" });
    headings.forEach((h) => { const el = document.getElementById(h.id); if (el) io.observe(el); });
    return () => io.disconnect();
  }, [headings]);

  return (
    <div className="doc-grid">
      <div className="doc-main" ref={main}>{children}</div>
      <aside className="doc-aside" aria-label="On this page">
        {headings.length > 0 && (
          <nav className="doc-toc">
            <p className="doc-toc-h">On this page</p>
            <ol>
              {headings.map((h) => (
                <li key={h.id}>
                  <a href={`#${h.id}`} className={active === h.id ? "on" : undefined}>{h.text}</a>
                </li>
              ))}
            </ol>
          </nav>
        )}
      </aside>
    </div>
  );
}
