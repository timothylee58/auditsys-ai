import type { DocumentRecord } from "@/types/audit";

export function DocumentTable({ documents }: { documents: DocumentRecord[] }) {
  return (
    <div className="overflow-hidden rounded-md border border-line">
      <table className="w-full border-collapse text-left text-sm">
        <thead className="bg-white/5 text-xs uppercase tracking-[0.18em] text-zinc-400">
          <tr>
            <th className="px-4 py-3">Document</th>
            <th className="px-4 py-3">Status</th>
            <th className="px-4 py-3">Risk</th>
            <th className="px-4 py-3">Uploaded</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-line">
          {documents.map((document) => (
            <tr key={document.id} className="bg-panel/50">
              <td className="px-4 py-4 font-medium text-zinc-100">{document.name}</td>
              <td className="px-4 py-4 text-zinc-300">{document.status.replace("_", " ")}</td>
              <td className="px-4 py-4 text-accent">{document.riskScore}</td>
              <td className="px-4 py-4 text-zinc-400">{document.uploadedAt}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
