"use client";

import { ReviewCard } from "@/components/features/review-queue/ReviewCard";
import { useReviewQueue } from "@/hooks/useReviewQueue";

export default function ReviewQueuePage() {
  const { items, isLoading, approve, reject, override } = useReviewQueue();

  return (
    <section>
      <p className="text-xs uppercase tracking-[0.24em] text-accent">Human validation</p>
      <h2 className="mt-2 font-display text-5xl font-bold">
        Review Queue{items.length > 0 && <span className="ml-3 text-lg text-accent">({items.length})</span>}
      </h2>
      {isLoading && <p className="mt-8 text-sm text-zinc-500">Loading…</p>}
      {!isLoading && items.length === 0 && (
        <p className="mt-8 rounded-md border border-line bg-panel/50 p-6 text-sm text-zinc-400">
          No answers are pending review.
        </p>
      )}
      <div className="mt-8 grid gap-4 md:grid-cols-2">
        {items.map((item) => (
          <ReviewCard
            key={item.id}
            item={item}
            onApprove={() => approve(item.id)}
            onReject={(reason) => reject(item.id, reason)}
            onOverride={(answer, notes) => override(item.id, answer, notes)}
          />
        ))}
      </div>
    </section>
  );
}
