import type { ReviewItem } from "@/types/audit";
import { ReviewActions } from "@/components/features/review-queue/ReviewActions";

export function ReviewCard({
  item,
  onApprove,
  onReject,
  onOverride,
}: {
  item: ReviewItem;
  onApprove: () => Promise<void>;
  onReject: (reason: string) => Promise<void>;
  onOverride: (correctedAnswer: string, notes?: string) => Promise<void>;
}) {
  return (
    <article className="rounded-md border border-line bg-panel p-5">
      <div className="flex items-center justify-between">
        <p className="text-xs uppercase tracking-[0.18em] text-accent">
          Confidence {item.confidence_score !== null ? `${Math.round(item.confidence_score * 100)}%` : "—"}
        </p>
        <span className="text-xs text-zinc-500">{new Date(item.created_at).toLocaleString()}</span>
      </div>
      <h3 className="mt-2 text-lg font-semibold">{item.query}</h3>
      <p className="mt-3 text-sm leading-6 text-zinc-400">{item.draft_answer}</p>
      <div className="mt-4">
        <ReviewActions onApprove={onApprove} onReject={onReject} onOverride={onOverride} />
      </div>
    </article>
  );
}
