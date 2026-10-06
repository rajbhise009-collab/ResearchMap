#!/usr/bin/env python3
"""Check a deployed ResearchMap site from the outside. Standard library only.

  python3 tools/live-check.py https://researchmap-one.vercel.app
  python3 tools/live-check.py https://example.org --vercel-host researchmap-one.vercel.app

Checks (FAIL exits non-zero; WARN and SKIP do not):
  - https works (when the base URL is https)
  - the four security headers on / and on a gap page (taken from the sitemap)
  - robots.txt and sitemap.xml are served; their hosts match the base URL;
    production robots.txt does not block everything
  - canonical and og:url hosts match the base URL (on / and the gap page)
  - every og:image URL returns 200
  - the Vercel analytics script (WARN only: it 404s until Web Analytics is
    enabled in the Vercel dashboard)
  - redirects to the base URL, when the host resolves (else SKIP):
    http -> https, www <-> apex, and the *.vercel.app host (--vercel-host)
"""
from __future__ import annotations

import argparse
import re
import socket
import sys
import urllib.error
import urllib.parse
import urllib.request

HEADERS = ["X-Content-Type-Options", "Referrer-Policy", "Permissions-Policy", "X-Frame-Options"]
UA = {"User-Agent": "ResearchMap-live-check/1.0"}
results: list[tuple[str, str, str]] = []


def note(status: str, label: str, detail: str = "") -> None:
    results.append((status, label, detail))
    print(f"{status:<4}  {label}" + (f"  — {detail}" if detail else ""), flush=True)


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None


_noredir = urllib.request.build_opener(_NoRedirect)


def fetch(url: str, follow: bool = True, timeout: float = 20.0):
    """(status, headers, body, final_url); status -1 on network error.
    Redirects (301/302/303/307/308) are followed here, up to 5 hops, so the
    result does not depend on the Python version's urllib."""
    for _ in range(6):
        req = urllib.request.Request(url, headers=UA)
        try:
            r = _noredir.open(req, timeout=timeout)
            return r.status, r.headers, r.read().decode("utf-8", "replace"), r.geturl()
        except urllib.error.HTTPError as e:
            loc = e.headers.get("Location") if e.headers else None
            if follow and e.code in (301, 302, 303, 307, 308) and loc:
                url = urllib.parse.urljoin(url, loc)
                continue
            return e.code, e.headers, "", url
        except Exception as e:  # noqa: BLE001
            return -1, {}, str(e), url
    return -1, {}, "too many redirects", url


def host_of(url: str) -> str:
    return urllib.parse.urlparse(url).netloc.lower()


def resolves(host: str) -> bool:
    try:
        socket.getaddrinfo(host.split(":")[0], None)
        return True
    except OSError:
        return False


def meta(html: str, attr: str, name: str) -> list[str]:
    return re.findall(rf'<meta {attr}="{re.escape(name)}" content="([^"]+)"', html)


