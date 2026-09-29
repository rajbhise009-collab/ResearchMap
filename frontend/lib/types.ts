export type Tier = "high" | "medium" | "low";

// ---- consumer-facing (the only shape the reader's view is built from) ----

export interface PlainCaveat { code: string; label: string; text: string; }

export interface ConsumerCard {
  headline: string;
  headline_is_quoted: boolean;
  kind: string;
  kind_id: string;
  kind_short: string;
  kind_long: string;
  strength: string;
  strength_meaning: string;
  why: string;
  caveats: PlainCaveat[];
  paper_count: number;
}

export interface Fidelity { label: string; text: string; }

export interface ConsumerPaper {
  fidelity: Fidelity;
  claims_label: string;
  limitations_label: string;
  future_work_label: string;
  methods_label: string;
  citations_label: string;
  no_claims: string;
  no_limitations: string;
  no_future_work: string;
  no_methods: string;
}

// ---- pre-flight predictor result ----------------------------------------
// GET /api/preflight?q=… — computed live from free OpenAlex metadata.
// The consumer view is what a public visitor sees; `dev` is the full
// hypothesis-vs-guarantee internals surfaced only under ?dev=1.
// See docs/findings/domain-coherence-predictor.md for the honesty story.

export interface PreflightConsumer {
  headline: string;
  coverage_line: string;
  diagnostic_line: string;
  diagnostic_confidence: string;
  estimate_headline: string;
}

export interface PreflightDev {
  features: {
    n_papers: number;
    intracorpus_reference_rate: number;
    citation_reciprocity: number;
    citation_modularity: number;
    review_ratio: number;
    temporal_churn: number;
    venue_concentration: number;
    term_vector_spread: number;
    median_year: number | null;
    year_span: number | null;
  };
  verdict: {
    contested_score: number;
    contested_band: string;
    method_transfer_score: number;
    method_transfer_band: string;
    caveat: string;
  };
  cost_projection: {
    target_papers: number;
    est_extraction_usd: number;
    est_pair_classification_usd: number;
    est_total_usd: number;
    est_hours: string;
  };
  credit_headers?: Record<string, unknown> | null;
  openalex_filter?: string;
  cache_path?: string;
  top_paper_titles?: (string | null)[];
}

export interface PreflightResult {
  query: string;
  n_openalex_matches: number;
  n_sampled: number;
  consumer: PreflightConsumer;
  dev: PreflightDev;
}

// ---- raw internals (developer mode only) ----

export interface Caveat { code: string; label: string; detail: string; }
export interface SupportingPaper {
  paper_id: string; title: string | null; year: number | null;
  input_source: string; abstract_only: boolean; domain_centrality: string;
}
export interface EvidenceItem {
  kind: string; id: string; paper_id: string | null; text: string | null;
}
export interface Opportunity {
  schema_version: string; id: string; slug: string; rank: number;
  gap_type: string; scorer: string; title: string;
  score: number; confidence: number; confidence_tier: Tier; trust: number;
  confirm_status: string | null;
  component_scores: Record<string, number>;
  explanation: string;
  caveats: Caveat[];
  supporting_papers: SupportingPaper[];
  evidence_trail: EvidenceItem[];
  relationship_ids: string[];
  consumer: ConsumerCard;
}
export interface PaperSummary {
  paper_id: string; wid: string; title: string | null; year: number | null;
  input_source: string; abstract_only: boolean; domain_centrality: string;
  provenance: string | null; doi: string | null;
}
export interface Claim { id: string; text: string; type: string; confidence: number; }
export interface Limitation { id: string; text: string; normalized_category: string; source_scope: string; }
export interface FutureWork { id: string; text: string; addressed_by: string | null; }
export interface Methodology { id: string; name: string; description: string | null; datasets: string[]; conditions: string[]; }
export interface PaperLink { paper_id: string; title: string | null; }
export interface PaperDetail {
  paper_id: string; wid: string; title: string | null; year: number | null; doi: string | null;
  input_source: string; abstract_only: boolean; domain_centrality: string; provenance: string | null;
  abstract: string | null;
  claims: Claim[]; limitations: Limitation[]; future_work: FutureWork[]; methodologies: Methodology[];
  cites: PaperLink[]; cited_by: PaperLink[];
  consumer: ConsumerPaper;
}
export interface Stats {
  papers: number; full_text: number; abstract_only: number; core: number; peripheral: number;
  scorer_yields: Record<string, number>;
  relationships: number; spend_to_date_usd: number; manifest_hash: string | null; note: string;
}
export interface Finding { slug: string; title: string; path: string; markdown: string; }

// ---- the translation layer, shipped from Python ----

export interface Kind { id: string; name: string; short: string; long: string; }

export interface Attribution {
  label: string;
  intro: string;
  items: [string, string, string][];   // [name, url, note]
}

export interface LibraryManifest {
  slug: string;
  name: string;
  short_name: string;
  blurb: string;
  n_papers: number;
  is_default: boolean;
  not_advice_note: string | null;
  snapshot_path: string;         // e.g. "/data" or "/data/library/<slug>"
}

export interface LibrariesManifest {
  libraries: LibraryManifest[];
  default_slug: string;
}

export interface LibraryEntry {
  slug: string;
  name: string;
  n_papers: number;
  note: string;
}

export interface LibrariesNote {
  label: string;
  intro: string;
  items: LibraryEntry[];
}

export interface LanguagePack {
  ui: Record<string, string>;
  dev: Record<string, string>;
  kinds: Record<string, Kind>;
  caveats: Record<string, { label: string; text: string }>;
  confirm_status: Record<string, { label: string; text: string }>;
  strength_meaning: Record<string, string>;
  strength_order: Record<string, number>;
  abstract_only: Fidelity;
  full_text: Fidelity;
  search: {
    placeholder: string;
    hint: string;
    searching: string;
    in_domain: { note: string };
    borderline: { label: string; note: string };
    out_of_domain: { label: string; note: string; what_we_have: string; build_cta: string };
    no_results: { label: string; note: string };
  };
  build_library: {
    title: string; body: string; estimate_label: string;
    estimates: [string, string][]; not_yet: string;
  };
  no_disagreements: { headline: string; body: string; link_label: string };
  attribution: Attribution;
  libraries_note: LibrariesNote;
}

// ---- lightweight payloads handed to client components ----
// Evidence trails stay on the server side of the build: they belong on the
// detail page, not in every list page's JavaScript.

export interface GapDoc {
  slug: string;
  consumer: ConsumerCard;
  dev: Record<string, unknown>;
}
export interface PaperDoc {
  wid: string;
  title: string;
  year: number | null;
  abstract_only: boolean;
  domain_centrality: string;
  input_source: string;
  dev: Record<string, unknown>;
}

// ---- search ----

export interface IndexDoc {
  type: "opportunity" | "paper";
  ref: string; title: string; kind: string; strength: string;
  terms: Record<string, number>;
}
export interface SearchIndex {
  n_docs: number; max_idf: number;
  idf: Record<string, number>;
  docs: IndexDoc[];
  synonyms: Record<string, string[]>;
  stopwords: string[];
}
export interface SearchHit {
  type: "opportunity" | "paper";
  ref: string; title: string; kind: string; strength: string;
  score: number; matched: string[];
}
export interface SearchResult {
  verdict: "in_domain" | "borderline" | "out_of_domain" | "empty";
  coverage: number; best: number; breadth: number; n_matched: number;
  hits: SearchHit[];
  known: string[]; unknown: string[]; expanded: string[];
}
