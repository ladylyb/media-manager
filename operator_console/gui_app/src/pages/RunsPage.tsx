import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { DataTable } from "@/components/DataTable";
import { StatusBadge } from "@/components/StatusBadge";
import { ErrorAlert } from "@/components/ErrorAlert";
import { JsonViewer } from "@/components/JsonViewer";
import { MetricCard } from "@/components/MetricCard";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { getRuns } from "@/lib/api/endpoints";
import { queryKeys } from "@/lib/api/queryKeys";
import { queryOptions } from "@/lib/api/queryOptions";
import type { PaginatedResponse, Run } from "@/types/api";
import { Activity, CheckCircle2, Clock3, X, XCircle } from "lucide-react";

function getErrorMessage(err: unknown): string | null {
  if (!err) return null;
  if (err instanceof Error) return err.message;
  return String(err);
}

export default function RunsPage() {
  const [sortKey, setSortKey] = useState("started_at");
  const [sortOrder, setSortOrder] = useState<"asc" | "desc">("desc");
  const [selectedRun, setSelectedRun] = useState<Run | null>(null);
  const [page, setPage] = useState(1);
  const pageSize = 25;

  const runsQuery = useQuery({
    queryKey: queryKeys.runs(200),
    queryFn: async () => (await getRuns({ limit: 200 })).data,
    staleTime: queryOptions.runs.staleTime,
  });

  const data = (runsQuery.data as PaginatedResponse<Run> | undefined) ?? null;

  const handleSort = (key: string) => {
    if (sortKey === key) setSortOrder(o => (o === "asc" ? "desc" : "asc"));
    else {
      setSortKey(key);
      setSortOrder("desc");
    }
  };

  const columns = [
    {
      key: "operation_run_id",
      header: "Operation Run ID",
      sortable: true,
      className: "font-mono text-xs",
      render: (r: Run) => `${r.operation_run_id.slice(0, 12)}…`,
    },
    { key: "operation_type", header: "Type", sortable: true },
    { key: "status", header: "Status", sortable: true },
    {
      key: "started_at",
      header: "Started",
      sortable: true,
      render: (r: Run) => new Date(r.started_at).toLocaleString(),
    },
    {
      key: "duration_ms",
      header: "Duration",
      sortable: true,
      render: (r: Run) => (r.duration_ms == null ? "--" : `${r.duration_ms.toFixed(1)}ms`),
      className: "font-mono",
    },
    {
      key: "status",
      header: "Run Status",
      sortable: true,
      render: (r: Run) => (
        <StatusBadge
          label={r.status}
          severity={r.status === "COMPLETED" ? "success" : r.status === "FAILED" ? "destructive" : "caution"}
          dot
        />
      ),
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
  const completedRuns = sorted.filter(run => run.status === "COMPLETED").length;
  const failedRuns = sorted.filter(run => run.status === "FAILED").length;
  const activeRuns = sorted.filter(run => run.status === "STARTED").length;

  return (
    <div className="space-y-6 p-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Runs</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Review operation history, compare statuses, and inspect run metadata without leaving the page.
        </p>
      </div>

      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
        <MetricCard title="Loaded Runs" value={sorted.length} subtitle="Client-side review window" icon={<Activity className="h-4 w-4" />} loading={runsQuery.isLoading} />
        <MetricCard title="Completed" value={completedRuns} subtitle="Successful completions" icon={<CheckCircle2 className="h-4 w-4" />} loading={runsQuery.isLoading} />
        <MetricCard title="Failed" value={failedRuns} subtitle="Needs operator review" icon={<XCircle className="h-4 w-4" />} loading={runsQuery.isLoading} />
        <MetricCard title="Active" value={activeRuns} subtitle="Started but not yet complete" icon={<Clock3 className="h-4 w-4" />} loading={runsQuery.isLoading} />
      </div>

      <div className="grid gap-6 xl:grid-cols-[minmax(0,1.7fr)_24rem]">
        <div className="min-w-0 space-y-4">
          <Card>
            <CardHeader className="pb-3">
              <CardDescription>Run History</CardDescription>
              <CardTitle className="text-xl">Recent operation runs</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              {runsQuery.error && <ErrorAlert message={getErrorMessage(runsQuery.error) || "Failed to load runs"} />}
              <div className="flex flex-wrap items-center justify-between gap-3 text-sm text-muted-foreground">
                <span>Sorted by <span className="font-medium text-foreground">{sortKey}</span> in <span className="font-medium text-foreground">{sortOrder}</span> order</span>
                <span>Showing {pagedItems.length} of {sorted.length} loaded runs</span>
              </div>
              <DataTable
                columns={columns}
                data={pagedItems}
                loading={runsQuery.isLoading}
                emptyMessage="No runs recorded yet"
                onRowClick={setSelectedRun}
                sortKey={sortKey}
                sortOrder={sortOrder}
                onSort={handleSort}
              />
              {data && totalPages > 1 && (
                <div className="flex items-center justify-center gap-2">
                  <button
                    onClick={() => setPage(p => Math.max(1, p - 1))}
                    disabled={page === 1}
                    className="rounded border px-3 py-1 text-sm disabled:opacity-50"
                  >
                    Prev
                  </button>
                  <span className="text-xs text-muted-foreground">
                    Page {page} of {totalPages}
                  </span>
                  <button
                    onClick={() => setPage(p => Math.min(totalPages, p + 1))}
                    disabled={page === totalPages}
                    className="rounded border px-3 py-1 text-sm disabled:opacity-50"
                  >
                    Next
                  </button>
                </div>
              )}
            </CardContent>
          </Card>
        </div>

        <Card className="self-start xl:sticky xl:top-6">
          <CardHeader className="pb-3">
            <div className="flex items-center justify-between gap-3">
              <div>
                <CardDescription>Inspection Panel</CardDescription>
                <CardTitle className="text-xl">Run details</CardTitle>
              </div>
              {selectedRun && (
                <Button variant="ghost" size="sm" onClick={() => setSelectedRun(null)}>
                  Clear
                </Button>
              )}
            </div>
          </CardHeader>
          <CardContent>
            {selectedRun ? (
              <div className="space-y-4">
                <div className="flex items-center justify-between gap-3">
                  <StatusBadge
                    label={selectedRun.status}
                    severity={selectedRun.status === "COMPLETED" ? "success" : selectedRun.status === "FAILED" ? "destructive" : "caution"}
                    dot
                  />
                  <button onClick={() => setSelectedRun(null)}>
                    <X className="h-4 w-4 text-muted-foreground hover:text-foreground" />
                  </button>
                </div>
                <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-1">
                  <div className="rounded-lg border bg-muted/20 p-3">
                    <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">Operation Run ID</p>
                    <p className="mt-2 break-all font-mono text-xs">{selectedRun.operation_run_id}</p>
                  </div>
                  <div className="rounded-lg border bg-muted/20 p-3">
                    <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">Type</p>
                    <p className="mt-2 text-sm">{selectedRun.operation_type}</p>
                  </div>
                  <div className="rounded-lg border bg-muted/20 p-3">
                    <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">Started</p>
                    <p className="mt-2 text-sm">{new Date(selectedRun.started_at).toLocaleString()}</p>
                  </div>
                  <div className="rounded-lg border bg-muted/20 p-3">
                    <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">Completed</p>
                    <p className="mt-2 text-sm">
                      {selectedRun.completed_at ? new Date(selectedRun.completed_at).toLocaleString() : "--"}
                    </p>
                  </div>
                  <div className="rounded-lg border bg-muted/20 p-3">
                    <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">Duration</p>
                    <p className="mt-2 font-mono text-sm">
                      {selectedRun.duration_ms == null ? "--" : `${selectedRun.duration_ms.toFixed(1)}ms`}
                    </p>
                  </div>
                  <div className="rounded-lg border bg-muted/20 p-3">
                    <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">Linked Run ID</p>
                    <p className="mt-2 break-all font-mono text-xs">{selectedRun.linked_run_id ?? "--"}</p>
                  </div>
                </div>
                {(selectedRun.context || selectedRun.details) && (
                  <JsonViewer data={selectedRun.context ?? selectedRun.details ?? {}} title="Run Metadata" />
                )}
              </div>
            ) : (
              <div className="rounded-lg border border-dashed bg-muted/20 p-6 text-center">
                <p className="text-sm font-medium">No run selected</p>
                <p className="mt-1 text-sm text-muted-foreground">
                  Click a row in the table to inspect metadata, timestamps, and linked run context.
                </p>
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
