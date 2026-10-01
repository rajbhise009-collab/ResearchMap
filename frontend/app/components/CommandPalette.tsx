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
import { asset } from "../../lib/basePath";

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

  // Resolve the active library's snapshot path (same ?lib= /
  // localStorage / default_slug sequence as everywhere else) and fetch
  // THAT library's search-index. Without this the palette loads the
  // LLM-cal index even when the user has switched to Diet.
  const [activeSnapshot, setActiveSnapshot] = useState<string>("/data");
  const [activeSlug, setActiveSlug] = useState<string | null>(null);
  useEffect(() => {
    if (!open || index) return;
    let live = true;
    const loadIndex = async () => {
      let snapshotPath = "/data";
      try {
        const r = await fetch(asset("/data/libraries.json"));
        if (r.ok) {
          const m = await r.json();
          const requested = new URLSearchParams(window.location.search).get("lib");
          const remembered = (() => {
            try { return window.localStorage.getItem("researchmap.library"); }
            catch { return null; }
          })();
          const slug = requested || remembered || m.default_slug;
          const lib = (m.libraries || []).find((l: any) => l.slug === slug)
                       || (m.libraries || [])[0];
          if (lib) {
            snapshotPath = lib.snapshot_path;
            if (live) {
              setActiveSnapshot(snapshotPath);
              setActiveSlug(lib.slug);
            }
          }
        }
      } catch {}
      try {
        const rr = await fetch(asset(`${snapshotPath}/search-index.json`));
        if (!rr.ok) return;
        const j: SearchIndex = await rr.json();
        if (live) setIndex(j);
      } catch {}
    };
    loadIndex();
    return () => { live = false; };
  }, [open, index]);

  // Fetch per-library opportunities + papers once the palette opens so
  // the hit→card lookup matches the active library. Falls back to the
  // SSR props if the fetches fail or the library has no file (so
  // legacy single-library deploys keep working).
  const [liveGaps, setLiveGaps] = useState<GapDoc[] | null>(null);
  const [livePapers, setLivePapers] = useState<PaperDoc[] | null>(null);
  useEffect(() => {
    if (!open) return;
    let live = true;
    (async () => {
      try {
        const [oppR, papR] = await Promise.all([
          fetch(asset(`${activeSnapshot}/opportunities.json`)),
          fetch(asset(`${activeSnapshot}/papers.json`)),
        ]);
        if (oppR.ok && live) {
          const oj = await oppR.json();
          setLiveGaps((oj.items || []).map((o: any) => ({
            slug: o.slug, consumer: o.consumer, dev: {},
          }) as unknown as GapDoc));
        }
        if (papR.ok && live) {
          const pj = await papR.json();
          setLivePapers((pj.items || []).map((p: any) => ({
            wid: p.wid, title: p.title ?? p.wid,
            year: p.year, abstract_only: p.abstract_only,
            domain_centrality: p.domain_centrality, dev: {},
          }) as unknown as PaperDoc));
        }
      } catch {}
    })();
    return () => { live = false; };
  }, [open, activeSnapshot]);

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

  // Debounced search-as-you-type. The retrieval uses prefix matching
  // on the last typed token (3-char minimum) so partial typing like
  // "alc" surfaces the alcohol gaps mid-type. The verdict is still
  // computed from COMPLETE tokens only inside search(), so a prefix
  // cannot make an OOD query look in_domain.
  useEffect(() => {
    if (!index) return;
    const trimmed = q.trim();
    if (!trimmed || trimmed.length < 3) {
      setResult(null); setSelected(0); return;
    }
    const t = setTimeout(() => {
      setResult(search(index, q, 12, { prefixLast: true }));
      setSelected(0);
    }, DEBOUNCE_MS);
    return () => clearTimeout(t);
  }, [q, index]);

  const effectiveGaps = liveGaps ?? gaps;
  const effectivePapers = livePapers ?? papers;
  const gapBySlug = useMemo(
    () => new Map(effectiveGaps.map((g) => [g.slug, g])),
    [effectiveGaps]);
  const paperByWid = useMemo(
    () => new Map(effectivePapers.map((p) => [p.wid, p])),
    [effectivePapers]);
  const suffix = activeSlug ? `?lib=${encodeURIComponent(activeSlug)}` : "";

  type Item = { href: string; title: string; kind: string; strength?: string };
  const items: Item[] = useMemo(() => {
    if (!result || result.verdict === "out_of_domain" || result.verdict === "empty") return [];
    const out: Item[] = [];
    for (const h of result.hits) {
      if (h.type === "opportunity") {
        const g = gapBySlug.get(h.ref);
        // Fall back to the hit's own fields when the lookup map doesn't
        // know this slug — see Ask.tsx for the same pattern.
        out.push({
          href: `/gap/${h.ref}/${suffix}`,
          title: g?.consumer.headline_is_quoted
            ? `“${g.consumer.headline}”`
            : (g?.consumer.headline ?? h.title),
          kind: g?.consumer.kind ?? (h.kind || "A result"),
          strength: g?.consumer.strength ?? (h.strength || "Unverified lead"),
        });
      } else {
        const p = paperByWid.get(h.ref);
        out.push({
          href: `/paper/${h.ref}/${suffix}`,
          title: p?.title ?? h.title,
          kind: "Paper",
        });
      }
    }
    return out.slice(0, 10);
  }, [result, gapBySlug, paperByWid, suffix]);

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
