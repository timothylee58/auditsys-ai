import { apiGet } from "@/lib/api";
import type { ReviewItem } from "@/types/audit";

export const dynamic = "force-dynamic";

export default async function ReviewQueuePage() {
  const items = await apiGet<ReviewItem[]>("/review-queue");

  return (
    <section>
      <p className="text-xs uppercase tracking-[0.24em] text-accent">Human validation</p>
      <h2 className="mt-2 font-display text-5xl font-bold">Review Queue</h2>
      <div className="mt-8 grid gap-4 md:grid-cols-2">
        {items.map((item) => (
          <article key={item.id} className="rounded-md border border-line bg-panel p-5">
            <p className="text-xs uppercase tracking-[0.18em] text-accent">{item.severity}</p>
            <h3 className="mt-2 text-xl font-semibold">{item.title}</h3>
            <p className="mt-4 text-sm text-zinc-400">Assigned to {item.assignee}</p>
          </article>
        ))}
      </div>
    </section>
  );
}
