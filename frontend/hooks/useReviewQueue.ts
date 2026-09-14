"use client";

import { useCallback, useEffect, useState } from "react";
import { apiGet, apiPost, DEMO_USER_ID } from "@/lib/api";
import type { ReviewItem, ReviewItemPage } from "@/types/audit";

// review-queue's contract identifies the caller via a `reviewer_user_id`
// query param rather than the X-User-ID header apiGet/apiPost already send
// (see lib/api.ts's TODO on DEMO_USER_ID) — append it explicitly here.
const REVIEWER_QS = `reviewer_user_id=${encodeURIComponent(DEMO_USER_ID)}`;

export function useReviewQueue() {
  const [items, setItems] = useState<ReviewItem[]>([]);
  const [isLoading, setIsLoading] = useState(true);

  const refresh = useCallback(async () => {
    setIsLoading(true);
    try {
      const page = await apiGet<ReviewItemPage>(`/review-queue?status=pending&${REVIEWER_QS}`);
      setItems(page.items);
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  async function approve(id: string) {
    await apiPost(`/review-queue/${id}/approve?${REVIEWER_QS}`);
    setItems((prev) => prev.filter((item) => item.id !== id));
  }

  async function reject(id: string, reason: string) {
    await apiPost(`/review-queue/${id}/reject?${REVIEWER_QS}`, { reason });
    setItems((prev) => prev.filter((item) => item.id !== id));
  }

  async function override(id: string, correctedAnswer: string, notes?: string) {
    await apiPost(`/review-queue/${id}/override?${REVIEWER_QS}`, {
      corrected_answer: correctedAnswer,
      notes,
    });
    setItems((prev) => prev.filter((item) => item.id !== id));
  }

  return { items, isLoading, refresh, approve, reject, override };
}
