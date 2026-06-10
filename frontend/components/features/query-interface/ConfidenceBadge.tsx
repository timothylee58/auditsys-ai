export function ConfidenceBadge({ score }: { score: number }) {
  return (
    <span className="rounded-full border border-line bg-white/5 px-3 py-1 text-xs text-accent">
      {score}% confidence
    </span>
  );
}
