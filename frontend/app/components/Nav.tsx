"use client";
import { useEffect, useRef } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";

const LINKS = [
  ["/gaps/", "What we found"],
  ["/papers/", "Papers"],
  ["/library/", "The library"],
  ["/about/", "About"],
];

export default function Nav() {
  const path = usePathname() || "/";
  // After the first in-app page change, pages fade in (globals.css
  // html[data-nav]); the first load never animates.
  const first = useRef(true);
  useEffect(() => {
    if (first.current) { first.current = false; return; }
    document.documentElement.setAttribute("data-nav", "");
  }, [path]);
  return (
    <nav aria-label="Main">
      {LINKS.map(([href, label]) => (
        <Link key={href} href={href}
          aria-current={path.startsWith(href) ? "page" : undefined}
          className={path.startsWith(href) ? "on" : undefined}>
          {label}
        </Link>
      ))}
    </nav>
  );
}
