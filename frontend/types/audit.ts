export type DocumentRecord = {
  id: string;
  name: string;
  status: "indexed" | "processing" | "needs_review" | "deleted";
  uploadedAt: string;
  riskScore: number;
};

export type AuditEvent = {
  id: string;
  actor: string;
  action: string;
  target: string;
  createdAt: string;
};

export type ReviewItem = {
  id: string;
  title: string;
  severity: "critical" | "high" | "medium" | "low";
  assignee: string;
};

export type AuditLogEntry = {
  id: string;
  session_id: string;
  user_id: string;
  query: string;
  answer: string | null;
  citations: Array<Record<string, unknown>>;
  confidence_score: number;
  prompt_version: string;
  model_name: string;
  trace_id: string;
  status: string;
  review_item_id: string | null;
  pii_detected: boolean;
  validation_passed: boolean;
  validation_errors: string[];
  created_at: string;
};

export type ReviewQueueItem = {
  id: string;
  session_id: string;
  user_id: string;
  query: string;
  draft_answer: string;
  citations: Array<Record<string, unknown>>;
  confidence_score: number;
  status: string;
  reviewer_id: string | null;
  reviewed_at: string | null;
  reviewer_action: "approve" | "reject" | "override" | null;
  override_answer: string | null;
  reviewer_notes: string | null;
  created_at: string;
};

export type EvalResult = {
  id: string;
  status: string;
  started_at: string;
  completed_at: string | null;
  metrics: Record<string, number>;
};
