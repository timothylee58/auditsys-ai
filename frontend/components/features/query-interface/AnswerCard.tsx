export function AnswerCard({ answer }: { answer: string }) {
  return (
    <article className="rounded-md border border-line bg-panel p-5">
      <p className="text-sm leading-6 text-zinc-200">{answer}</p>
    </article>
  );
}
