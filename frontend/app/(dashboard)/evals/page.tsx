const metrics = [
  { label: "Citation precision", value: "92%" },
  { label: "Reviewer agreement", value: "87%" },
  { label: "Open exceptions", value: "14" }
];

export default function EvalsPage() {
  return (
    <section>
      <p className="text-xs uppercase tracking-[0.24em] text-accent">Quality gates</p>
      <h2 className="mt-2 font-display text-5xl font-bold">Evaluation Dashboard</h2>
      <div className="mt-8 grid gap-4 md:grid-cols-3">
        {metrics.map((metric) => (
          <article key={metric.label} className="rounded-md border border-line bg-panel p-6">
            <p className="text-sm text-zinc-400">{metric.label}</p>
            <p className="mt-3 font-display text-5xl font-bold text-accent">{metric.value}</p>
          </article>
        ))}
      </div>
    </section>
  );
}
