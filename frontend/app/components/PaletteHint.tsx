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
      Quick search
      <kbd>{os === "mac" ? "⌘" : "Ctrl"}</kbd>
      <kbd>K</kbd>
    </button>
  );
}
