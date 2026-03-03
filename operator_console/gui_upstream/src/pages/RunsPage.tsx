import { useEffect, useState, useCallback } from "react";
import { DataTable } from "@/components/DataTable";
import { StatusBadge } from "@/components/StatusBadge";
import { ErrorAlert } from "@/components/ErrorAlert";
import { JsonViewer } from "@/components/JsonViewer";
import { getRuns } from "@/lib/api/endpoints";
import type { Run, PaginatedResponse } from "@/types/api";
import { X } from "lucide-react";

export default function RunsPage() {
  const [data, setData] = useState<PaginatedResponse<Run> | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [sortKey, setSortKey] = useState("timestamp");
  const [sortOrder, setSortOrder] = useState<"asc" | "desc">("desc");
  const [selectedRun, setSelectedRun] = useState<Run | null>(null);
  const [page, setPage] = useState(1);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await getRuns({ page, page_size: 25, sort: sortKey, order: sortOrder });
      setData(res.data);
    } catch (err: any) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [page, sortKey, sortOrder]);

  useEffect(() => { load(); }, [load]);

  const handleSort = (key: string) => {
    if (sortKey === key) setSortOrder(o => o === "asc" ? "desc" : "asc");
    else { setSortKey(key); setSortOrder("desc"); }
  };

  const columns = [
    { key: "run_id", header: "Run ID", sortable: true, className: "font-mono text-xs", render: (r: Run) => r.run_id.slice(0, 12) + "…" },
    { key: "timestamp", header: "Timestamp", sortable: true, render: (r: Run) => new Date(r.timestamp).toLocaleString() },
    { key: "files_processed", header: "Files", sortable: true, className: "font-mono" },
    { key: "duplicates_found", header: "Dupes", sortable: true, className: "font-mono" },
    { key: "runtime_ms", header: "Runtime", sortable: true, render: (r: Run) => `${r.runtime_ms}ms`, className: "font-mono" },
    {
      key: "regression", header: "Regression", sortable: true,
      render: (r: Run) => <StatusBadge label={r.regression} severity={r.regression === "PASS" ? "success" : r.regression === "FAIL" ? "destructive" : "caution"} dot />,
    },
  ];

  return (
    <div className="p-6 space-y-6 flex gap-6">
      <div className="flex-1 min-w-0 space-y-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Runs</h1>
          <p className="text-sm text-muted-foreground mt-1">Pipeline execution history</p>
        </div>
        {error && <ErrorAlert message={error} onDismiss={() => setError(null)} />}
        <DataTable
          columns={columns}
          data={data?.items ?? []}
          loading={loading}
          emptyMessage="No runs recorded yet"
          onRowClick={setSelectedRun}
          sortKey={sortKey}
          sortOrder={sortOrder}
          onSort={handleSort}
        />
        {data && data.total_pages > 1 && (
          <div className="flex items-center justify-center gap-2">
            <button onClick={() => setPage(p => Math.max(1, p - 1))} disabled={page === 1} className="px-3 py-1 text-sm rounded border disabled:opacity-50">Prev</button>
            <span className="text-xs text-muted-foreground">Page {page} of {data.total_pages}</span>
            <button onClick={() => setPage(p => Math.min(data.total_pages, p + 1))} disabled={page === data.total_pages} className="px-3 py-1 text-sm rounded border disabled:opacity-50">Next</button>
          </div>
        )}
      </div>

      {selectedRun && (
        <div className="w-96 shrink-0 rounded-lg border bg-card p-5 space-y-4 animate-slide-in-right self-start sticky top-0">
          <div className="flex items-center justify-between">
            <h3 className="font-semibold text-sm">Run Details</h3>
            <button onClick={() => setSelectedRun(null)}><X className="h-4 w-4 text-muted-foreground hover:text-foreground" /></button>
          </div>
          <div className="space-y-2 text-sm">
            <div><span className="text-muted-foreground">ID:</span> <span className="font-mono text-xs">{selectedRun.run_id}</span></div>
            <div><span className="text-muted-foreground">Time:</span> {new Date(selectedRun.timestamp).toLocaleString()}</div>
            <div><span className="text-muted-foreground">Files:</span> {selectedRun.files_processed}</div>
            <div><span className="text-muted-foreground">Duplicates:</span> {selectedRun.duplicates_found}</div>
            <div><span className="text-muted-foreground">Runtime:</span> {selectedRun.runtime_ms}ms</div>
            <StatusBadge label={selectedRun.regression} severity={selectedRun.regression === "PASS" ? "success" : selectedRun.regression === "FAIL" ? "destructive" : "caution"} dot />
          </div>
          {selectedRun.details && <JsonViewer data={selectedRun.details} title="Run Metadata" />}
        </div>
      )}
    </div>
  );
}
