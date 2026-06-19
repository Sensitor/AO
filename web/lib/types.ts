export interface Project {
  id: string;
  org_id: string;
  name: string;
  buyer_name: string | null;
  status: string;
  deadline: string | null;
  created_at: string;
}

export interface DocumentT {
  id: string;
  project_id: string | null;
  kind: string;
  filename: string;
  content_type: string | null;
  status: string;
  chunk_count: number;
  error: string | null;
  created_at: string;
}

export interface Requirement {
  id: string;
  project_id: string;
  document_id: string | null;
  code: string | null;
  text: string;
  category: string | null;
  obligation: string;
  source_excerpt: string | null;
  status: string;
  created_at: string;
}

export interface ComplianceSource {
  document_id: string;
  filename: string;
  chunk_index: number;
  excerpt: string;
  score: number;
}

export interface ComplianceEntry {
  id: string;
  project_id: string;
  requirement_id: string;
  requirement_text: string | null;
  obligation: string | null;
  verdict: string;
  rationale: string | null;
  sources: ComplianceSource[];
  status: string;
}

export interface Section {
  id: string;
  project_id: string;
  requirement_id: string;
  title: string;
  content: string;
  status: string;
}
