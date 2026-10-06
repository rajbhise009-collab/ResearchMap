// Contact wording for every configuration state. Pure (no imports) so it
// can be tested without a frontend test runner. Never invents an address:
// only what site.config.json provides is shown.
export interface ContactConfig {
  contactEmail: string;
  repoUrl: string;
  repoIsPublic: boolean;
}

export interface ContactLine { lead: string; href: string; label: string; }

export interface ContactContent {
  lines: ContactLine[];
  /** Shown instead of lines when no contact route is configured. */
  none: string | null;
}

export function contactContent(c: ContactConfig): ContactContent {
  const email = (c.contactEmail || "").trim();
  const issues = c.repoIsPublic && (c.repoUrl || "").trim()
    ? `${c.repoUrl.trim().replace(/\/+$/, "")}/issues` : "";
  const issuesLabel = issues.replace(/^https?:\/\//, "");
  const lines: ContactLine[] = [];
  if (email) lines.push({ lead: "Email:", href: `mailto:${email}`, label: email });
  if (issues) {
    lines.push({
      lead: email ? "You can also open an issue on GitHub:" : "Open an issue on GitHub:",
      href: issues, label: issuesLabel,
    });
  }
  return {
    lines,
    none: lines.length ? null
      : "There is no way to contact the project through this site yet.",
  };
}
