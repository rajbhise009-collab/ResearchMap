# Launching on a custom domain — the manual steps

Everything that can be automated is in the repository. These steps need your
accounts, so only you can do them. Do them in this order.

## 1. Fill in `frontend/site.config.json`

```json
{
  "siteName": "ResearchMap",
  "authorName": "",
  "contactEmail": "",
  "affiliation": "",
  "repoUrl": "https://github.com/rajbhise009-collab/ResearchMap",
  "repoIsPublic": true
}
```

- `contactEmail`: an address you are happy to publish. Empty fields are never
  shown; with an empty email and a public repo, the Contact page links to
  GitHub Issues only.
- `authorName`, `affiliation`: shown on /contact only if filled.
- `repoIsPublic`: keep in step with the repository's real visibility.
- `siteName`: renaming the site is this one line.

Commit and push the change.

## 2. Add the domain in Vercel

1. Vercel → your project → **Settings → Domains → Add**, enter the domain.
2. Vercel shows the exact DNS records to create (an `A` record for the apex
   and/or a `CNAME` for `www`). Copy **exactly those values** into your
   registrar's DNS settings. Do not use values from anywhere else.
3. Wait until Vercel shows the domain as **Valid Configuration**.

## 3. Redirects

In **Settings → Domains**:

1. Choose one canonical host (apex `example.org` or `www.example.org`) and set
   the other to **Redirect** to it (308).
2. Edit the `*.vercel.app` domain and set it to **Redirect** to the canonical
   host, so the preview address does not compete with the real one.

## 4. Set the site URL and redeploy

1. **Settings → Environment Variables → Add**:
   `NEXT_PUBLIC_SITE_URL` = `https://<your canonical host>` (no trailing
   slash), environment **Production** only.
2. **Deployments** → latest production deployment → **⋯ → Redeploy**, and
   **untick "Use existing Build Cache"**. The URL is baked in at build time;
   a cached build keeps the old one.

## 5. Run the launch check

Locally, with the same values Vercel uses:

```bash
cd frontend
NEXT_PUBLIC_SITE_URL=https://<your canonical host> VERCEL_ENV=production npm run build
NEXT_PUBLIC_SITE_URL=https://<your canonical host> npm run launch-check
```

All lines should say PASS. (A normal local build is deliberately non-indexable,
so "built as production" fails without `VERCEL_ENV=production`.)

## 6. Enable Vercel Web Analytics

Project → **Analytics** → **Enable**. The site already loads the page-view
script; nothing else to change. It records page views only (no cookies), as
the /privacy page says.

## 7. Optional: Google Search Console

1. Add the domain property and verify it with the DNS TXT record Google gives.
2. **Sitemaps** → submit `https://<your canonical host>/sitemap.xml`.

## 8. Test share previews

Paste a home, a library and a gap URL into a link-preview checker (for
example the LinkedIn Post Inspector or a Slack/Discord message to yourself).
Each should show the title, description and the 1200×630 image for its
library. Diet previews end "not dietary or medical advice".

## 9. The weekly growth and daily health workflows

`.github/workflows/weekly-grow.yml` adds papers every Monday and publishes
only when every check passes. `.github/workflows/daily-health.yml` checks the
live site every day. Runbook: [OPERATIONS.md](OPERATIONS.md). Neither does
anything useful until you:

1. GitHub → repo **Settings → Secrets and variables → Actions → New
   repository secret**:
   - `GEMINI_API_KEY`: create a **new** key in Google AI Studio / Cloud
     console, restricted to the **Generative Language API**, used only here;
   - `OPENALEX_API_KEY`: your OpenAlex key.
2. Optional, under **Variables**: `NEXT_PUBLIC_SITE_URL` (once you have a
   domain) and `WEEKLY_BUDGET_INR` (default 25).
3. **Actions → Weekly grow → Run workflow** once. The first run only submits
   a batch (nothing to collect yet), so it publishes little; the second run,
   a week later, adds the papers. Read the Issue each run opens.
4. **Actions → Daily health → Run workflow** once to confirm it passes.

To pause growth: **Actions → Weekly grow → ⋯ → Disable workflow**.

## 10. Before advertising

Read `REPORT_launch.md`, in particular the repository-audit section about the
old answer key that GitHub still serves by commit identifier.

## 11. Your remaining manual steps (as of 2026-10-08)

Things only you can do, in a sensible order:

1. **Secrets, then one run:** add `GEMINI_API_KEY` (a NEW key restricted to
   the Generative Language API) and `OPENALEX_API_KEY` as repository secrets,
   then run **Weekly grow** once from the Actions tab (section 9).
2. **Google Cloud budget alert:** Cloud console → Billing → Budgets & alerts
   → create a budget alert on the project that owns the Gemini key, so you
   get an email well before any limit.
3. **Vercel Web Analytics:** enable it (section 6).
4. **Name, domain, site URL and contact email:** decide the name; buy and
   connect the domain (sections 2–5); set `NEXT_PUBLIC_SITE_URL` in Vercel
   and as a GitHub Actions variable; fill `contactEmail` in
   `frontend/site.config.json` (section 1).
5. **Legal review** of `/terms` and `/privacy` by someone qualified.
6. **The expert review** of the libraries' results.

