import type { ReviewItem } from "@/types/audit";

export function ReviewCard({ item }: { item: ReviewItem }) {
  return (
    <article className="rounded-md border border-line bg-panel p-5">
      <p className="text-xs uppercase tracking-[0.18em] text-accent">{item.severity}</p>
      <h3 className="mt-2 text-lg font-semibold">{item.title}</h3>
      <p className="mt-3 text-sm text-zinc-400">{item.assignee}</p>
    </article>
  );
}
