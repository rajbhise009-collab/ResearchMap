"use client";
// The command palette is loaded after the page is interactive: nobody needs
// it before they press Cmd+K or tap Quick search, so its code and styles
// (palette.css) stay out of the first paint.
import dynamic from "next/dynamic";
import type { ComponentProps } from "react";
import type CommandPaletteType from "./CommandPalette";

const CommandPalette = dynamic(() => import("./CommandPalette"), { ssr: false });

export default function PaletteLoader(props: ComponentProps<typeof CommandPaletteType>) {
  return <CommandPalette {...props} />;
}
