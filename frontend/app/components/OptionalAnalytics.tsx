"use client";
// Page-view analytics via @vercel/analytics — ONLY loaded when the
// build is not the developer build (ENABLE_DEV=1 baked in as
// NEXT_PUBLIC_ENABLE_DEV="1"). Also skipped when ?dev=1 is on the URL.
//
// Vercel Hobby plan does NOT support custom events; this file loads
// nothing beyond page views. No search-query logging is wired up.
// If a future upgrade to Pro is decided, the refused-query scrubber
// in lib/analytics-scrub.ts is ready — but it will remain unwired
// until that decision is documented.

import { useEffect, useState } from "react";
import dynamic from "next/dynamic";

const DEV_ENABLED = process.env.NEXT_PUBLIC_ENABLE_DEV === "1";

// Load the Analytics component only if we're not in a dev build. Even
// then, we skip it when ?dev=1 is on the URL so a Raj-visited page
// doesn't feed the aggregate numbers with maintainer traffic.
const Analytics = dynamic(
  () => import("@vercel/analytics/react").then((m) => m.Analytics),
  { ssr: false }
);

export default function OptionalAnalytics() {
  const [enabled, setEnabled] = useState(false);
  useEffect(() => {
    if (DEV_ENABLED) return;
    const dev = new URLSearchParams(window.location.search).get("dev");
    if (dev === "1") return;
    setEnabled(true);
  }, []);
  if (!enabled) return null;
  return <Analytics />;
}
