"use client";
// The ⌘K entry point. Opens over the whole app, uses the same search
// index and gate the landing page uses, and takes the user directly to
// the first hit (or shows the honest refusal panel inline if the query
// is out-of-domain).
//
// One index, one search function, one gate — the palette can't disagree
// with the landing page because they call the same code.

import {
  useCallback, useEffect, useMemo, useRef, useState,
} from "react";
import { useRouter } from "next/navigation";
import type {
  GapDoc, PaperDoc, LanguagePack, SearchIndex, SearchResult,
} from "../../lib/types";
import { search } from "../../lib/search";

const DEBOUNCE_MS = 90;

function CommandPalette({ lang, gaps, papers }: {
  lang: LanguagePack;
  gaps: GapDoc[];
  papers: PaperDoc[];
}) {
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState("");
  const [result, setResult] = useState<SearchResult | null>(null);
  const [selected, setSelected] = useState(0);
  const [index, setIndex] = useState<SearchIndex | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const router = useRouter();

  // Same lazy fetch pattern as Ask — no double load if both are on the page.
  useEffect(() => {
    if (!open || index) return;
    let live = true;
    // Relative fetch so it works whether the user is at / or /gap/xyz/.
    fetch("/data/search-index.json")
      .then((r) => (r.ok ? r.json() : Promise.reject()))
      .then((j: SearchIndex) => { if (live) setIndex(j); })
      .catch(() => {});
    return () => { live = false; };
  }, [open, index]);

  // ⌘K / Ctrl-K / "/" opens; Esc closes.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const inField = document.activeElement instanceof HTMLElement &&
        ["INPUT", "TEXTAREA"].includes(document.activeElement.tagName);
      if ((e.key === "k" || e.key === "K") && (e.metaKey || e.ctrlKey)) {
        e.preventDefault();
        setOpen((v) => !v);
      } else if (e.key === "/" && !inField && !open) {
        e.preventDefault();
        setOpen(true);
      } else if (e.key === "Escape" && open) {
        setOpen(false);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);

  // The button in the masthead flips the open state — no separate handler.
  // A `#palette` URL fragment also opens it, which doubles as a bookmarkable
  // "quick search" entry from a browser's address bar.
  useEffect(() => {
    const openHandler = () => setOpen(true);
    window.addEventListener("researchmap:open-palette", openHandler);
    if (window.location.hash === "#palette") setOpen(true);
    return () => window.removeEventListener("researchmap:open-palette", openHandler);
  }, []);

  // Focus the input the moment the palette opens.
  useEffect(() => {
    if (open) requestAnimationFrame(() => inputRef.current?.focus());
    else { setQ(""); setResult(null); setSelected(0); }
  }, [open]);

  // Debounced search-as-you-type. 90ms is short enough to feel instant on
  // a modern machine, long enough to skip the middle of a keystroke run.
  useEffect(() => {
    if (!index) return;
    if (!q.trim()) { setResult(null); setSelected(0); return; }
    const t = setTimeout(() => {
      setResult(search(index, q, 12));
      setSelected(0);
    }, DEBOUNCE_MS);
    return () => clearTimeout(t);
  }, [q, index]);

  const gapBySlug = useMemo(() => new Map(gaps.map((g) => [g.slug, g])), [gaps]);
  const paperByWid = useMemo(() => new Map(papers.map((p) => [p.wid, p])), [papers]);

  type Item = { href: string; title: string; kind: string; strength?: string };
  const items: Item[] = useMemo(() => {
    if (!result || result.verdict === "out_of_domain" || result.verdict === "empty") return [];
    const out: Item[] = [];
    for (const h of result.hits) {
      if (h.type === "opportunity") {
        const g = gapBySlug.get(h.ref);
        if (g) out.push({
          href: `/gap/${g.slug}/`,
          title: g.consumer.headline_is_quoted ? `“${g.consumer.headline}”` : g.consumer.headline,
          kind: g.consumer.kind,
          strength: g.consumer.strength,
        });
      } else {
        const p = paperByWid.get(h.ref);
        if (p) out.push({ href: `/paper/${p.wid}/`, title: p.title, kind: "Paper" });
      }
    }
    return out.slice(0, 10);
  }, [result, gapBySlug, paperByWid]);

  const go = useCallback((href: string) => {
    setOpen(false);
    router.push(href);
  }, [router]);

  const onKeyDown = useCallback((e: React.KeyboardEvent) => {
    if (e.key === "ArrowDown") { e.preventDefault(); setSelected((i) => Math.min(items.length - 1, i + 1)); }
    else if (e.key === "ArrowUp") { e.preventDefault(); setSelected((i) => Math.max(0, i - 1)); }
    else if (e.key === "Enter" && items[selected]) { e.preventDefault(); go(items[selected].href); }
    else if (e.key === "Enter" && q.trim() && !items.length) {
      // A fully-typed query with no hits — send them to the honest landing.
      go(`/?q=${encodeURIComponent(q)}`);
    }
  }, [items, selected, q, go]);

  if (!open) return null;

  const showOOD = result?.verdict === "out_of_domain";
  const showBorderline = result?.verdict === "borderline";

  return (
    <div
      className="cmdk-scrim"
      role="dialog" aria-modal="true" aria-label="Search"
      onClick={(e) => { if (e.target === e.currentTarget) setOpen(false); }}
    >
      <div className="cmdk" onKeyDown={onKeyDown}>
        <input
          ref={inputRef}
          className="cmdk-input"
          placeholder={lang.search.placeholder}
          value={q}
          onChange={(e) => setQ(e.target.value)}
          aria-label={lang.search.placeholder}
        />
        <div className="cmdk-list" role="listbox">
          {!q.trim() && (
            <div className="cmdk-empty">{lang.search.hint}</div>
          )}
          {q.trim() && !index && (
            <div className="cmdk-empty">{lang.search.searching}</div>
          )}
          {items.map((it, i) => (
            <a
              key={it.href}
              href={it.href}
              className="cmdk-item"
              role="option" aria-selected={i === selected}
              onMouseEnter={() => setSelected(i)}
              onClick={(e) => { e.preventDefault(); go(it.href); }}
            >
              <div className="title">{it.title}</div>
              <div className="meta">
                <span>{it.kind}</span>
                {it.strength && (<><span>·</span><span>{it.strength}</span></>)}
              </div>
            </a>
          ))}
          {showBorderline && (
            <div className="cmdk-empty" style={{ textAlign: "left", paddingBottom: 8 }}>
              <strong style={{ color: "var(--ink-strong)", display: "block", marginBottom: 6 }}>
                {lang.search.borderline.label}
              </strong>
              {lang.search.borderline.note}
            </div>
          )}
          {showOOD && q.trim() && (
            <div className="cmdk-empty" style={{ textAlign: "left" }}>
              <strong style={{ color: "var(--ink-strong)", display: "block", marginBottom: 6 }}>
                {lang.search.out_of_domain.label}
              </strong>
              {lang.search.out_of_domain.note.replace("{covers}", lang.ui.library_covers)}.{" "}
              <a href="/" onClick={(e) => { e.preventDefault(); go("/"); }}>
                See what this library covers →
              </a>
            </div>
          )}
        </div>
        <div className="cmdk-foot">
          <span><kbd>↑</kbd><kbd>↓</kbd> navigate</span>
          <span><kbd>↵</kbd> open</span>
          <span><kbd>esc</kbd> close</span>
        </div>
      </div>
    </div>
  );
}

export default CommandPalette;

// Keyboard-hint chip in the masthead — the affordance that teaches ⌘K
// exists. Separate export because RSC's client-manifest can't resolve the
// static-property pattern (`Palette.Hint = ...`) reliably across builds.
export function PaletteHint() {
  const [os, setOs] = useState<"mac" | "other">("mac");
  useEffect(() => {
    setOs(/Mac|iPhone|iPad|iPod/.test(navigator.userAgent) ? "mac" : "other");
  }, []);
  return (
    <button
      className="kbd-hint"
      onClick={() => window.dispatchEvent(new Event("researchmap:open-palette"))}
      aria-label="Open command palette"
    >
      Quick search
      <kbd>{os === "mac" ? "⌘" : "Ctrl"}</kbd>
      <kbd>K</kbd>
    </button>
  );
}
