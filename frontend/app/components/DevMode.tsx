"use client";
// Developer mode. State lives in React context (so it survives client-side
// navigation) and is mirrored into the URL as ?dev=1 (so it survives a
// reload and can be shared). Deliberately no localStorage, sessionStorage
// or cookies — nothing is written to the browser.

import {
  createContext, useCallback, useContext, useEffect, useState, type ReactNode,
} from "react";

const Ctx = createContext<{ dev: boolean; toggle: () => void }>({
  dev: false,
  toggle: () => {},
});

export function DevModeProvider({ children }: { children: ReactNode }) {
  const [dev, setDev] = useState(false);

  // Seed from the URL once mounted. Reading location during render would
  // break the static prerender, so it happens in an effect.
  useEffect(() => {
    const p = new URLSearchParams(window.location.search).get("dev");
    if (p === "1") setDev(true);
  }, []);

  const toggle = useCallback(() => {
    setDev((prev) => {
      const next = !prev;
      const url = new URL(window.location.href);
      if (next) url.searchParams.set("dev", "1");
      else url.searchParams.delete("dev");
      window.history.replaceState(null, "", url.toString());
      return next;
    });
  }, []);

  return <Ctx.Provider value={{ dev, toggle }}>{children}</Ctx.Provider>;
}

export const useDev = () => useContext(Ctx);

export function DevToggle({ label }: { label: string }) {
  const { dev, toggle } = useDev();
  return (
    <button className="dev-toggle" aria-pressed={dev} onClick={toggle}>
      {label}{dev ? " · on" : ""}
    </button>
  );
}

export function DevBanner({ note }: { note: string }) {
  const { dev } = useDev();
  if (!dev) return null;
  return <div className="dev-banner">{note}</div>;
}

/** A block that only exists when developer mode is on. */
export function Dev({ title, children }: { title?: string; children: ReactNode }) {
  const { dev } = useDev();
  if (!dev) return null;
  return (
    <div className="dev">
      {title && <h4>{title}</h4>}
      {children}
    </div>
  );
}

/** Key/value dump of raw internals. */
export function DevKV({ title, data }: { title: string; data: Record<string, unknown> }) {
  const { dev } = useDev();
  if (!dev) return null;
  const rows = Object.entries(data).filter(([, v]) => v !== undefined && v !== null);
  if (!rows.length) return null;
  return (
    <div className="dev">
      <h4>{title}</h4>
      <div className="kv">
        {rows.map(([k, v]) => (
          <div key={k} style={{ display: "contents" }}>
            <span className="k">{k}</span>
            <span>{typeof v === "object" ? JSON.stringify(v) : String(v)}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

/** The raw JSON behind whatever is on screen. */
export function DevJSON({ title, data }: { title: string; data: unknown }) {
  const { dev } = useDev();
  if (!dev) return null;
  return (
    <div className="dev">
      <h4>{title}</h4>
      <pre>{JSON.stringify(data, null, 2)}</pre>
    </div>
  );
}
