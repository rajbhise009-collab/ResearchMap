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
  const navRef = useRef<HTMLElement>(null);
  useEffect(() => {
    // Phones: the nav is one scrollable row; keep the current page in view.
    const nav = navRef.current;
    const on = nav?.querySelector<HTMLElement>("a.on");
    if (nav && on && nav.scrollWidth > nav.clientWidth) {
      nav.scrollLeft = on.offsetLeft - (nav.clientWidth - on.offsetWidth) / 2;
    }
    if (first.current) { first.current = false; return; }
    document.documentElement.setAttribute("data-nav", "");
  }, [path]);
  return (
    <nav aria-label="Main" ref={navRef}>
      {LINKS.map(([href, label]) => (
        <Link key={href} href={href}
          aria-current={path.startsWith(href) ? "page" : undefined}
          className={path.startsWith(href) ? "on" : undefined}
          // A mouse or touch click (detail > 0) gives up focus after it
          // navigates, so some browsers do not draw the keyboard focus ring
          // on the current page's link. Keyboard activation keeps focus.
          onClick={(e) => { if (e.detail > 0) e.currentTarget.blur(); }}>
          {label}
        </Link>
      ))}
    </nav>
  );
}
