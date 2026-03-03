import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { MetricCard } from "@/components/MetricCard";
import { StatusBadge } from "@/components/StatusBadge";
import { ErrorAlert } from "@/components/ErrorAlert";
import { OperationRiskLabel } from "@/components/OperationRiskLabel";
import { JsonViewer } from "@/components/JsonViewer";
import { Button } from "@/components/ui/button";
import {
  getDashboardSummary,
  getLatestMetrics,
  invalidateReadsAfterOperation,
  runIngest,
  runOperatorRun,
} from "@/lib/api/endpoints";
import { queryKeys } from "@/lib/api/queryKeys";
import { queryOptions } from "@/lib/api/queryOptions";
import type { DashboardSummary, LatestMetrics, OperationResult } from "@/types/api";
import {
  Files,
  ImageIcon,
  Video,
  Layers,
  Crown,
  PlayCircle,
  Timer,
  Database,
  Zap,
  Loader2,
} from "lucide-react";

function getErrorMessage(err: unknown): string | null {
  if (!err) return null;
  if (err instanceof Error) return err.message;
  return String(err);
}

export default function DashboardPage() {
  const queryClient = useQueryClient();
  const [actionMode, setActionMode] = useState<"validate" | "composite">("validate");
  const [actionLoading, setActionLoading] = useState(false);
  const [actionResult, setActionResult] = useState<OperationResult | null>(null);
  const [rootPath, setRootPath] = useState("");
  const [actionError, setActionError] = useState<string | null>(null);

  const summaryQuery = useQuery({
    queryKey: queryKeys.dashboardSummary,
    queryFn: async () => (await getDashboardSummary()).data as DashboardSummary,
    staleTime: queryOptions.dashboardSummary.staleTime,
  });

  const metricsQuery = useQuery({
    queryKey: queryKeys.latestMetrics,
    queryFn: async () => (await getLatestMetrics()).data as LatestMetrics,
    staleTime: queryOptions.latestMetrics.staleTime,
  });

  const summary = summaryQuery.data;
  const metrics = metricsQuery.data;
  const loading = summaryQuery.isLoading || metricsQuery.isLoading;
  const error =
    actionError || getErrorMessage(summaryQuery.error) || getErrorMessage(metricsQuery.error);

  const handleQuickAction = async () => {
    setActionLoading(true);
    setActionResult(null);
    setActionError(null);
    try {
      if (actionMode === "validate") {
        const res = await runIngest({ folder_path: rootPath || undefined, dry_run: true });
        setActionResult(res.data);
        await invalidateReadsAfterOperation(queryClient, "ingest");
      } else {
        const res = await runOperatorRun({
          folder_path: rootPath || undefined,
          policy_name: "FIRST_SEEN",
          dry_run: false,
        });
        setActionResult(res.data);
        await invalidateReadsAfterOperation(queryClient, "operatorRun");
      }
    } catch (err: unknown) {
      setActionError(getErrorMessage(err) || "Operation failed");
    } finally {
      setActionLoading(false);
    }
  };

  return (
    <div className="p-6 space-y-6 max-w-7xl">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Dashboard</h1>
        <p className="text-sm text-muted-foreground mt-1">System overview and quick actions</p>
      </div>

      {error && <ErrorAlert message={error} onDismiss={() => setActionError(null)} />}

      <div>
        <h2 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-3">Pipeline Summary</h2>
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
          <MetricCard title="Total Files" value={summary?.total_files ?? 0} icon={<Files className="h-4 w-4" />} loading={loading} />
          <MetricCard title="Images" value={summary?.total_images ?? 0} icon={<ImageIcon className="h-4 w-4" />} loading={loading} />
          <MetricCard title="Videos" value={summary?.total_videos ?? 0} icon={<Video className="h-4 w-4" />} loading={loading} />
          <MetricCard title="Dup Groups" value={summary?.duplicate_groups ?? 0} icon={<Layers className="h-4 w-4" />} loading={loading} />
          <MetricCard title="Canonical" value={summary?.canonical_files ?? 0} icon={<Crown className="h-4 w-4" />} loading={loading} />
          <MetricCard title="Total Runs" value={summary?.total_runs ?? 0} icon={<PlayCircle className="h-4 w-4" />} loading={loading} />
        </div>
      </div>

      <div>
        <h2 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-3">Performance</h2>
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
          <MetricCard title="Ingest" value={`${metrics?.ingest_time_ms ?? 0}ms`} icon={<Timer className="h-4 w-4" />} loading={loading} />
          <MetricCard title="Plan" value={`${metrics?.plan_time_ms ?? 0}ms`} icon={<Timer className="h-4 w-4" />} loading={loading} />
          <MetricCard title="Apply" value={`${metrics?.apply_time_ms ?? 0}ms`} icon={<Timer className="h-4 w-4" />} loading={loading} />
          <MetricCard title="DB" value={`${metrics?.db_time_ms ?? 0}ms`} icon={<Database className="h-4 w-4" />} loading={loading} />
          <MetricCard title="Cache Hit" value={`${(metrics?.cache_hit_rate ?? 0).toFixed(1)}%`} icon={<Zap className="h-4 w-4" />} loading={loading} />
          <div className="rounded-lg border bg-card p-4 flex items-center justify-center">
            {loading ? (
              <div className="h-8 w-16 rounded bg-muted animate-pulse" />
            ) : (
              <StatusBadge
                label={`Regression: ${metrics?.last_regression_status ?? "UNKNOWN"}`}
                severity={metrics?.last_regression_status === "PASS" ? "success" : metrics?.last_regression_status === "FAIL" ? "destructive" : "caution"}
                dot
              />
            )}
          </div>
        </div>
      </div>

      <div>
        <h2 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-3">Quick Action</h2>
        <div className="rounded-lg border bg-card p-5 space-y-4">
          <div className="flex items-center gap-3">
            <div className="flex rounded-md border overflow-hidden">
              <button
                onClick={() => setActionMode("validate")}
                className={`px-3 py-1.5 text-xs font-medium transition-colors ${actionMode === "validate" ? "bg-primary text-primary-foreground" : "bg-card hover:bg-muted"}`}
              >
                Validate Ingest
              </button>
              <button
                onClick={() => setActionMode("composite")}
                className={`px-3 py-1.5 text-xs font-medium transition-colors ${actionMode === "composite" ? "bg-primary text-primary-foreground" : "bg-card hover:bg-muted"}`}
              >
                Composite Run
              </button>
            </div>
            <OperationRiskLabel mutating={actionMode === "composite"} />
          </div>
          <p className="text-sm text-muted-foreground">
            {actionMode === "validate"
              ? "Performs a dry-run ingest to validate files without modifying state. Safe to run at any time."
              : "Runs the full ingest → plan → apply pipeline. This will modify database state and file records."}
          </p>
          <div className="flex items-center gap-3">
            <input
              value={rootPath}
              onChange={e => setRootPath(e.target.value)}
              placeholder="Root path (optional)"
              className="flex-1 max-w-sm rounded-md border bg-background px-3 py-2 text-sm font-mono"
            />
            <Button onClick={handleQuickAction} disabled={actionLoading} variant={actionMode === "composite" ? "destructive" : "default"}>
              {actionLoading && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
              Execute
            </Button>
          </div>
          {actionResult && (
            <div className="space-y-3 pt-2">
              <div className="flex items-center gap-3">
                <StatusBadge label={actionResult.success ? "Success" : "Failed"} severity={actionResult.success ? "success" : "destructive"} dot />
                <span className="text-xs text-muted-foreground font-mono">{actionResult.duration_ms}ms</span>
              </div>
              <p className="text-sm">{actionResult.summary}</p>
              <JsonViewer data={actionResult.details} title="Operation Details" />
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
