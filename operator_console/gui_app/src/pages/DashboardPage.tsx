import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { MetricCard } from "@/components/MetricCard";
import { StatusBadge } from "@/components/StatusBadge";
import { ErrorAlert } from "@/components/ErrorAlert";
import { OperationRiskLabel } from "@/components/OperationRiskLabel";
import { JsonViewer } from "@/components/JsonViewer";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import {
  getDashboardSummary,
  getLatestMetrics,
  invalidateReadsAfterOperation,
  runIngest,
  runOperatorRun,
} from "@/lib/api/endpoints";
import { queryKeys } from "@/lib/api/queryKeys";
import { queryOptions } from "@/lib/api/queryOptions";
import type { DashboardSummary, LatestMetrics, OperationResult } from "@/types";
import {
  ArrowRight,
  Crown,
  Database,
  Files,
  ImageIcon,
  Layers,
  Loader2,
  PlayCircle,
  Timer,
  Video,
  Zap,
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

  const performanceCards = [
    {
      title: "Ingest",
      value: `${metrics?.ingest_time_ms ?? 0}ms`,
      subtitle: "Discovery and metadata load",
      icon: <Timer className="h-4 w-4" />,
    },
    {
      title: "Plan",
      value: `${metrics?.plan_time_ms ?? 0}ms`,
      subtitle: "Planner runtime",
      icon: <Timer className="h-4 w-4" />,
    },
    {
      title: "Apply",
      value: `${metrics?.apply_time_ms ?? 0}ms`,
      subtitle: "Apply engine runtime",
      icon: <Timer className="h-4 w-4" />,
    },
    {
      title: "DB",
      value: `${metrics?.db_time_ms ?? 0}ms`,
      subtitle: "Durable write time",
      icon: <Database className="h-4 w-4" />,
    },
    {
      title: "Cache Hit",
      value: `${(metrics?.cache_hit_rate ?? 0).toFixed(1)}%`,
      subtitle: "Read-path efficiency",
      icon: <Zap className="h-4 w-4" />,
    },
  ];

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
    <div className="max-w-7xl space-y-6 p-6">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Dashboard</h1>
          <p className="mt-1 max-w-2xl text-sm text-muted-foreground">
            System overview, runtime health, and the fastest path into validate or composite runs.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <StatusBadge
            label={`Regression: ${metrics?.last_regression_status ?? "UNKNOWN"}`}
            severity={
              metrics?.last_regression_status === "PASS"
                ? "success"
                : metrics?.last_regression_status === "FAIL"
                  ? "destructive"
                  : "caution"
            }
            dot
          />
          <StatusBadge
            label={actionMode === "validate" ? "Safe Validate Mode" : "Mutating Composite Mode"}
            severity={actionMode === "validate" ? "info" : "caution"}
          />
        </div>
      </div>

      {error && <ErrorAlert message={error} onDismiss={() => setActionError(null)} />}

      <div className="grid gap-4 xl:grid-cols-[1.4fr_0.9fr]">
        <Card className="border-primary/15 bg-gradient-to-br from-card via-card to-primary/5">
          <CardHeader className="pb-4">
            <CardDescription>Pipeline Summary</CardDescription>
            <CardTitle className="text-xl">Current media system posture</CardTitle>
          </CardHeader>
          <CardContent className="grid grid-cols-2 gap-3 md:grid-cols-3 lg:grid-cols-6">
            <MetricCard title="Total Files" value={summary?.total_files ?? 0} icon={<Files className="h-4 w-4" />} loading={loading} />
            <MetricCard title="Images" value={summary?.total_images ?? 0} icon={<ImageIcon className="h-4 w-4" />} loading={loading} />
            <MetricCard title="Videos" value={summary?.total_videos ?? 0} icon={<Video className="h-4 w-4" />} loading={loading} />
            <MetricCard title="Dup Groups" value={summary?.duplicate_groups ?? 0} icon={<Layers className="h-4 w-4" />} loading={loading} />
            <MetricCard title="Canonical" value={summary?.canonical_files ?? 0} icon={<Crown className="h-4 w-4" />} loading={loading} />
            <MetricCard title="Total Runs" value={summary?.total_runs ?? 0} icon={<PlayCircle className="h-4 w-4" />} loading={loading} />
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-4">
            <CardDescription>Quick Action</CardDescription>
            <CardTitle className="text-xl">Execute the next operation</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="flex items-center gap-3">
              <div className="flex overflow-hidden rounded-md border">
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
                ? "Performs a dry-run ingest to validate files without modifying durable state."
                : "Runs the ingest, plan, and apply pipeline. This is a mutating operation."}
            </p>
            <div className="flex flex-col gap-3 sm:flex-row">
              <Input
                value={rootPath}
                onChange={e => setRootPath(e.target.value)}
                placeholder="Root path (optional)"
                className="max-w-xl font-mono"
              />
              <Button
                onClick={handleQuickAction}
                disabled={actionLoading}
                variant={actionMode === "composite" ? "destructive" : "default"}
              >
                {actionLoading && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                Execute
              </Button>
            </div>
            {actionResult ? (
              <div className="space-y-3 rounded-lg border bg-muted/30 p-4">
                <div className="flex flex-wrap items-center gap-3">
                  <StatusBadge label={actionResult.success ? "Success" : "Failed"} severity={actionResult.success ? "success" : "destructive"} dot />
                  <span className="font-mono text-xs text-muted-foreground">{actionResult.duration_ms}ms</span>
                </div>
                <p className="text-sm">{actionResult.summary}</p>
                <JsonViewer data={actionResult.details} title="Operation Details" />
              </div>
            ) : (
              <div className="rounded-lg border border-dashed bg-muted/20 p-4 text-sm text-muted-foreground">
                Execute a quick action to inspect the latest result payload without leaving the dashboard.
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      <div>
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">Performance</h2>
          <span className="text-xs text-muted-foreground">Latest recorded timings</span>
        </div>
        <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
          {performanceCards.map(card => (
            <MetricCard
              key={card.title}
              title={card.title}
              value={card.value}
              subtitle={card.subtitle}
              icon={card.icon}
              loading={loading}
            />
          ))}
          <Card className="flex items-center justify-center p-4">
            {loading ? (
              <div className="h-8 w-16 animate-pulse rounded bg-muted" />
            ) : (
              <div className="space-y-2 text-center">
                <StatusBadge
                  label={`Regression: ${metrics?.last_regression_status ?? "UNKNOWN"}`}
                  severity={metrics?.last_regression_status === "PASS" ? "success" : metrics?.last_regression_status === "FAIL" ? "destructive" : "caution"}
                  dot
                />
                <p className="text-xs text-muted-foreground">Latest benchmark regression signal</p>
              </div>
            )}
          </Card>
        </div>
      </div>

      <Card>
        <CardHeader className="pb-3">
          <CardDescription>Operator workflow</CardDescription>
          <CardTitle className="text-xl">Suggested operating sequence</CardTitle>
        </CardHeader>
        <CardContent className="grid gap-3 md:grid-cols-3">
          <div className="rounded-lg border bg-muted/20 p-4">
            <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">1. Validate</p>
            <p className="mt-2 text-sm">Start with a dry-run ingest when checking a new root path or recent file drop.</p>
          </div>
          <div className="rounded-lg border bg-muted/20 p-4">
            <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">2. Review</p>
            <p className="mt-2 text-sm">Inspect duplicates, gallery output, and recent runs before making a mutating pass.</p>
          </div>
          <div className="rounded-lg border bg-muted/20 p-4">
            <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">3. Apply</p>
            <p className="mt-2 flex items-center gap-2 text-sm">
              Run the composite pipeline only when the validation signal looks healthy.
              <ArrowRight className="h-4 w-4 text-muted-foreground" />
            </p>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
