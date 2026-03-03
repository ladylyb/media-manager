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
  const [sortKey, setSortKey] = useState("started_at");
  const [sortOrder, setSortOrder] = useState<"asc" | "desc">("desc");
  const [selectedRun, setSelectedRun] = useState<Run | null>(null);
  const [page, setPage] = useState(1);
  const pageSize = 25;

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await getRuns({ limit: 200 });
      setData(res.data);
    } catch (err: any) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const handleSort = (key: string) => {
    if (sortKey === key) setSortOrder(o => o === "asc" ? "desc" : "asc");
    else { setSortKey(key); setSortOrder("desc"); }
  };

  const columns = [
    { key: "operation_run_id", header: "Operation Run ID", sortable: true, className: "font-mono text-xs", render: (r: Run) => r.operation_run_id.slice(0, 12) + "…" },
    { key: "operation_type", header: "Type", sortable: true },
    { key: "status", header: "Status", sortable: true },
    { key: "started_at", header: "Started", sortable: true, render: (r: Run) => new Date(r.started_at).toLocaleString() },
    { key: "duration_ms", header: "Duration", sortable: true, render: (r: Run) => r.duration_ms == null ? "--" : `${r.duration_ms.toFixed(1)}ms`, className: "font-mono" },
    {
      key: "status", header: "Run Status", sortable: true,
      render: (r: Run) => <StatusBadge label={r.status} severity={r.status === "COMPLETED" ? "success" : r.status === "FAILED" ? "destructive" : "caution"} dot />,
    },
  ];
  const sorted = [...(data?.items ?? [])].sort((a, b) => {
    const aVal = (a as Record<string, unknown>)[sortKey];
    const bVal = (b as Record<string, unknown>)[sortKey];
    if (aVal === bVal) return 0;
    const order = sortOrder === "asc" ? 1 : -1;
    return aVal && bVal && aVal > bVal ? order : -order;
  });
  const totalPages = Math.max(1, Math.ceil(sorted.length / pageSize));
  const pagedItems = sorted.slice((page - 1) * pageSize, page * pageSize);

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
          data={pagedItems}
          loading={loading}
          emptyMessage="No runs recorded yet"
          onRowClick={setSelectedRun}
          sortKey={sortKey}
          sortOrder={sortOrder}
          onSort={handleSort}
        />
        {data && totalPages > 1 && (
          <div className="flex items-center justify-center gap-2">
            <button onClick={() => setPage(p => Math.max(1, p - 1))} disabled={page === 1} className="px-3 py-1 text-sm rounded border disabled:opacity-50">Prev</button>
            <span className="text-xs text-muted-foreground">Page {page} of {totalPages}</span>
            <button onClick={() => setPage(p => Math.min(totalPages, p + 1))} disabled={page === totalPages} className="px-3 py-1 text-sm rounded border disabled:opacity-50">Next</button>
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
            <div><span className="text-muted-foreground">Operation Run ID:</span> <span className="font-mono text-xs">{selectedRun.operation_run_id}</span></div>
            <div><span className="text-muted-foreground">Type:</span> {selectedRun.operation_type}</div>
            <div><span className="text-muted-foreground">Status:</span> {selectedRun.status}</div>
            <div><span className="text-muted-foreground">Started:</span> {new Date(selectedRun.started_at).toLocaleString()}</div>
            <div><span className="text-muted-foreground">Completed:</span> {selectedRun.completed_at ? new Date(selectedRun.completed_at).toLocaleString() : "--"}</div>
            <div><span className="text-muted-foreground">Duration:</span> {selectedRun.duration_ms == null ? "--" : `${selectedRun.duration_ms.toFixed(1)}ms`}</div>
            <div><span className="text-muted-foreground">Linked Run ID:</span> <span className="font-mono text-xs">{selectedRun.linked_run_id ?? "--"}</span></div>
            <StatusBadge label={selectedRun.status} severity={selectedRun.status === "COMPLETED" ? "success" : selectedRun.status === "FAILED" ? "destructive" : "caution"} dot />
          </div>
          {(selectedRun.context || selectedRun.details) && <JsonViewer data={selectedRun.context ?? selectedRun.details ?? {}} title="Run Metadata" />}
        </div>
      )}
    </div>
  );
}
