export type DocumentRecord = {
  id: string;
  name: string;
  status: "indexed" | "processing" | "needs_review";
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
