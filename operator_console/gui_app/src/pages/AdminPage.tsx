import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Line,
  LineChart,
  XAxis,
  YAxis,
} from "recharts";
import { ErrorAlert } from "@/components/ErrorAlert";
import { ConfirmDialog } from "@/components/ConfirmDialog";
import { JsonViewer } from "@/components/JsonViewer";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { ChartContainer, ChartTooltip, ChartTooltipContent } from "@/components/ui/chart";
import { Input } from "@/components/ui/input";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Badge } from "@/components/ui/badge";
import {
  adminDbReset,
  cancelBenchmarkRun,
  getAdminObservabilityFailures,
  getAdminObservabilityMetricsSeries,
  getAdminObservabilityOperationRuns,
  getAdminObservabilitySummary,
  getBenchmarkRun,
  getBenchmarkRuns,
  invalidateAllReadsAfterDbReset,
  queueDiscoveryBenchmark,
  queueMetadataBenchmark,
} from "@/lib/api/endpoints";
import { queryKeys } from "@/lib/api/queryKeys";
import type {
  BenchmarkRun,
  DbResetPreview,
  DbResetResult,
  FailureEventItem,
  ObservabilityMetricsSeries,
  ObservabilitySummary,
  Run,
} from "@/types/api";
import {
  Activity,
  AlertTriangle,
  BarChart3,
  Eye,
  Gauge,
  LineChart as LineChartIcon,
  Loader2,
  Play,
  RefreshCw,
  Trash2,
  XCircle,
} from "lucide-react";

const chartConfig = {
  operations: { label: "Operations", color: "hsl(195 85% 42%)" },
  failures: { label: "Failures", color: "hsl(355 78% 55%)" },
  latency: { label: "Latency ms", color: "hsl(36 90% 48%)" },
};

