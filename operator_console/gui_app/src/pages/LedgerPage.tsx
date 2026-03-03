import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { MetricCard } from "@/components/MetricCard";
import { DataTable } from "@/components/DataTable";
import { ErrorAlert } from "@/components/ErrorAlert";
import { Button } from "@/components/ui/button";
import {
  getAnalytics,
  getMediaByHash,
  getMediaHistory,
  getMediaByStatus,
  getReappearances,
  getHashAudit,
} from "@/lib/api/endpoints";
import { queryKeys } from "@/lib/api/queryKeys";
import { queryOptions } from "@/lib/api/queryOptions";
import type { AnalyticsSummary, MediaFileRecord, HashAuditResult } from "@/types/api";
import { BarChart3, FileSearch, Search } from "lucide-react";

type QueryMode = "hash" | "history" | "status" | "reappearances";

function getErrorMessage(err: unknown): string | null {
  if (!err) return null;
  if (err instanceof Error) return err.message;
  return String(err);
}

export default function LedgerPage() {
  const [error, setError] = useState<string | null>(null);

  const [queryMode, setQueryMode] = useState<QueryMode>("hash");
  const [queryInput, setQueryInput] = useState("");
  const [queryResults, setQueryResults] = useState<MediaFileRecord[]>([]);
  const [queryLoading, setQueryLoading] = useState(false);

  const [auditSampleLimit, setAuditSampleLimit] = useState("100");
  const [auditRootPath, setAuditRootPath] = useState("");
  const [auditResults, setAuditResults] = useState<HashAuditResult[]>([]);
  const [auditLoading, setAuditLoading] = useState(false);

  const analyticsQuery = useQuery({
    queryKey: queryKeys.analytics,
    queryFn: async () => (await getAnalytics()).data,
    staleTime: queryOptions.analytics.staleTime,
  });

  const analytics = (analyticsQuery.data as AnalyticsSummary | undefined) ?? null;

  const executeQuery = async () => {
    setQueryLoading(true);
    setQueryResults([]);
    setError(null);
    try {
      let res;
      switch (queryMode) {
        case "hash":
          res = await getMediaByHash(queryInput);
          setQueryResults(res.data);
          break;
        case "history":
          res = await getMediaHistory(queryInput);
          setQueryResults(res.data);
          break;
        case "status":
          res = await getMediaByStatus(queryInput);
          setQueryResults((res.data as any).items || []);
          break;
        case "reappearances":
          res = await getReappearances(queryInput);
          setQueryResults((res.data as any).items || []);
          break;
      }
    } catch (err: unknown) {
      setError(getErrorMessage(err) || "Query failed");
    } finally {
      setQueryLoading(false);
    }
  };

  const executeAudit = async () => {
    setAuditLoading(true);
    setAuditResults([]);
    setError(null);
    try {
      const res = await getHashAudit({
        sample_limit: Number(auditSampleLimit),
        root_path: auditRootPath || undefined,
      });
      setAuditResults(res.data);
    } catch (err: unknown) {
      setError(getErrorMessage(err) || "Audit failed");
    } finally {
      setAuditLoading(false);
    }
  };

  const mediaColumns = [
    {
      key: "hash_sha256",
      header: "Hash",
      className: "font-mono text-xs",
      render: (r: MediaFileRecord) => `${r.hash_sha256.slice(0, 16)}…`,
    },
    {
      key: "current_path",
      header: "Path",
      className: "font-mono text-xs truncate max-w-[200px]",
    },
    { key: "status", header: "Status" },
    {
      key: "discovered_at",
      header: "First Seen",
      render: (r: MediaFileRecord) =>
        r.discovered_at ? new Date(r.discovered_at).toLocaleDateString() : "—",
    },
    {
      key: "size_bytes",
      header: "Size",
      render: (r: MediaFileRecord) => `${(r.size_bytes / 1024).toFixed(1)} KB`,
    },
  ];

  const auditColumns = [
    {
      key: "hash",
      header: "Hash",
      className: "font-mono text-xs",
      render: (r: HashAuditResult) => `${r.hash.slice(0, 16)}…`,
    },
    { key: "path", header: "Path", className: "font-mono text-xs" },
    { key: "status", header: "Status" },
    { key: "audit_note", header: "Note" },
  ];

  const combinedError = error || getErrorMessage(analyticsQuery.error);

  return (
    <div className="p-6 space-y-6 max-w-7xl">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Ledger</h1>
        <p className="text-sm text-muted-foreground mt-1">Media file analytics and audit queries</p>
      </div>

      {combinedError && (
        <ErrorAlert message={combinedError} onDismiss={() => setError(null)} />
      )}

      <div>
        <h2 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-3">Analytics</h2>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <MetricCard
            title="Total Records"
            value={analytics?.total_records ?? 0}
            icon={<BarChart3 className="h-4 w-4" />}
            loading={analyticsQuery.isLoading}
          />
          <MetricCard
            title="Avg File Size"
            value={analytics ? `${(analytics.avg_file_size / 1024).toFixed(1)} KB` : "—"}
            loading={analyticsQuery.isLoading}
          />
          {analytics?.by_status &&
            Object.entries(analytics.by_status)
              .slice(0, 2)
              .map(([status, count]) => (
                <MetricCard
                  key={status}
                  title={status}
                  value={count}
                  loading={analyticsQuery.isLoading}
                />
              ))}
        </div>
      </div>

      <div>
        <h2 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-3">Query</h2>
        <div className="rounded-lg border bg-card p-4 space-y-4">
          <div className="flex gap-2 flex-wrap">
            {(["hash", "history", "status", "reappearances"] as QueryMode[]).map(m => (
              <button
                key={m}
                onClick={() => setQueryMode(m)}
                className={`px-3 py-1.5 text-xs font-medium rounded-md border transition-colors ${queryMode === m ? "bg-primary text-primary-foreground border-primary" : "bg-card hover:bg-muted"}`}
              >
                {m === "hash"
                  ? "By Hash Prefix"
                  : m === "history"
                    ? "By Path History"
                    : m === "status"
                      ? "By Status"
                      : "Reappearances"}
              </button>
            ))}
          </div>
          <input
            value={queryInput}
            onChange={e => setQueryInput(e.target.value)}
            placeholder={
              queryMode === "hash"
                ? "Enter hash prefix…"
                : queryMode === "history"
                  ? "Enter file path…"
                  : queryMode === "status"
                    ? "Enter status…"
                    : "Enter file path…"
            }
            className="w-full max-w-md rounded-md border bg-background px-3 py-2 text-sm font-mono"
          />
          <Button size="sm" onClick={executeQuery} disabled={queryLoading || !queryInput}>
            <Search className="mr-2 h-3.5 w-3.5" />Search
          </Button>
          <DataTable
            columns={mediaColumns}
            data={queryResults}
            loading={queryLoading}
            emptyMessage="No results. Run a query above."
          />
        </div>
      </div>

      <div>
        <h2 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-3">Hash Audit</h2>
        <div className="rounded-lg border bg-card p-4 space-y-4">
          <div className="flex items-end gap-3">
            <div>
              <label className="text-xs font-medium text-muted-foreground">Sample Limit</label>
              <input
                value={auditSampleLimit}
                onChange={e => setAuditSampleLimit(e.target.value)}
                className="mt-1 w-24 rounded-md border bg-background px-3 py-2 text-sm font-mono"
              />
            </div>
            <div className="flex-1">
              <label className="text-xs font-medium text-muted-foreground">Root Path</label>
              <input
                value={auditRootPath}
                onChange={e => setAuditRootPath(e.target.value)}
                placeholder="/media"
                className="mt-1 w-full max-w-sm rounded-md border bg-background px-3 py-2 text-sm font-mono"
              />
            </div>
            <Button size="sm" onClick={executeAudit} disabled={auditLoading}>
              <FileSearch className="mr-2 h-3.5 w-3.5" />Audit
            </Button>
          </div>
          <DataTable
            columns={auditColumns}
            data={auditResults}
            loading={auditLoading}
            emptyMessage="No audit results. Run an audit above."
          />
        </div>
      </div>
    </div>
  );
}
