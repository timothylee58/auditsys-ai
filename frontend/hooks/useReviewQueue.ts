"use client";

import { useCallback, useEffect, useState } from "react";
import { apiGet, apiPost } from "@/lib/api";
import type { ReviewItem, ReviewItemPage } from "@/types/audit";

// The reviewer identity is derived server-side from the authenticated
// session — no reviewer_user_id query param is needed (or accepted).

export function useReviewQueue() {
  const [items, setItems] = useState<ReviewItem[]>([]);
  const [isLoading, setIsLoading] = useState(true);

  const fetchQueue = useCallback(
    () => apiGet<ReviewItemPage>("/review-queue?status=pending"),
    []
  );

  const refresh = useCallback(async () => {
    setIsLoading(true);
    try {
      setItems((await fetchQueue()).items);
    } finally {
      setIsLoading(false);
    }
  }, [fetchQueue]);

  useEffect(() => {
    // Initial load: setState only inside promise callbacks (never
    // synchronously in the effect body) per react-hooks/set-state-in-effect.
    let cancelled = false;
    fetchQueue().then(
      (page) => {
        if (cancelled) return;
        setItems(page.items);
        setIsLoading(false);
      },
      () => {
        if (!cancelled) setIsLoading(false);
      }
    );
    return () => {
      cancelled = true;
    };
  }, [fetchQueue]);

  async function approve(id: string) {
    await apiPost(`/review-queue/${id}/approve`);
    setItems((prev) => prev.filter((item) => item.id !== id));
  }

  async function reject(id: string, reason: string) {
    await apiPost(`/review-queue/${id}/reject`, { reason });
    setItems((prev) => prev.filter((item) => item.id !== id));
  }

  async function override(id: string, correctedAnswer: string, notes?: string) {
    await apiPost(`/review-queue/${id}/override`, {
      corrected_answer: correctedAnswer,
      notes,
    });
    setItems((prev) => prev.filter((item) => item.id !== id));
  }

  return { items, isLoading, refresh, approve, reject, override };
}
