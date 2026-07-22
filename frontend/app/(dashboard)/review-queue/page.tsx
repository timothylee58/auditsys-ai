"use client";

import { useCallback, useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { ConfidenceBadge } from "@/components/features/query-interface/ConfidenceBadge";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

interface ReviewItem {
  id: string;
  session_id: string;
  user_id: string;
  query: string;
  draft_answer: string;
  citations: Array<{ document_id?: string; content?: string }>;
  confidence_score: number;
  status: string;
  created_at: string;
}

interface ReviewList {
  items: ReviewItem[];
  total: number;
  page: number;
  page_size: number;
  has_next: boolean;
}

export default function ReviewQueuePage() {
  const [data, setData] = useState<ReviewList | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState<string | null>(null);
  const [overrideModal, setOverrideModal] = useState<ReviewItem | null>(null);
  const [overrideAnswer, setOverrideAnswer] = useState("");
  const [overrideNotes, setOverrideNotes] = useState("");
  const [rejectModal, setRejectModal] = useState<ReviewItem | null>(null);
  const [rejectReason, setRejectReason] = useState("");

  const fetchReviews = useCallback(async () => {
    setIsLoading(true);
    try {
      const res = await fetch(`${API_BASE_URL}/review`);
      if (res.ok) setData(await res.json());
    } catch {
      // silent
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchReviews();
  }, [fetchReviews]);

  const handleApprove = async (itemId: string) => {
    setActionLoading(itemId);
    try {
      const res = await fetch(`${API_BASE_URL}/review/${itemId}/approve`, { method: "POST" });
      if (res.ok) await fetchReviews();
    } finally {
      setActionLoading(null);
    }
  };

  const handleReject = async () => {
    if (!rejectModal || rejectReason.length < 5) return;
    setActionLoading(rejectModal.id);
    try {
      const res = await fetch(`${API_BASE_URL}/review/${rejectModal.id}/reject`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ reason: rejectReason }),
      });
      if (res.ok) {
        setRejectModal(null);
        setRejectReason("");
        await fetchReviews();
      }
    } finally {
      setActionLoading(null);
    }
  };

  const handleOverride = async () => {
    if (!overrideModal || overrideAnswer.length < 10) return;
    setActionLoading(overrideModal.id);
    try {
      const res = await fetch(`${API_BASE_URL}/review/${overrideModal.id}/override`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          corrected_answer: overrideAnswer,
          notes: overrideNotes || null,
        }),
      });
      if (res.ok) {
        setOverrideModal(null);
        setOverrideAnswer("");
        setOverrideNotes("");
        await fetchReviews();
      }
    } finally {
      setActionLoading(null);
    }
  };

  return (
    <section>
      <div className="flex items-center justify-between">
        <div>
          <p className="text-xs uppercase tracking-[0.24em] text-accent">Human validation</p>
          <h2 className="mt-2 font-display text-5xl font-bold">Review Queue</h2>
        </div>
        {data && data.total > 0 && (
          <span className="inline-flex h-7 min-w-7 items-center justify-center rounded-full bg-amber-500/20 px-2 text-xs font-bold text-amber-400">
            {data.total}
          </span>
        )}
      </div>

      {isLoading ? (
        <p className="mt-8 text-zinc-500">Loading...</p>
      ) : !data?.items.length ? (
        <div className="mt-8 rounded-md border border-line bg-panel p-8 text-center">
          <p className="text-zinc-400">No items pending review</p>
          <p className="mt-1 text-xs text-zinc-600">
            Items appear here when the AI confidence is below threshold.
          </p>
        </div>
      ) : (
        <div className="mt-8 space-y-4">
          {data.items.map((item) => (
            <article key={item.id} className="rounded-md border border-line bg-panel p-5">
              <div className="flex items-start justify-between">
                <div className="flex-1">
                  <p className="text-xs text-zinc-500">
                    {new Date(item.created_at).toLocaleString()} &middot; {item.user_id}
                  </p>
                  <p className="mt-2 text-sm font-medium text-zinc-100">{item.query}</p>
                </div>
                <ConfidenceBadge score={item.confidence_score} />
              </div>

              <div className="mt-4 rounded-md border border-line/50 bg-ink/50 p-3">
                <p className="text-[10px] uppercase tracking-wider text-zinc-500">Draft Answer</p>
                <p className="mt-1 text-sm leading-6 text-zinc-300">{item.draft_answer}</p>
              </div>

              {item.citations.length > 0 && (
                <div className="mt-3">
                  <p className="text-[10px] uppercase tracking-wider text-zinc-500">
                    Citations ({item.citations.length})
                  </p>
                  <div className="mt-1 flex flex-wrap gap-2">
                    {item.citations.slice(0, 3).map((c, i) => (
                      <span key={i} className="rounded bg-white/5 px-2 py-0.5 text-xs text-zinc-400">
                        {c.document_id?.slice(0, 8) || `Source ${i + 1}`}
                      </span>
                    ))}
                    {item.citations.length > 3 && (
                      <span className="text-xs text-zinc-500">+{item.citations.length - 3} more</span>
                    )}
                  </div>
                </div>
              )}

              <div className="mt-4 flex gap-2">
                <Button
                  onClick={() => handleApprove(item.id)}
                  disabled={actionLoading === item.id}
                >
                  {actionLoading === item.id ? "..." : "Approve"}
                </Button>
                <Button
                  variant="secondary"
                  onClick={() => { setRejectModal(item); setRejectReason(""); }}
                  disabled={actionLoading === item.id}
                >
                  Reject
                </Button>
                <Button
                  variant="secondary"
                  onClick={() => { setOverrideModal(item); setOverrideAnswer(item.draft_answer); setOverrideNotes(""); }}
                  disabled={actionLoading === item.id}
                >
                  Override
                </Button>
              </div>
            </article>
          ))}
        </div>
      )}

      {/* Reject Modal */}
      {rejectModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4">
          <div className="w-full max-w-md rounded-lg border border-line bg-panel p-6">
            <h3 className="text-lg font-semibold text-zinc-100">Reject Review Item</h3>
            <p className="mt-2 text-sm text-zinc-400">Provide a reason for rejecting this answer.</p>
            <textarea
              value={rejectReason}
              onChange={(e) => setRejectReason(e.target.value)}
              className="mt-4 w-full rounded-md border border-line bg-ink p-3 text-sm text-zinc-200 outline-none focus:border-accent"
              rows={3}
              placeholder="Reason for rejection (min 5 characters)..."
            />
            <div className="mt-4 flex justify-end gap-2">
              <Button variant="secondary" onClick={() => setRejectModal(null)}>Cancel</Button>
              <Button onClick={handleReject} disabled={rejectReason.length < 5}>Reject</Button>
            </div>
          </div>
        </div>
      )}

      {/* Override Modal */}
      {overrideModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4">
          <div className="w-full max-w-lg rounded-lg border border-line bg-panel p-6">
            <h3 className="text-lg font-semibold text-zinc-100">Override Answer</h3>
            <p className="mt-2 text-sm text-zinc-400">Provide a corrected answer (min 10 characters).</p>
            <textarea
              value={overrideAnswer}
              onChange={(e) => setOverrideAnswer(e.target.value)}
              className="mt-4 w-full rounded-md border border-line bg-ink p-3 text-sm text-zinc-200 outline-none focus:border-accent"
              rows={5}
              placeholder="Corrected answer..."
            />
            <textarea
              value={overrideNotes}
              onChange={(e) => setOverrideNotes(e.target.value)}
              className="mt-3 w-full rounded-md border border-line bg-ink p-3 text-sm text-zinc-200 outline-none focus:border-accent"
              rows={2}
              placeholder="Notes (optional)..."
            />
            <div className="mt-4 flex justify-end gap-2">
              <Button variant="secondary" onClick={() => setOverrideModal(null)}>Cancel</Button>
              <Button onClick={handleOverride} disabled={overrideAnswer.length < 10}>Save Override</Button>
            </div>
          </div>
        </div>
      )}
    </section>
  );
}
