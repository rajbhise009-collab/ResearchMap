# Security audit — dependency posture

**Updated 2026-09-30.**

## Current pins

| dep | pin | why |
|:--|:--|:--|
| `next` | `^14.2.35` | latest 14.2.x patched release (14.2.28 → 14.2.35 in this run) |
| `postcss` | `^8.5.22` (via npm `overrides`) | patches [GHSA-qx2v-qp2m-jg93] XSS and 3 sourceMappingURL advisories in the postcss transitive |

## What `npm audit` reports now

```
info 0  low 0  moderate 0  high 0  critical 1
```

The single remaining critical is a **rollup of Next.js advisories** all listed
against the range `9.5.0 – 15.5.23`. Every advisory in the rollup targets a
Next runtime feature we do not use in production:

- **Image Optimizer** — we set `images.unoptimized: true` in `next.config.mjs`.
- **HTTP request smuggling in rewrites** — no rewrites configured.
- **Middleware / Proxy** — no middleware.
- **Server Components / Server Actions DoS + SSRF** — we run **`output: "export"`**;
  there is no Next server in production. The deployed artifact is plain HTML +
  CSS + JS on Vercel static hosting.
- **App Router CSP nonces XSS** — we do not set CSP nonces.
- **beforeInteractive scripts XSS** — no `<Script strategy="beforeInteractive">` in
  the codebase.

Closing the rollup would require moving to Next 16, which npm audit flags as
`--force` (breaking). The upgrade would also require a router migration that is
not justified for a static-export site that doesn't run any of the vulnerable
server code paths.

Kept on `14.2.35` deliberately. Reviewed at each npm audit run; if any
advisory that affects `output: "export"` mode appears, revisit.

## Non-breaking upgrades applied in this run

- `next` 14.2.15 → 14.2.35 (patch bump within the 14.2 line).
- `postcss` 8.4.31 → 8.5.28 via npm `overrides`. Closes:
  - GHSA-qx2v-qp2m-jg93 (XSS via unescaped `</style>`)
  - GHSA-6g55-p6wh-862q (sourceMappingURL read)
  - GHSA-fxqj-rqcc-2cmp (incomplete fix of above)
  - GHSA-r28c-9q8g-f849 (path traversal via sourceMappingURL)

No `--force`. Static export, typecheck, and 363-test backend suite all pass.