function formatBucketLabel(timestamp: string) {
  return new Date(timestamp).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

function SeverityBadge({ value }: { value: string }) {
  const normalized = value.toUpperCase();
  const variant =
    normalized === "COMPLETED"
      ? "default"
      : normalized.includes("FAIL") || normalized.includes("CANCEL")
        ? "destructive"
        : "secondary";
  return <Badge variant={variant as "default" | "secondary" | "destructive"}>{value}</Badge>;
}

function MetricCard({ title, value, hint }: { title: string; value: string; hint?: string }) {
  return (
    <Card>
      <CardHeader className="pb-2">
        <CardDescription>{title}</CardDescription>
        <CardTitle className="text-2xl">{value}</CardTitle>
      </CardHeader>
      {hint ? <CardContent className="pt-0 text-xs text-muted-foreground">{hint}</CardContent> : null}
    </Card>
  );
}

function ObservabilityTab() {
  const summaryQuery = useQuery({
    queryKey: queryKeys.adminObservabilitySummary,
    queryFn: getAdminObservabilitySummary,
    refetchInterval: 10_000,
  });
  const runsQuery = useQuery({
    queryKey: queryKeys.adminObservabilityRuns({ limit: 25 }),
    queryFn: () => getAdminObservabilityOperationRuns({ limit: 25 }),
    refetchInterval: 10_000,
  });
  const failuresQuery = useQuery({
    queryKey: queryKeys.adminObservabilityFailures(20),
    queryFn: () => getAdminObservabilityFailures({ limit: 20 }),
    refetchInterval: 10_000,
  });
  const seriesQuery = useQuery({
    queryKey: queryKeys.adminObservabilitySeries(24),
    queryFn: () => getAdminObservabilityMetricsSeries({ hours: 24 }),
    refetchInterval: 10_000,
  });

  const summary = summaryQuery.data?.data as ObservabilitySummary | undefined;
  const failures = failuresQuery.data?.data;
  const series = seriesQuery.data?.data as ObservabilityMetricsSeries | undefined;
  const chartRows = useMemo(() => {
    if (!series) return [];
    const operations = new Map(series.series.operation_volume.map((point) => [point.timestamp, point.value]));
    const failureMap = new Map(series.series.failure_volume.map((point) => [point.timestamp, point.value]));
    const latencyMap = new Map(series.series.latency_ms_avg.map((point) => [point.timestamp, point.value]));
    return series.series.operation_volume.map((point) => ({
      timestamp: point.timestamp,
      label: formatBucketLabel(point.timestamp),
      operations: operations.get(point.timestamp) ?? 0,
      failures: failureMap.get(point.timestamp) ?? 0,
      latency: latencyMap.get(point.timestamp) ?? 0,
    }));
  }, [series]);

  if (summaryQuery.isLoading || runsQuery.isLoading || failuresQuery.isLoading || seriesQuery.isLoading) {
    return <div className="text-sm text-muted-foreground">Loading observability data…</div>;
  }

  const error =
    summaryQuery.error ||
    runsQuery.error ||
    failuresQuery.error ||
    seriesQuery.error;
  if (error instanceof Error) {
    return <ErrorAlert message={error.message} />;
  }

  return (
    <div className="space-y-6">
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <MetricCard title="Metrics" value={summary?.metrics_enabled ? "Enabled" : "Disabled"} hint="Prometheus scrape surface" />
        <MetricCard title="24h failures" value={String(summary?.recent_failure_count ?? 0)} hint="Durable failure events" />
        <MetricCard
          title="Avg apply latency"
          value={`${Number(summary?.latest_metrics?.apply_time_ms ?? 0).toFixed(1)} ms`}
          hint="Latest persisted perf artifact"
        />
        <MetricCard
          title="Cache hit rate"
          value={`${Number(summary?.latest_metrics?.cache_hit_rate ?? 0).toFixed(1)}%`}
          hint="Latest persisted cache signal"
        />
      </div>

      <div className="grid gap-4 xl:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2"><BarChart3 className="h-4 w-4" /> Operation volume</CardTitle>
            <CardDescription>Hourly operations and failures over the last 24 hours.</CardDescription>
          </CardHeader>
          <CardContent>
            <ChartContainer config={chartConfig} className="h-[260px] w-full">
              <BarChart data={chartRows}>
                <CartesianGrid vertical={false} />
                <XAxis dataKey="label" tickLine={false} axisLine={false} />
                <YAxis allowDecimals={false} />
                <ChartTooltip content={<ChartTooltipContent />} />
                <Bar dataKey="operations" fill="var(--color-operations)" radius={4} />
                <Bar dataKey="failures" fill="var(--color-failures)" radius={4} />
              </BarChart>
            </ChartContainer>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2"><LineChartIcon className="h-4 w-4" /> Latency trend</CardTitle>
            <CardDescription>Average operation duration by hour.</CardDescription>
          </CardHeader>
          <CardContent>
            <ChartContainer config={chartConfig} className="h-[260px] w-full">
              <LineChart data={chartRows}>
                <CartesianGrid vertical={false} />
                <XAxis dataKey="label" tickLine={false} axisLine={false} />
                <YAxis />
                <ChartTooltip content={<ChartTooltipContent />} />
                <Line dataKey="latency" type="monotone" stroke="var(--color-latency)" strokeWidth={2} dot={false} />
              </LineChart>
            </ChartContainer>
          </CardContent>
        </Card>
      </div>

      <div className="grid gap-4 xl:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2"><Activity className="h-4 w-4" /> Recent failed signals</CardTitle>
            <CardDescription>Failure events and failed operation runs.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            {(failures?.failure_events as FailureEventItem[] | undefined)?.slice(0, 6).map((item) => (
              <div key={item.id} className="rounded-md border p-3">
                <div className="flex items-center justify-between gap-2">
                  <div className="font-mono text-xs">{item.error_code}</div>
                  <div className="text-xs text-muted-foreground">{new Date(item.created_at).toLocaleString()}</div>
                </div>
                <p className="mt-1 text-sm">{item.error_message}</p>
              </div>
            ))}
            {(!failures || failures.failure_events.length === 0) && (
              <div className="text-sm text-muted-foreground">No recent failure events.</div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2"><Gauge className="h-4 w-4" /> External monitoring</CardTitle>
            <CardDescription>Prometheus and Grafana links when configured.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="flex flex-wrap gap-2">
              {summary?.prometheus_url ? (
                <Button asChild variant="outline"><a href={summary.prometheus_url} target="_blank" rel="noreferrer">Open Prometheus</a></Button>
              ) : <div className="text-sm text-muted-foreground">Prometheus URL not configured.</div>}
              {summary?.grafana_url ? (
                <Button asChild><a href={summary.grafana_url} target="_blank" rel="noreferrer">Open Grafana</a></Button>
              ) : <div className="text-sm text-muted-foreground">Grafana URL not configured.</div>}
            </div>
            <div className="space-y-2 text-sm">
              {Object.entries(summary?.last_success_by_type ?? {}).map(([key, value]) => (
                <div key={key} className="flex items-center justify-between border-b pb-1">
                  <span className="font-mono text-xs">{key}</span>
                  <span className="text-muted-foreground">{value ? new Date(value).toLocaleString() : "Never"}</span>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Recent operation runs</CardTitle>
          <CardDescription>Shared durable operation log powering the Admin console.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          {(runsQuery.data?.data as Run[] | undefined)?.slice(0, 12).map((run) => (
            <div key={run.operation_run_id} className="flex flex-wrap items-center justify-between gap-3 rounded-md border p-3">
              <div>
                <div className="font-medium">{run.operation_type}</div>
                <div className="font-mono text-xs text-muted-foreground">{run.operation_run_id}</div>
              </div>
              <div className="text-sm text-muted-foreground">{new Date(run.started_at).toLocaleString()}</div>
              <SeverityBadge value={run.status} />
            </div>
          ))}
        </CardContent>
      </Card>
    </div>
  );
}

function BenchmarksTab() {
  const queryClient = useQueryClient();
  const [metadataItems, setMetadataItems] = useState("1000");
  const [metadataBatchSize, setMetadataBatchSize] = useState("250");
  const [discoveryItems, setDiscoveryItems] = useState("1000");
  const [challengeWord, setChallengeWord] = useState("media-manager");
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);

  const runsQuery = useQuery({
    queryKey: queryKeys.benchmarkRuns(50),
    queryFn: () => getBenchmarkRuns({ limit: 50 }),
    refetchInterval: 5_000,
  });
  const selectedRunQuery = useQuery({
    queryKey: selectedRunId ? queryKeys.benchmarkRun(selectedRunId) : ["admin", "benchmark", "idle"],
    queryFn: () => getBenchmarkRun(selectedRunId as string),
    enabled: Boolean(selectedRunId),
    refetchInterval: 5_000,
  });

  const metadataMutation = useMutation({
    mutationFn: () =>
      queueMetadataBenchmark({
        items: Number(metadataItems),
        batch_size: Number(metadataBatchSize),
        challenge_word: challengeWord,
      }),
    onSuccess: (result) => {
      setSelectedRunId(result.data.operation_run_id);
      queryClient.invalidateQueries({ queryKey: queryKeys.benchmarkRunsRoot });
      queryClient.invalidateQueries({ queryKey: queryKeys.runsRoot });
    },
  });

  const discoveryMutation = useMutation({
    mutationFn: () =>
      queueDiscoveryBenchmark({
        items: Number(discoveryItems),
        challenge_word: challengeWord,
      }),
    onSuccess: (result) => {
      setSelectedRunId(result.data.operation_run_id);
      queryClient.invalidateQueries({ queryKey: queryKeys.benchmarkRunsRoot });
      queryClient.invalidateQueries({ queryKey: queryKeys.runsRoot });
    },
  });

  const cancelMutation = useMutation({
    mutationFn: (operationRunId: string) => cancelBenchmarkRun(operationRunId),
    onSuccess: (_, operationRunId) => {
      setSelectedRunId(operationRunId);
      queryClient.invalidateQueries({ queryKey: queryKeys.benchmarkRunsRoot });
      queryClient.invalidateQueries({ queryKey: queryKeys.benchmarkRun(operationRunId) });
      queryClient.invalidateQueries({ queryKey: queryKeys.runsRoot });
    },
  });

  const benchmarkRuns = (runsQuery.data?.data as BenchmarkRun[] | undefined) ?? [];
  const selectedRun = selectedRunId ? (selectedRunQuery.data?.data as BenchmarkRun | undefined) : undefined;
  const benchmarkError =
    (metadataMutation.error as Error | null)?.message ||
    (discoveryMutation.error as Error | null)?.message ||
    (cancelMutation.error as Error | null)?.message ||
    (runsQuery.error as Error | null)?.message ||
    (selectedRunQuery.error as Error | null)?.message;

  return (
    <div className="space-y-6">
      {benchmarkError ? <ErrorAlert message={benchmarkError} /> : null}

      <div className="grid gap-4 xl:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Metadata benchmark</CardTitle>
            <CardDescription>Database-only synthetic metadata upsert and lookup benchmark.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            <Input value={metadataItems} onChange={(event) => setMetadataItems(event.target.value)} placeholder="Items" />
            <Input value={metadataBatchSize} onChange={(event) => setMetadataBatchSize(event.target.value)} placeholder="Batch size" />
            <Input value={challengeWord} onChange={(event) => setChallengeWord(event.target.value)} placeholder="Challenge word" />
            <Button onClick={() => metadataMutation.mutate()} disabled={metadataMutation.isPending || discoveryMutation.isPending}>
              {metadataMutation.isPending ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Play className="mr-2 h-4 w-4" />}
              Queue metadata benchmark
            </Button>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Discovery benchmark</CardTitle>
            <CardDescription>Synthetic canonical/tag query benchmark for discovery reads.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            <Input value={discoveryItems} onChange={(event) => setDiscoveryItems(event.target.value)} placeholder="Items seeded" />
            <Input value={challengeWord} onChange={(event) => setChallengeWord(event.target.value)} placeholder="Challenge word" />
            <Button onClick={() => discoveryMutation.mutate()} disabled={metadataMutation.isPending || discoveryMutation.isPending}>
              {discoveryMutation.isPending ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Play className="mr-2 h-4 w-4" />}
              Queue discovery benchmark
            </Button>
          </CardContent>
        </Card>
      </div>

      <div className="grid gap-4 xl:grid-cols-[1.2fr_1fr]">
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2"><RefreshCw className="h-4 w-4" /> Benchmark queue</CardTitle>
            <CardDescription>Queued and recent benchmark runs.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            {runsQuery.isLoading ? (
              <div className="text-sm text-muted-foreground">Loading benchmark runs…</div>
            ) : benchmarkRuns.length === 0 ? (
              <div className="text-sm text-muted-foreground">No benchmark runs queued yet.</div>
            ) : benchmarkRuns.map((run) => (
              <div
                key={run.operation_run_id}
                className="flex flex-wrap items-center justify-between gap-3 rounded-md border p-3"
              >
                <button className="text-left" onClick={() => setSelectedRunId(run.operation_run_id)}>
                  <div className="font-medium">{run.benchmark_type}</div>
                  <div className="font-mono text-xs text-muted-foreground">{run.operation_run_id}</div>
                </button>
                <SeverityBadge value={run.status} />
                <div className="flex items-center gap-2">
                  <span className="text-xs text-muted-foreground">{new Date(run.queued_at).toLocaleString()}</span>
                  {(run.status === "QUEUED" || run.status === "RUNNING" || run.status === "CANCEL_REQUESTED") ? (
                    <Button variant="outline" size="sm" onClick={() => cancelMutation.mutate(run.operation_run_id)}>
                      <XCircle className="mr-2 h-3.5 w-3.5" />
                      Cancel
                    </Button>
                  ) : null}
                </div>
              </div>
            ))}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Selected benchmark</CardTitle>
            <CardDescription>Durable result payload for the selected benchmark run.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            {!selectedRunId ? (
              <div className="text-sm text-muted-foreground">Select a benchmark run to inspect it.</div>
            ) : selectedRunQuery.isLoading ? (
              <div className="text-sm text-muted-foreground">Loading benchmark detail…</div>
            ) : selectedRun ? (
              <>
                <div className="flex items-center justify-between">
                  <div>
                    <div className="font-medium">{selectedRun.benchmark_type}</div>
                    <div className="font-mono text-xs text-muted-foreground">{selectedRun.operation_run_id}</div>
                  </div>
                  <SeverityBadge value={selectedRun.status} />
                </div>
                {selectedRun.summary_payload ? <JsonViewer data={selectedRun.summary_payload} title="Summary" /> : null}
                {selectedRun.report_payload ? <JsonViewer data={selectedRun.report_payload} title="Report" /> : null}
                {selectedRun.error_message ? <ErrorAlert message={selectedRun.error_message} /> : null}
              </>
            ) : (
              <div className="text-sm text-muted-foreground">Benchmark run not found.</div>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

function ResetTab() {
  const queryClient = useQueryClient();
  const [preview, setPreview] = useState<DbResetPreview | null>(null);
  const [result, setResult] = useState<DbResetResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [confirmOpen, setConfirmOpen] = useState(false);

  const handleDryRun = async () => {
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const res = await adminDbReset({ dry_run: true });
      setPreview(res.data as DbResetPreview);
    } catch (err: any) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const handleExecute = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await adminDbReset({ dry_run: false, challenge_word: "media-manager" });
      setResult(res.data as DbResetResult);
      setPreview(null);
      await invalidateAllReadsAfterDbReset(queryClient);
    } catch (err: any) {
      setError(err.message);
    } finally {
      setLoading(false);
      setConfirmOpen(false);
    }
  };

  return (
    <div className="space-y-6">
      {error && <ErrorAlert message={error} onDismiss={() => setError(null)} />}
      <div className="rounded-lg border-2 border-destructive/30 bg-destructive/5 p-6 space-y-4">
        <div className="flex items-center gap-3">
          <div className="p-2 rounded-md bg-destructive/10">
            <AlertTriangle className="h-6 w-6 text-destructive" />
          </div>
          <div>
            <h2 className="font-bold text-lg">Database Reset</h2>
            <p className="text-sm text-muted-foreground">Permanently delete all data from the media pipeline database. This action cannot be undone.</p>
          </div>
        </div>

        <div className="flex gap-3">
          <Button variant="outline" onClick={handleDryRun} disabled={loading}>
            {loading && !confirmOpen ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Eye className="mr-2 h-4 w-4" />}
            Preview (Dry Run)
          </Button>
          <Button variant="destructive" onClick={() => setConfirmOpen(true)} disabled={loading || !preview}>
            <Trash2 className="mr-2 h-4 w-4" />
            Execute Reset
          </Button>
        </div>

        {preview ? (
          <div className="space-y-3">
            <h3 className="text-sm font-semibold">Affected Tables</h3>
            <div className="grid grid-cols-2 gap-2">
              {preview.affected_tables.map((table) => (
                <div key={table} className="rounded-md border bg-card p-3 flex items-center justify-between">
                  <span className="text-sm font-mono">{table}</span>
                  <span className="text-xs font-mono text-destructive font-bold">planned</span>
                </div>
              ))}
            </div>
          </div>
        ) : null}

        {result ? (
          <div className="space-y-3">
            <ErrorAlert message={result.message} severity={result.success ? "info" : "error"} />
            <JsonViewer data={result} title="Reset Result" />
          </div>
        ) : null}
      </div>

      <ConfirmDialog
        open={confirmOpen}
        onOpenChange={setConfirmOpen}
        title="Confirm Database Reset"
        description="This will permanently delete ALL data from the media pipeline database. This action is irreversible."
        destructive
        challengeWord="media-manager"
        onConfirm={handleExecute}
        loading={loading}
      >
        {preview ? (
          <div className="text-sm text-muted-foreground">
            <p className="font-semibold">Tables to be cleared:</p>
            <ul className="list-disc list-inside mt-1">
              {preview.affected_tables.map((t) => <li key={t} className="font-mono text-xs">{t}</li>)}
            </ul>
          </div>
        ) : null}
      </ConfirmDialog>
    </div>
  );
}

export default function AdminPage() {
  return (
    <div className="p-6 space-y-6 max-w-7xl">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Admin</h1>
        <p className="text-sm text-muted-foreground mt-1">Controlled destructive operations, observability, and benchmark workflows over the API.</p>
      </div>

      <Tabs defaultValue="observability" className="space-y-4">
        <TabsList className="grid w-full grid-cols-3 max-w-2xl">
          <TabsTrigger value="observability">Observability</TabsTrigger>
          <TabsTrigger value="benchmarks">Benchmarks</TabsTrigger>
          <TabsTrigger value="reset">Reset</TabsTrigger>
        </TabsList>
        <TabsContent value="observability"><ObservabilityTab /></TabsContent>
        <TabsContent value="benchmarks"><BenchmarksTab /></TabsContent>
        <TabsContent value="reset"><ResetTab /></TabsContent>
      </Tabs>
    </div>
  );
}
