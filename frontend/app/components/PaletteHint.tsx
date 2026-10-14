"use client";
import { useEffect, useState } from "react";

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
      onClick={() => {
        // The palette loads lazily; if it is not there yet it opens on arrival.
        (window as Window & { __rmOpenPalette?: boolean }).__rmOpenPalette = true;
        window.dispatchEvent(new Event("researchmap:open-palette"));
      }}
      aria-label="Open command palette"
    >
      <svg className="kbd-hint-icon" width="16" height="16" viewBox="0 0 24 24" fill="none"
           stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" aria-hidden>
        <circle cx="11" cy="11" r="7" /><line x1="16.4" y1="16.4" x2="21" y2="21" />
      </svg>
      <span className="kbd-hint-text">Quick search</span>
      <kbd>{os === "mac" ? "⌘" : "Ctrl"}</kbd>
      <kbd>K</kbd>
    </button>
  );
}
