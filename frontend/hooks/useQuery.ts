"use client";

import { useState } from "react";
import { API_BASE_URL, DEMO_USER_ID } from "@/lib/api";

export interface QueryResult {
  answer: string;
  citations: Array<{ document_id?: string; page_number?: number; similarity?: number }>;
  confidence_score: number;
  trace_id: string;
  status: "answered" | "pending_review" | "rejected";
  session_id: string;
  review_item_id: string | null;
}

export interface QueryStatus {
  status: "answered" | "pending_review" | "rejected";
  answer: string | null;
  review_note: string | null;
}

export function useAuditQuery() {
  const [result, setResult] = useState<QueryResult | null>(null);
  const [pollStatus, setPollStatus] = useState<QueryStatus | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function runQuery(question: string) {
    setIsLoading(true);
    setError(null);
    setPollStatus(null);
    try {
      const res = await fetch(`${API_BASE_URL}/query`, {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-User-ID": DEMO_USER_ID },
        body: JSON.stringify({ question }),
      });
      if (!res.ok && res.status !== 202) throw new Error(`Query failed: ${res.status}`);
      const data = (await res.json()) as QueryResult;
      setResult(data);
      if (data.status === "pending_review") {
        pollForResolution(data.session_id);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unknown error");
    } finally {
      setIsLoading(false);
    }
  }

  function pollForResolution(sessionId: string, attempt = 0) {
    if (attempt > 60) return; // stop after ~5 minutes at 5s intervals
    setTimeout(async () => {
      try {
        const res = await fetch(`${API_BASE_URL}/query/status/${sessionId}`, {
          headers: { "X-User-ID": DEMO_USER_ID },
        });
        if (!res.ok) return;
        const data = (await res.json()) as QueryStatus;
        setPollStatus(data);
        if (data.status === "pending_review") {
          pollForResolution(sessionId, attempt + 1);
        }
      } catch {
        // transient network error — the next scheduled poll will retry
      }
    }, 5000);
  }

  return { result, pollStatus, isLoading, error, runQuery };
}
