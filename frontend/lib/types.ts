export type Tier = "high" | "medium" | "low";

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
}
export interface Stats {
  papers: number; full_text: number; abstract_only: number; core: number; peripheral: number;
  scorer_yields: Record<string, number>;
  relationships: number; spend_to_date_usd: number; manifest_hash: string | null; note: string;
}
export interface Finding { slug: string; title: string; path: string; markdown: string; }
