"use client";

import { FormEvent, useCallback, useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { AnswerCard } from "@/components/features/query-interface/AnswerCard";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";
const MAX_QUESTION_LENGTH = 2000;
const POLL_INTERVAL_MS = 5000;

interface QueryResult {
  answer: string;
  citations: Array<{ document_id?: string; chunk_index?: number; content?: string; score?: number }>;
  confidence_score: number;
  trace_id: string;
  status: string;
}

interface PendingResult {
  review_item_id: string;
  message: string;
  session_id: string;
}

type ViewState = "idle" | "loading" | "answered" | "pending_review" | "rejected" | "error";

export default function QueryPage() {
  const [question, setQuestion] = useState("");
  const [viewState, setViewState] = useState<ViewState>("idle");
  const [result, setResult] = useState<QueryResult | null>(null);
  const [pendingInfo, setPendingInfo] = useState<PendingResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [reviewNote, setReviewNote] = useState<string | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const eventSourceRef = useRef<EventSource | null>(null);

  // Cleanup polling/SSE on unmount
  useEffect(() => {
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
      if (eventSourceRef.current) eventSourceRef.current.close();
    };
  }, []);

  const startSSEStream = useCallback((sessionId: string) => {
    const es = new EventSource(`${API_BASE_URL}/query/stream/${sessionId}`);
    eventSourceRef.current = es;

    es.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        if (data.event === "done") {
          es.close();
          return;
        }
        if (data.status === "answered" && data.answer) {
          setResult({
            answer: data.answer,
            citations: [],
            confidence_score: 0,
            trace_id: "",
            status: "answered",
          });
          setViewState("answered");
          es.close();
        } else if (data.status === "rejected") {
          setViewState("rejected");
          setReviewNote(data.review_note || "Your query was rejected by the compliance team.");
          es.close();
        }
      } catch {
        // ignore parse errors
      }
    };

    es.onerror = () => {
      es.close();
      // Fallback to polling
      startPolling(sessionId);
    };
  }, []);

  const startPolling = useCallback((sessionId: string) => {
    pollRef.current = setInterval(async () => {
      try {
        const res = await fetch(`${API_BASE_URL}/query/status/${sessionId}`);
        if (!res.ok) return;
        const data = await res.json();

        if (data.status === "answered" && data.answer) {
          setResult({
            answer: data.answer,
            citations: [],
            confidence_score: 0,
            trace_id: "",
            status: "answered",
          });
          setViewState("answered");
          if (pollRef.current) clearInterval(pollRef.current);
        } else if (data.status === "rejected") {
          setViewState("rejected");
          setReviewNote(data.review_note || "Your query was rejected by the compliance team.");
          if (pollRef.current) clearInterval(pollRef.current);
        }
      } catch {
        // continue polling
      }
    }, POLL_INTERVAL_MS);
  }, []);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (!question.trim() || question.length < 5) return;

    setViewState("loading");
    setError(null);
    setResult(null);
    setPendingInfo(null);
    setReviewNote(null);

    try {
      const res = await fetch(`${API_BASE_URL}/query`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question: question.trim() }),
      });

      if (res.status === 200) {
        const data: QueryResult = await res.json();
        setResult(data);
        setViewState("answered");
      } else if (res.status === 202) {
        const data: PendingResult = await res.json();
        setPendingInfo(data);
        setViewState("pending_review");
        // Start SSE streaming for real-time updates
        startSSEStream(data.session_id);
      } else {
        const errData = await res.json().catch(() => ({ detail: "Unknown error" }));
        setError(errData.detail || `Request failed: ${res.status}`);
        setViewState("error");
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Network error");
      setViewState("error");
    }
  }

  const charCount = question.length;
  const isOverLimit = charCount > MAX_QUESTION_LENGTH;

  return (
    <section>
      <p className="text-xs uppercase tracking-[0.24em] text-accent">Grounded search</p>
      <h2 className="mt-2 font-display text-5xl font-bold">Ask the audit file</h2>

      <form onSubmit={handleSubmit} className="mt-8 rounded-md border border-line bg-panel p-4">
        <div className="flex items-center justify-between">
          <label htmlFor="query" className="text-sm font-medium text-zinc-200">
            Query
          </label>
          <span
            className={`text-xs ${isOverLimit ? "text-red-400" : "text-zinc-500"}`}
          >
            {charCount}/{MAX_QUESTION_LENGTH}
          </span>
        </div>
        <textarea
          id="query"
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          className="mt-3 min-h-40 w-full rounded-md border border-line bg-ink p-4 text-zinc-100 outline-none focus:border-accent"
          placeholder="Find policy exceptions with source evidence..."
          maxLength={MAX_QUESTION_LENGTH}
        />
        <div className="mt-4 flex justify-end">
          <Button
            type="submit"
            disabled={viewState === "loading" || !question.trim() || question.length < 5 || isOverLimit}
          >
            {viewState === "loading" ? "Running..." : "Run query"}
          </Button>
        </div>
      </form>

      {viewState === "error" && error && (
        <p className="mt-4 rounded-md border border-red-800 bg-red-950/40 p-3 text-sm text-red-400">
          {error}
        </p>
      )}

      {viewState === "pending_review" && (
        <div className="mt-6 rounded-md border border-yellow-700 bg-yellow-950/40 p-5">
          <p className="text-sm font-medium text-yellow-300">Pending Compliance Review</p>
          <p className="mt-2 text-sm text-yellow-400/80">
            Your answer is being reviewed by our compliance team. This page will update
            automatically when a decision is made.
          </p>
          <div className="mt-3 flex items-center gap-2">
            <span className="inline-block h-2 w-2 animate-pulse rounded-full bg-yellow-400" />
            <span className="text-xs text-zinc-400">Waiting for review...</span>
          </div>
        </div>
      )}

      {viewState === "rejected" && (
        <div className="mt-6 rounded-md border border-red-700 bg-red-950/40 p-5">
          <p className="text-sm font-medium text-red-300">Query Rejected</p>
          <p className="mt-2 text-sm text-red-400/80">
            {reviewNote || "This query was rejected by the compliance team."}
          </p>
        </div>
      )}

      {viewState === "answered" && result && (
        <div className="mt-6">
          <AnswerCard
            answer={result.answer}
            citations={result.citations}
            confidenceScore={result.confidence_score}
            traceId={result.trace_id}
          />
        </div>
      )}
    </section>
  );
}
