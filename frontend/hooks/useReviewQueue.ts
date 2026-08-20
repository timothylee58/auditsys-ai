"use client";

import { useCallback, useEffect, useState } from "react";
import { apiGet, apiPost } from "@/lib/api";
import type { ReviewItem, ReviewItemPage } from "@/types/audit";

export function useReviewQueue() {
  const [items, setItems] = useState<ReviewItem[]>([]);
  const [isLoading, setIsLoading] = useState(true);

  const refresh = useCallback(async () => {
    setIsLoading(true);
    try {
      const page = await apiGet<ReviewItemPage>("/review-queue?status=pending");
      setItems(page.items);
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  async function approve(id: string) {
    await apiPost(`/review-queue/${id}/approve`);
    setItems((prev) => prev.filter((item) => item.id !== id));
  }

  async function reject(id: string, reason: string) {
    await apiPost(`/review-queue/${id}/reject`, { reason });
    setItems((prev) => prev.filter((item) => item.id !== id));
  }

  async function override(id: string, correctedAnswer: string, notes?: string) {
    await apiPost(`/review-queue/${id}/override`, { corrected_answer: correctedAnswer, notes });
    setItems((prev) => prev.filter((item) => item.id !== id));
  }

  return { items, isLoading, refresh, approve, reject, override };
}