def check_page(base: str, path: str, label: str) -> None:
    s, h, body, _ = fetch(base + path)
    if s != 200:
        note("FAIL", f"{label} ({path}) served", f"status {s}")
        return
    missing = [k for k in HEADERS if not (h.get(k) if hasattr(h, "get") else None)]
    note("FAIL" if missing else "PASS", f"{label}: security headers",
         f"missing {missing}" if missing else "; ".join(f"{k}: {h.get(k)}" for k in HEADERS))
    want = host_of(base)
    canon = re.findall(r'<link rel="canonical" href="([^"]+)"', body)
    ogurl = meta(body, "property", "og:url")
    bad = [u for u in canon + ogurl if host_of(u) != want]
    note("FAIL" if (bad or not canon or not ogurl) else "PASS", f"{label}: canonical and og:url host = {want}",
         f"bad={bad} canonical={len(canon)} og:url={len(ogurl)}" if (bad or not canon or not ogurl) else "")
    for img in meta(body, "property", "og:image"):
        si, hi, _, _ = fetch(img)
        ok = si == 200
        note("PASS" if ok else "FAIL", f"{label}: og:image returns 200", f"{img} -> {si}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("base")
    ap.add_argument("--vercel-host", default="researchmap-one.vercel.app",
                    help="the project's *.vercel.app host; '' to skip that redirect check")
    a = ap.parse_args(argv)
    base = a.base.rstrip("/")
    u = urllib.parse.urlparse(base)
    host = u.netloc.lower()
    results.clear()

    s, _, _, _ = fetch(base + "/")
    if u.scheme == "https":
        note("PASS" if s == 200 else "FAIL", "https works", f"GET {base}/ -> {s}")
    else:
        note("SKIP", "https works", "base URL is not https")

    sm_s, _, sm, _ = fetch(base + "/sitemap.xml")
    locs = re.findall(r"<loc>([^<]+)</loc>", sm)
    bad = [l for l in locs if host_of(l) != host]
    note("PASS" if sm_s == 200 and locs and not bad else "FAIL", "sitemap.xml served, hosts match",
         f"status {sm_s}, {len(locs)} URLs, {len(bad)} with another host" + (f" e.g. {bad[0]}" if bad else ""))
    rb_s, _, rb, _ = fetch(base + "/robots.txt")
    sm_lines = re.findall(r"(?im)^sitemap:\s*(\S+)", rb)
    rb_bad = [l for l in sm_lines if host_of(l) != host]
    blocks = bool(re.search(r"(?im)^disallow:\s*/\s*$", rb))
    note("PASS" if rb_s == 200 and not rb_bad else "FAIL", "robots.txt served, sitemap host matches",
         f"status {rb_s}, sitemap lines {sm_lines}")
    note("WARN" if blocks else "PASS", "robots.txt allows indexing",
         "Disallow: / (expected only on non-production builds)" if blocks else "")

    check_page(base, "/", "home")
    gap = next((urllib.parse.urlparse(l).path for l in locs if "/gap/" in l), None)
    if gap:
        check_page(base, gap, "gap page")
    else:
        note("FAIL", "gap page found in sitemap")

    an_s, _, _, _ = fetch(base + "/_vercel/insights/script.js")
    note("PASS" if an_s == 200 else "WARN", "analytics script (/_vercel/insights/script.js)",
         "" if an_s == 200 else f"status {an_s} — enable Web Analytics in the Vercel dashboard")

    def redirect_check(src: str, label: str) -> None:
        h = host_of(src)
        if not resolves(h):
            note("SKIP", label, f"{h} does not resolve")
            return
        st, _, _, final = fetch(src)
        ok = st == 200 and final.rstrip("/").startswith(base)
        note("PASS" if ok else "FAIL", label, f"{src} -> {final} ({st})")

    if u.scheme == "https":
        redirect_check(f"http://{host}/", "http -> https")
    else:
        note("SKIP", "http -> https", "base URL is not https")
    other = host[4:] if host.startswith("www.") else f"www.{host}"
    if re.fullmatch(r"[\d.:]+|localhost(:\d+)?", host) or host.endswith(".vercel.app"):
        note("SKIP", "www <-> apex redirect", f"not applicable to {host}")
    else:
        redirect_check(f"{u.scheme}://{other}/", "www <-> apex redirect")
    if not a.vercel_host:
        note("SKIP", "*.vercel.app redirect", "no --vercel-host given")
    elif a.vercel_host.lower() == host:
        note("SKIP", "*.vercel.app redirect", "the base URL is the vercel.app host")
    else:
        redirect_check(f"https://{a.vercel_host}/", "*.vercel.app -> base URL")

    fails = sum(1 for s_, _, _ in results if s_ == "FAIL")
    print(f"\n{fails} failed, {sum(1 for s_, _, _ in results if s_ == 'PASS')} passed, "
          f"{sum(1 for s_, _, _ in results if s_ == 'WARN')} warnings, "
          f"{sum(1 for s_, _, _ in results if s_ == 'SKIP')} skipped")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
