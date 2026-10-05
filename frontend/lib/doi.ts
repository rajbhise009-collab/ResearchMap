// DOIs arrive in several forms ("10.x/y", "https://doi.org/10.x/y",
// "doi:10.x/y"). Links and exports always use the bare DOI.
export function bareDoi(doi: string | null | undefined): string | null {
  if (!doi) return null;
  const d = doi.trim().replace(/^https?:\/\/(dx\.)?doi\.org\//i, "").replace(/^doi:\s*/i, "");
  return d || null;
}

export function doiUrl(doi: string | null | undefined): string | null {
  const d = bareDoi(doi);
  return d ? `https://doi.org/${d}` : null;
}
