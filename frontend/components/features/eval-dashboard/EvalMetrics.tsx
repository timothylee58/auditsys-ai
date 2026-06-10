export function EvalMetrics({ precision = 0, recall = 0 }: { precision?: number; recall?: number }) {
  return (
    <div className="grid gap-4 sm:grid-cols-2">
      <div className="rounded-md border border-line bg-panel p-4">Precision: {precision}%</div>
      <div className="rounded-md border border-line bg-panel p-4">Recall: {recall}%</div>
    </div>
  );
}
