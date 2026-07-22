"use client";

import { useCallback, useEffect, useState } from "react";
import { Button } from "@/components/ui/button";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

interface AuditEntry {
  id: string;
  session_id: string;
  user_id: string;
  query: string;
  answer: string | null;
  confidence_score: number;
  model_name: string;
  prompt_version: string;
  status: string;
  pii_detected: boolean;
  trace_id: string;
  created_at: string;
}

interface AuditPage {
  entries: AuditEntry[];
  total: number;
  page: number;
  page_size: number;
  has_next: boolean;
}

interface Filters {
  status: string;
  date_from: string;
  date_to: string;
  min_confidence: string;
  max_confidence: string;
  pii_only: boolean;
}

export default function AuditLogPage() {
  const [data, setData] = useState<AuditPage | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [page, setPage] = useState(1);
  const [filters, setFilters] = useState<Filters>({
    status: "",
    date_from: "",
    date_to: "",
    min_confidence: "",
    max_confidence: "",
    pii_only: false,
  });

  const fetchAuditLog = useCallback(async () => {
    setIsLoading(true);
    try {
      const params = new URLSearchParams();
      params.set("page", page.toString());
      params.set("page_size", "20");
      if (filters.status) params.set("status", filters.status);
      if (filters.date_from) params.set("date_from", filters.date_from);
      if (filters.date_to) params.set("date_to", filters.date_to);
      if (filters.min_confidence) params.set("min_confidence", filters.min_confidence);
      if (filters.max_confidence) params.set("max_confidence", filters.max_confidence);
      if (filters.pii_only) params.set("pii_only", "true");

      const res = await fetch(`${API_BASE_URL}/audit?${params.toString()}`);
      if (res.ok) {
        setData(await res.json());
      }
    } catch {
      // Error silently
    } finally {
      setIsLoading(false);
    }
  }, [page, filters]);

  useEffect(() => {
    fetchAuditLog();
  }, [fetchAuditLog]);

  const exportCSV = () => {
    if (!data?.entries.length) return;
    const headers = [
      "Timestamp",
      "Query",
      "Status",
      "Confidence",
      "Model",
      "Prompt Version",
      "PII Detected",
      "Trace ID",
    ];
    const rows = data.entries.map((e) => [
      e.created_at,
      `"${e.query.replace(/"/g, '""')}"`,
      e.status,
      e.confidence_score.toFixed(2),
      e.model_name,
      e.prompt_version,
      e.pii_detected ? "Yes" : "No",
      e.trace_id,
    ]);
    const csv = [headers.join(","), ...rows.map((r) => r.join(","))].join("\n");
    const blob = new Blob([csv], { type: "text/csv" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `audit-log-${new Date().toISOString().slice(0, 10)}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const statusColor = (status: string) => {
    switch (status) {
      case "answered":
        return "bg-emerald-500/20 text-emerald-400";
      case "pending_review":
        return "bg-amber-500/20 text-amber-400";
      case "rejected":
        return "bg-red-500/20 text-red-400";
      default:
        return "bg-zinc-500/20 text-zinc-400";
    }
  };

  return (
    <section>
      <div className="flex items-center justify-between">
        <div>
          <p className="text-xs uppercase tracking-[0.24em] text-accent">Chain of custody</p>
          <h2 className="mt-2 font-display text-5xl font-bold">Audit Log</h2>
        </div>
        <Button variant="secondary" onClick={exportCSV} disabled={!data?.entries.length}>
          Export CSV
        </Button>
      </div>

      {/* Filters */}
      <div className="mt-6 flex flex-wrap gap-3 rounded-md border border-line bg-panel p-4">
        <select
          value={filters.status}
          onChange={(e) => { setFilters((f) => ({ ...f, status: e.target.value })); setPage(1); }}
          className="rounded-md border border-line bg-ink px-3 py-1.5 text-sm text-zinc-200"
        >
          <option value="">All statuses</option>
          <option value="answered">Answered</option>
          <option value="pending_review">Pending Review</option>
          <option value="rejected">Rejected</option>
        </select>

        <input
          type="date"
          value={filters.date_from}
          onChange={(e) => { setFilters((f) => ({ ...f, date_from: e.target.value })); setPage(1); }}
          className="rounded-md border border-line bg-ink px-3 py-1.5 text-sm text-zinc-200"
          placeholder="From date"
        />
        <input
          type="date"
          value={filters.date_to}
          onChange={(e) => { setFilters((f) => ({ ...f, date_to: e.target.value })); setPage(1); }}
          className="rounded-md border border-line bg-ink px-3 py-1.5 text-sm text-zinc-200"
          placeholder="To date"
        />

        <div className="flex items-center gap-2">
          <label className="text-xs text-zinc-400">Confidence:</label>
          <input
            type="range"
            min="0"
            max="100"
            value={(parseFloat(filters.min_confidence) || 0) * 100}
            onChange={(e) => {
              setFilters((f) => ({ ...f, min_confidence: (parseInt(e.target.value) / 100).toString() }));
              setPage(1);
            }}
            className="h-1 w-24 accent-accent"
          />
          <span className="text-xs text-zinc-500">
            {Math.round((parseFloat(filters.min_confidence) || 0) * 100)}%+
          </span>
        </div>

        <label className="flex items-center gap-2 text-xs text-zinc-400">
          <input
            type="checkbox"
            checked={filters.pii_only}
            onChange={(e) => { setFilters((f) => ({ ...f, pii_only: e.target.checked })); setPage(1); }}
            className="rounded accent-accent"
          />
          PII only
        </label>
      </div>

      {/* Table */}
      <div className="mt-6 overflow-x-auto rounded-md border border-line">
        <table className="w-full text-sm">
          <thead className="border-b border-line bg-panel/60">
            <tr>
              <th className="px-4 py-3 text-left text-xs font-medium text-zinc-400">Timestamp</th>
              <th className="px-4 py-3 text-left text-xs font-medium text-zinc-400">Query</th>
              <th className="px-4 py-3 text-left text-xs font-medium text-zinc-400">Status</th>
              <th className="px-4 py-3 text-left text-xs font-medium text-zinc-400">Confidence</th>
              <th className="px-4 py-3 text-left text-xs font-medium text-zinc-400">Model</th>
              <th className="px-4 py-3 text-left text-xs font-medium text-zinc-400">Prompt</th>
              <th className="px-4 py-3 text-left text-xs font-medium text-zinc-400">PII</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-line">
            {isLoading ? (
              <tr>
                <td colSpan={7} className="px-4 py-8 text-center text-zinc-500">Loading...</td>
              </tr>
            ) : !data?.entries.length ? (
              <tr>
                <td colSpan={7} className="px-4 py-8 text-center text-zinc-500">No entries found</td>
              </tr>
            ) : (
              data.entries.map((entry) => (
                <tr key={entry.id} className="hover:bg-white/2">
                  <td className="whitespace-nowrap px-4 py-3 text-xs text-zinc-400">
                    {new Date(entry.created_at).toLocaleString()}
                  </td>
                  <td className="max-w-[200px] truncate px-4 py-3 text-zinc-200" title={entry.query}>
                    {entry.query.length > 50 ? `${entry.query.slice(0, 50)}...` : entry.query}
                  </td>
                  <td className="px-4 py-3">
                    <span className={`inline-block rounded-full px-2 py-0.5 text-xs font-medium ${statusColor(entry.status)}`}>
                      {entry.status}
                    </span>
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-2">
                      <div className="h-1.5 w-16 overflow-hidden rounded-full bg-zinc-700">
                        <div
                          className={`h-full rounded-full ${
                            entry.confidence_score >= 0.85
                              ? "bg-emerald-400"
                              : entry.confidence_score >= 0.75
                                ? "bg-amber-400"
                                : "bg-red-400"
                          }`}
                          style={{ width: `${entry.confidence_score * 100}%` }}
                        />
                      </div>
                      <span className="text-xs text-zinc-500">{Math.round(entry.confidence_score * 100)}%</span>
                    </div>
                  </td>
                  <td className="px-4 py-3 text-xs text-zinc-400">{entry.model_name}</td>
                  <td className="px-4 py-3 text-xs text-zinc-400">{entry.prompt_version}</td>
                  <td className="px-4 py-3">
                    {entry.pii_detected && (
                      <span className="inline-block rounded bg-red-500/20 px-1.5 py-0.5 text-[10px] font-medium text-red-400">
                        PII
                      </span>
                    )}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {/* Pagination */}
      {data && data.total > 0 && (
        <div className="mt-4 flex items-center justify-between text-sm text-zinc-400">
          <span>
            Showing {(page - 1) * 20 + 1}–{Math.min(page * 20, data.total)} of {data.total}
          </span>
          <div className="flex gap-2">
            <Button variant="secondary" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>
              Previous
            </Button>
            <Button variant="secondary" disabled={!data.has_next} onClick={() => setPage((p) => p + 1)}>
              Next
            </Button>
          </div>
        </div>
      )}
    </section>
  );
}
