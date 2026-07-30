"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";

const LINKS = [
  ["/", "Overview"],
  ["/opportunities/", "Opportunities"],
  ["/papers/", "Papers"],
  ["/findings/", "Findings"],
];

export default function Nav() {
  const path = usePathname();
  return (
    <header className="nav">
      <div className="nav-inner">
        <span className="brand">ResearchMap</span>
        {LINKS.map(([href, label]) => {
          const active = href === "/" ? path === "/" : path.startsWith(href);
          return (
            <Link key={href} href={href} className={active ? "active" : ""}>
              {label}
            </Link>
          );
        })}
        <span className="spacer" />
        <span className="tag">113-paper corpus · read-only</span>
      </div>
    </header>
  );
}
