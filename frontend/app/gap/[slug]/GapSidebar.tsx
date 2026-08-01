"use client";
// Sticky in-page nav. Highlights the section currently in view using an
// IntersectionObserver — a lot smaller than scrollspy libraries and no
// runtime cost for pages nobody scrolls.

import { useEffect, useState } from "react";

export default function GapSidebar({ sections }: { sections: [string, string][] }) {
  const [active, setActive] = useState<string>(sections[0]?.[0] ?? "");

  useEffect(() => {
    // We fire on the first section that has crossed above the header
    // baseline (~96px). rootMargin's negative bottom keeps sections from
    // "winning" while they're still at the bottom of the viewport.
    const io = new IntersectionObserver(
      (entries) => {
        // Prefer the entry closest to the top of the viewport that is
        // currently intersecting.
        const visible = entries
          .filter((e) => e.isIntersecting)
          .sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top);
        if (visible[0]?.target?.id) setActive(visible[0].target.id);
      },
      { rootMargin: "-96px 0px -60% 0px", threshold: [0, 0.5, 1] }
    );
    for (const [id] of sections) {
      const el = document.getElementById(id);
      if (el) io.observe(el);
    }
    return () => io.disconnect();
  }, [sections]);

  return (
    <nav className="detail-sidebar" aria-label="On this page">
      <div className="kicker">On this page</div>
      <ol>
        {sections.map(([id, label]) => (
          <li key={id}>
            <a href={`#${id}`} className={active === id ? "on" : undefined}>
              {label}
            </a>
          </li>
        ))}
      </ol>
    </nav>
  );
}
