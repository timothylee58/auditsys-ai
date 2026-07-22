"use client";

import { useState } from "react";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

export interface QueryResult {
  answer: string;
  confidence: number;
  confidence_score?: number;
  sources: Array<{ id?: string; name?: string; excerpt?: string; document_id?: string; content?: string }>;
  citations?: Array<{ document_id?: string; content?: string; score?: number }>;
  flagged_for_review: boolean;
  trace_id?: string;
  status?: string;
}

export function useAuditQuery() {
  const [result, setResult] = useState<QueryResult | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function runQuery(question: string) {
    setIsLoading(true);
    setError(null);
    try {
      const res = await fetch(`${API_BASE_URL}/query`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question }),
      });

      if (res.status === 200) {
        const data = await res.json();
        setResult({
          answer: data.answer,
          confidence: data.confidence_score ?? data.confidence ?? 0,
          confidence_score: data.confidence_score,
          sources: data.citations || data.sources || [],
          citations: data.citations,
          flagged_for_review: false,
          trace_id: data.trace_id,
          status: data.status,
        });
      } else if (res.status === 202) {
        const data = await res.json();
        setResult({
          answer: data.message || "Answer pending compliance review",
          confidence: 0,
          sources: [],
          flagged_for_review: true,
          status: "pending_review",
        });
      } else {
        const errData = await res.json().catch(() => null);
        throw new Error(errData?.detail || `Query failed: ${res.status}`);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unknown error");
    } finally {
      setIsLoading(false);
    }
  }

  return { result, isLoading, error, runQuery };
}
