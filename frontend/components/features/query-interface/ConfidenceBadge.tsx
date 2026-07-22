"use client";

interface ConfidenceBadgeProps {
  score: number;
}

/**
 * Visual confidence indicator badge.
 * - Green: >= 0.85 (high confidence)
 * - Amber: 0.75 - 0.85 (acceptable)
 * - Red: < 0.75 (low confidence, likely flagged for review)
 */
export function ConfidenceBadge({ score }: ConfidenceBadgeProps) {
  const percentage = Math.round(score * 100);

  let colorClass: string;
  let label: string;

  if (score >= 0.85) {
    colorClass = "bg-emerald-500/20 text-emerald-400 border-emerald-500/30";
    label = "High";
  } else if (score >= 0.75) {
    colorClass = "bg-amber-500/20 text-amber-400 border-amber-500/30";
    label = "Acceptable";
  } else {
    colorClass = "bg-red-500/20 text-red-400 border-red-500/30";
    label = "Low";
  }

  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs font-medium ${colorClass}`}
      title={`Confidence: ${percentage}% (${label})`}
    >
      <span
        className={`h-1.5 w-1.5 rounded-full ${
          score >= 0.85
            ? "bg-emerald-400"
            : score >= 0.75
              ? "bg-amber-400"
              : "bg-red-400"
        }`}
      />
      {percentage}%
    </span>
  );
}
