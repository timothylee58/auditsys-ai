export type DocumentRecord = {
  id: string;
  filename: string;
  entity: string | null;
  doc_date: string | null;
  status: "processing" | "indexed" | "failed" | "deleted" | "duplicate";
  page_count: number;
  chunk_count: number;
  created_at: string;
};

export type DocumentPage = {
  documents: DocumentRecord[];
  total: number;
  page: number;
  page_size: number;
  has_next: boolean;
};

export type AuditEvent = {
  id: string;
  session_id: string;
  query: string;
  answer: string | null;
  status: "answered" | "pending_review" | "rejected";
  confidence_score: number | null;
  model_name: string | null;
  prompt_version: string | null;
  pii_detected: boolean;
  created_at: string;
};

export type AuditLogPage = {
  entries: AuditEvent[];
  total: number;
  page: number;
  page_size: number;
  has_next: boolean;
};

export type ReviewItem = {
  id: string;
  session_id: string;
  query: string;
  draft_answer: string;
  confidence_score: number | null;
  citations: Array<{ document_id?: string; page_number?: number; similarity?: number }>;
  status: "pending" | "approved" | "rejected" | "overridden";
  created_at: string;
};

export type ReviewItemPage = {
  items: ReviewItem[];
  total: number;
  page: number;
  page_size: number;
  has_next: boolean;
};
