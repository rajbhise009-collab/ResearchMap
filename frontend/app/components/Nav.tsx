"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";

const LINKS = [
  ["/gaps/", "What we found"],
  ["/papers/", "Papers"],
  ["/library/", "The library"],
];

export default function Nav() {
  const path = usePathname() || "/";
  return (
    <nav>
      {LINKS.map(([href, label]) => (
        <Link key={href} href={href}
          className={path.startsWith(href) ? "on" : undefined}>
          {label}
        </Link>
      ))}
    </nav>
  );
}
