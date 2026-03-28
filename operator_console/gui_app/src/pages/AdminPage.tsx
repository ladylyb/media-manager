import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useSearchParams } from "react-router-dom";
import { Bar, BarChart, CartesianGrid, Line, LineChart, XAxis, YAxis } from "recharts";
import {
  Activity,
  AlertTriangle,
  BarChart3,
  CheckCircle2,
  ChevronDown,
  Clock3,
  Eye,
  FileSearch,
  Fingerprint,
  FolderTree,
  GitCompareArrows,
  FolderClock,
  Gauge,
  History,
  LineChart as LineChartIcon,
  Loader2,
  Play,
  RefreshCw,
  Save,
  Search,
  ShieldCheck,
  Sparkles,
  Trash2,
  Wand2,
  Workflow,
  XCircle,
  Plus,
  X,
} from "lucide-react";

import { ConfirmDialog } from "@/components/ConfirmDialog";
import { DataTable } from "@/components/DataTable";
import { ErrorAlert } from "@/components/ErrorAlert";
import { JsonViewer } from "@/components/JsonViewer";
import { MetricCard } from "@/components/MetricCard";
import { LiveProgressPanel } from "@/components/progress/LiveProgressPanel";
import { StatusBadge } from "@/components/StatusBadge";
import { TopSurfaceHeader } from "@/components/layout/TopSurfaceHeader";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { ChartContainer, ChartTooltip, ChartTooltipContent } from "@/components/ui/chart";
import { Checkbox } from "@/components/ui/checkbox";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  adminDbReset,
  cancelBenchmarkRun,
  getAdminObservabilityFailures,
  getAdminObservabilityMetricsSeries,
  getAdminObservabilityOperationRuns,
  getAdminObservabilitySummary,
  getAnalytics,
  getBenchmarkRun,
  getBenchmarkRuns,
  getHashAudit,
  getMediaByHash,
  getMediaByStatus,
  getMediaHistory,
  getPolicy,
  getReappearances,
  getRuns,
  invalidateAllReadsAfterDbReset,
  invalidateReadsAfterPolicyUpdate,
  queueDiscoveryBenchmark,
  queueMetadataBenchmark,
  reconcileStaleOperationRuns,
  updatePolicy,
} from "@/lib/api/endpoints";
import { queryKeys } from "@/lib/api/queryKeys";
import { queryOptions } from "@/lib/api/queryOptions";
import type {
  AnalyticsSummary,
  BenchmarkRun,
  DbResetPreview,
  DbResetResult,
  FailureEventItem,
  HashAuditResult,
  MediaFileRecord,
  ObservabilityMetricsSeries,
  OperationRunReconcileResult,
  ObservabilitySummary,
  PaginatedResponse,
  Policy,
  PolicyUpdate,
  Run,
} from "@/types";

type AdminTab =
  | "overview"
  | "activity"
  | "library-rules"
  | "file-history"
  | "integrity-check"
  | "system-health"
  | "benchmarks"
  | "reset";
type FileHistoryTask = "history" | "hash" | "status" | "reappearances";

const VALID_ADMIN_TABS: AdminTab[] = [
  "overview",
  "activity",
  "library-rules",
  "file-history",
  "integrity-check",
  "system-health",
  "benchmarks",
  "reset",
];
const STATUS_EXAMPLES = ["INGESTED", "PROCESSED", "DELETED"] as const;

const chartConfig = {
  operations: { label: "Operations", color: "hsl(195 85% 42%)" },
  failures: { label: "Failures", color: "hsl(355 78% 55%)" },
  latency: { label: "Latency ms", color: "hsl(36 90% 48%)" },
};

function getErrorMessage(err: unknown): string | null {
  if (!err) return null;
  if (err instanceof Error) return err.message;
  return String(err);
}

function getAdminTab(value: string | null): AdminTab {
  return VALID_ADMIN_TABS.includes(value as AdminTab) ? (value as AdminTab) : "overview";
}

function formatBucketLabel(timestamp: string) {
  return new Date(timestamp).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

function formatJobName(operationType: string) {
  return operationType
    .toLowerCase()
    .split("_")
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

function formatDuration(durationMs: number | null) {
  if (durationMs == null) return "Still running";
  if (durationMs < 1000) return `${durationMs.toFixed(0)} ms`;
  return `${(durationMs / 1000).toFixed(1)} s`;
}

function formatFileState(status: string) {
  return status.toLowerCase().replace(/_/g, " ");
}

function formatSize(sizeBytes: number) {
  if (sizeBytes < 1024) return `${sizeBytes} B`;
  if (sizeBytes < 1024 * 1024) return `${(sizeBytes / 1024).toFixed(1)} KB`;
  return `${(sizeBytes / (1024 * 1024)).toFixed(1)} MB`;
}

function getJobSummary(run: Run) {
  const jobName = formatJobName(run.operation_type);
  if (run.status === "FAILED") {
    return `${jobName} needs follow-up because it ended in failure.`;
  }
  if (run.status === "STARTED") {
    return `${jobName} has started and is still in progress.`;
  }
  return `${jobName} completed successfully.`;
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

function AdminMetricCard({ title, value, hint }: { title: string; value: string; hint?: string }) {
  return (
    <Card className="rounded-[24px] border-border/70 shadow-sm">
      <CardHeader className="pb-2">
        <CardDescription>{title}</CardDescription>
        <CardTitle className="text-2xl">{value}</CardTitle>
      </CardHeader>
      {hint ? <CardContent className="pt-0 text-xs text-muted-foreground">{hint}</CardContent> : null}
    </Card>
  );
}

function GuidanceCard({
  title,
  description,
  whenToUse,
  example,
}: {
  title: string;
  description: string;
  whenToUse: string;
  example: string;
}) {
  return (
    <Card className="rounded-[28px] border-border/70 bg-background/85 shadow-sm">
      <CardContent className="space-y-4 p-5">
        <p className="text-sm font-semibold text-foreground">{title}</p>
        <div className="grid gap-4 lg:grid-cols-3">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.22em] text-muted-foreground">
              What this helps with
            </p>
            <p className="mt-2 text-sm leading-6 text-foreground">{description}</p>
          </div>
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.22em] text-muted-foreground">
              When to use it
            </p>
            <p className="mt-2 text-sm leading-6 text-foreground">{whenToUse}</p>
          </div>
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.22em] text-muted-foreground">
              Try questions like
            </p>
            <p className="mt-2 text-sm leading-6 text-foreground">{example}</p>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

const policyOptions = [
  {
    value: "FIRST_SEEN",
    title: "Keep the first file the library saw",
    description:
      "Best when you want predictable, stable results and do not need to favor any particular folder.",
    helper: "Good default for most libraries.",
  },
  {
    value: "PREFER_ROOT",
    title: "Prefer files from specific folders",
    description:
      "Best when you want the app to keep copies from trusted folders, such as your main archive or curated library.",
    helper: "Use this when folder location matters.",
  },
  {
    value: "EXIF_FILENAME_FALLBACK",
    title: "Prefer embedded dates, then filename evidence",
    description:
      "Best for archives where filesystem timestamps drifted over time and filename patterns are more trustworthy than copied modified dates.",
    helper: "Uses embedded metadata first, then filename dates, then deterministic fallbacks.",
  },
  {
    value: "SHORTEST_PATH",
    title: "Prefer the shortest folder path",
    description:
      "Advanced option for libraries where cleaner, shorter paths usually represent the better kept copy.",
    helper: "Use only if that rule matches your library structure.",
  },
];

const namingStrategyOptions = [
  {
    value: "SHARED_CANONICAL_NAME",
    title: "Shared canonical name",
    description:
      "Keep duplicate families visually grouped by reusing the canonical base name and adding a duplicate suffix.",
    helper: "Best when grouping on disk matters more than preserving duplicate-specific naming clues.",
  },
  {
    value: "DUPLICATE_OWNS_DATE_STANDARDIZED",
    title: "Duplicate owns date (standardized)",
    description:
      "Keep standardized duplicate names, but let each duplicate use its own date evidence when its standardized name is built.",
    helper: "Good when you want normalized names without hiding a duplicate's own date trail.",
  },
  {
    value: "PRESERVE_DUPLICATE_ORIGINAL_NAME",
    title: "Preserve duplicate original name",
    description:
      "Keep the canonical item standardized, but preserve the duplicate's original filename so source provenance stays visible.",
    helper: "Best when duplicate history matters more than filename grouping.",
  },
];

function explainPolicyRule(rule: string): string {
  switch (rule) {
    case "embedded_metadata_evidence DESC":
      return "Prefer copies backed by embedded metadata or EXIF date evidence first.";
    case "filename_date_evidence DESC":
      return "If embedded metadata is not available, prefer copies whose filenames contain a usable date.";
    case "preferred_root_match DESC":
      return "Prefer files inside your chosen folders first.";
    case "first_seen_at ASC":
      return "If there is still a tie, keep the file seen earliest by the library.";
    case "file_instance_id ASC":
      return "If there is still a tie, use a stable internal order so the result stays deterministic.";
    default:
      return rule
        .replaceAll("_", " ")
        .replace(/\basc\b/i, "ascending")
        .replace(/\bdesc\b/i, "descending");
    }
}

function formatPolicyUpdatedAt(value: string | null) {
  if (!value) return "Not recorded";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString();
}

function PolicyChoiceCard({
  value,
  selected,
  title,
  description,
  helper,
  onSelect,
}: {
  value: string;
  selected: boolean;
  title: string;
  description: string;
  helper: string;
  onSelect: (value: string) => void;
}) {
  return (
    <button
      type="button"
      onClick={() => onSelect(value)}
      className={`w-full rounded-[28px] border p-5 text-left transition-all ${
        selected
          ? "border-primary/35 bg-primary/10 shadow-sm"
          : "border-border/70 bg-background/80 hover:border-primary/20 hover:bg-muted/35"
      }`}
    >
      <div className="space-y-2">
        <div className="flex flex-wrap items-center gap-2">
          <p className="text-base font-semibold text-foreground">{title}</p>
          {selected ? <StatusBadge label="Current choice" severity="success" /> : null}
        </div>
        <p className="text-sm leading-6 text-muted-foreground">{description}</p>
        <p className="text-sm font-medium text-foreground">{helper}</p>
      </div>
    </button>
  );
}

function WorkspaceCard({
  title,
  description,
  href,
  icon,
  badge,
}: {
  title: string;
  description: string;
  href: string;
  icon: React.ReactNode;
  badge?: string;
}) {
  return (
    <Link
      to={href}
      className="rounded-[26px] border border-border/70 bg-background/85 p-5 shadow-sm transition-colors hover:border-primary/25 hover:bg-primary/5"
    >
      <div className="flex items-start gap-4">
        <div className="rounded-2xl border border-border/70 bg-card p-3">{icon}</div>
        <div className="min-w-0">
          {badge ? (
            <p className="text-[11px] font-semibold uppercase tracking-[0.2em] text-muted-foreground">{badge}</p>
          ) : null}
          <p className="mt-1 text-base font-semibold text-foreground">{title}</p>
          <p className="mt-2 text-sm leading-6 text-muted-foreground">{description}</p>
        </div>
      </div>
    </Link>
  );
}

function OverviewTab({
  setTab,
}: {
  setTab: (tab: AdminTab) => void;
}) {
  const runsQuery = useQuery({
    queryKey: queryKeys.runs(50),
    queryFn: async () => (await getRuns({ limit: 50 })).data,
    staleTime: queryOptions.runs.staleTime,
  });
  const analyticsQuery = useQuery({
    queryKey: queryKeys.analytics,
    queryFn: async () => (await getAnalytics()).data,
    staleTime: queryOptions.analytics.staleTime,
  });
  const summaryQuery = useQuery({
    queryKey: queryKeys.adminObservabilitySummary,
    queryFn: getAdminObservabilitySummary,
    refetchInterval: 10_000,
  });

  const runs = ((runsQuery.data as PaginatedResponse<Run> | undefined)?.items ?? []);
  const failedRuns = runs.filter((run) => run.status === "FAILED").length;
  const activeRuns = runs.filter((run) => run.status === "STARTED").length;
  const analytics = (analyticsQuery.data as AnalyticsSummary | undefined) ?? null;
  const summary = summaryQuery.data?.data as ObservabilitySummary | undefined;
  const overviewError =
    getErrorMessage(runsQuery.error) ||
    getErrorMessage(analyticsQuery.error) ||
    getErrorMessage(summaryQuery.error);

  return (
    <div className="space-y-6">
      <GuidanceCard
        title="Start here"
        description="Admin is now one workspace. Begin with the calmer review tools first, then move into technical or destructive actions only when you actually need them."
        whenToUse="Use Overview when you are not sure where to go next or when you want the simplest path to the right tool."
        example="Did something fail? What do we know about this file? Is the system healthy? Do I need a benchmark or a reset?"
      />

      {overviewError ? <ErrorAlert message={overviewError} /> : null}

      <div className="grid gap-3 md:grid-cols-3">
        <MetricCard
          title="Needs attention"
          value={failedRuns}
          subtitle="Recent jobs that ended in failure"
          icon={<AlertTriangle className="h-4 w-4" />}
          loading={runsQuery.isLoading}
        />
        <MetricCard
          title="Tracked files"
          value={analytics?.total_records ?? 0}
          subtitle="Records available in file history"
          icon={<FileSearch className="h-4 w-4" />}
          loading={analyticsQuery.isLoading}
        />
        <MetricCard
          title="Recent failures"
          value={summary?.recent_failure_count ?? 0}
          subtitle="Durable failure events in the last 24 hours"
          icon={<XCircle className="h-4 w-4" />}
          loading={summaryQuery.isLoading}
        />
      </div>

      <div className="grid gap-4 lg:grid-cols-2 xl:grid-cols-3">
        <WorkspaceCard
          href="/admin?tab=activity"
          icon={<Activity className="h-5 w-5" />}
          badge="Most useful first"
          title="Review Activity"
          description="See what the system has done recently, whether something failed, and what happened inside a specific job."
        />
        <WorkspaceCard
          href="/admin?tab=file-history"
          icon={<History className="h-5 w-5" />}
          title="Find a File"
          description="Look up file history by path, fingerprint, or state without needing to understand the underlying ledger model."
        />
        <WorkspaceCard
          href="/admin?tab=library-rules"
          icon={<Wand2 className="h-5 w-5" />}
          title="Adjust Library Rules"
          description="Choose how the app decides which file should remain the main version when similar files are found."
        />
        <WorkspaceCard
          href="/admin?tab=system-health"
          icon={<Gauge className="h-5 w-5" />}
          title="Check System Health"
          description="Review failures, traffic trends, latency, and external monitoring links when you are troubleshooting."
        />
        <WorkspaceCard
          href="/admin?tab=integrity-check"
          icon={<ShieldCheck className="h-5 w-5" />}
          title="Run an Integrity Check"
          description="Perform a read-only verification pass on stored file fingerprints when you want extra confidence in file-record health."
        />
        <WorkspaceCard
          href="/admin?tab=benchmarks"
          icon={<BarChart3 className="h-5 w-5" />}
          badge="Advanced"
          title="Measure Performance"
          description="Queue synthetic benchmarks for metadata and discovery work. This is mainly for technical validation in dev or test."
        />
        <WorkspaceCard
          href="/admin?tab=reset"
          icon={<Trash2 className="h-5 w-5" />}
          badge="Danger zone"
          title="Reset Library Data"
          description="Preview or clear the database in dev and test environments only. This is destructive and should be used sparingly."
        />
      </div>

      <Card className="rounded-[28px] border-border/70 shadow-sm">
        <CardHeader className="pb-3">
          <CardDescription>Recommended flow</CardDescription>
          <CardTitle className="text-xl">Use the simplest tool that answers your question</CardTitle>
        </CardHeader>
        <CardContent className="grid gap-3 md:grid-cols-4">
          <button
            type="button"
            onClick={() => setTab("activity")}
            className="rounded-2xl border bg-muted/15 p-4 text-left transition-colors hover:bg-primary/5"
          >
            <p className="text-sm font-semibold">1. Activity</p>
            <p className="mt-2 text-sm text-muted-foreground">Start here when something may have failed or is still running.</p>
          </button>
          <button
            type="button"
            onClick={() => setTab("file-history")}
            className="rounded-2xl border bg-muted/15 p-4 text-left transition-colors hover:bg-primary/5"
          >
            <p className="text-sm font-semibold">2. File History</p>
            <p className="mt-2 text-sm text-muted-foreground">Use this when the question is about a file rather than a job.</p>
          </button>
          <button
            type="button"
            onClick={() => setTab("library-rules")}
            className="rounded-2xl border bg-muted/15 p-4 text-left transition-colors hover:bg-primary/5"
          >
            <p className="text-sm font-semibold">3. Library Rules</p>
            <p className="mt-2 text-sm text-muted-foreground">Use this when the wrong copy is being kept as the main version.</p>
          </button>
          <button
            type="button"
            onClick={() => setTab("system-health")}
            className="rounded-2xl border bg-muted/15 p-4 text-left transition-colors hover:bg-primary/5"
          >
            <p className="text-sm font-semibold">4. Advanced Tools</p>
            <p className="mt-2 text-sm text-muted-foreground">Only move into health, benchmarks, or reset when the simpler review tools are not enough.</p>
          </button>
        </CardContent>
      </Card>
    </div>
  );
}

function ActivityTab() {
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
  const sorted = [...(data?.items ?? [])].sort((a, b) => {
    const aVal = (a as Record<string, unknown>)[sortKey];
    const bVal = (b as Record<string, unknown>)[sortKey];
    if (aVal === bVal) return 0;
    const order = sortOrder === "asc" ? 1 : -1;
    return aVal && bVal && aVal > bVal ? order : -order;
  });

  useEffect(() => {
    if (!selectedRun && sorted.length > 0) {
      setSelectedRun(sorted[0]);
    }
  }, [selectedRun, sorted]);

  const totalPages = Math.max(1, Math.ceil(sorted.length / pageSize));
  const pagedItems = sorted.slice((page - 1) * pageSize, page * pageSize);
  const failedRuns = sorted.filter((run) => run.status === "FAILED").length;
  const activeRuns = sorted.filter((run) => run.status === "STARTED").length;
  const completedRuns = sorted.filter((run) => run.status === "COMPLETED").length;

  const columns = [
    {
      key: "operation_type",
      header: "Job",
      sortable: true,
      render: (run: Run) => (
        <div>
          <p className="font-medium text-foreground">{formatJobName(run.operation_type)}</p>
          <p className="text-xs text-muted-foreground">{getJobSummary(run)}</p>
        </div>
      ),
    },
    {
      key: "started_at",
      header: "Started",
      sortable: true,
      render: (run: Run) => new Date(run.started_at).toLocaleString(),
    },
    {
      key: "status",
      header: "Status",
      sortable: true,
      render: (run: Run) => (
        <StatusBadge
          label={run.status === "FAILED" ? "Needs attention" : run.status === "STARTED" ? "In progress" : "Completed"}
          severity={run.status === "COMPLETED" ? "success" : run.status === "FAILED" ? "destructive" : "caution"}
          dot
        />
      ),
    },
    {
      key: "duration_ms",
      header: "Duration",
      sortable: true,
      render: (run: Run) => formatDuration(run.duration_ms),
    },
  ];

  const handleSort = (key: string) => {
    if (sortKey === key) {
      setSortOrder((current) => (current === "asc" ? "desc" : "asc"));
      return;
    }
    setSortKey(key);
    setSortOrder("desc");
  };

  return (
    <div className="space-y-6">
      <GuidanceCard
        title="Activity"
        description="See what the system has done recently, whether anything failed, and what happened inside a specific job."
        whenToUse="Use this first when you want a calm overview of recent work or need to follow up on a job that did not finish cleanly."
        example="Did my last job fail? What happened in that job? Is anything still running?"
      />

      <div className="grid gap-3 md:grid-cols-3">
        <MetricCard
          title="Needs attention"
          value={failedRuns}
          subtitle="Jobs that ended in failure and may need a follow-up check"
          icon={<AlertTriangle className="h-4 w-4" />}
          loading={runsQuery.isLoading}
        />
        <MetricCard
          title="In progress"
          value={activeRuns}
          subtitle="Jobs that have started and have not finished yet"
          icon={<Clock3 className="h-4 w-4" />}
          loading={runsQuery.isLoading}
        />
        <MetricCard
          title="Completed recently"
          value={completedRuns}
          subtitle="Jobs that finished successfully in the current review window"
          icon={<CheckCircle2 className="h-4 w-4" />}
          loading={runsQuery.isLoading}
        />
      </div>

      <div className="grid gap-6 xl:grid-cols-[minmax(0,1.6fr)_24rem]">
        <Card className="min-w-0 rounded-[28px] border-border/70 shadow-sm">
          <CardHeader className="pb-3">
            <CardDescription>Recent jobs</CardDescription>
            <CardTitle className="text-xl">See what the system has done recently</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            {runsQuery.error ? (
              <ErrorAlert message={getErrorMessage(runsQuery.error) || "Failed to load recent jobs"} />
            ) : null}

            <div className="flex flex-wrap items-center justify-between gap-3 text-sm text-muted-foreground">
              <span>
                Showing <span className="font-medium text-foreground">{pagedItems.length}</span> of{" "}
                <span className="font-medium text-foreground">{sorted.length}</span> loaded jobs
              </span>
              <span>
                Sorted by <span className="font-medium text-foreground">{sortKey}</span> in{" "}
                <span className="font-medium text-foreground">{sortOrder}</span> order
              </span>
            </div>

            <DataTable
              columns={columns}
              data={pagedItems}
              loading={runsQuery.isLoading}
              emptyMessage="No jobs have been recorded yet."
              onRowClick={setSelectedRun}
              sortKey={sortKey}
              sortOrder={sortOrder}
              onSort={handleSort}
            />

            {data && totalPages > 1 ? (
              <div className="flex items-center justify-center gap-2">
                <button
                  onClick={() => setPage((current) => Math.max(1, current - 1))}
                  disabled={page === 1}
                  className="rounded border px-3 py-1 text-sm disabled:opacity-50"
                >
                  Prev
                </button>
                <span className="text-xs text-muted-foreground">Page {page} of {totalPages}</span>
                <button
                  onClick={() => setPage((current) => Math.min(totalPages, current + 1))}
                  disabled={page === totalPages}
                  className="rounded border px-3 py-1 text-sm disabled:opacity-50"
                >
                  Next
                </button>
              </div>
            ) : null}
          </CardContent>
        </Card>

        <Card className="rounded-[28px] border-border/70 shadow-sm xl:sticky xl:top-6 xl:self-start">
          <CardHeader className="pb-3">
            <CardDescription>Selected job</CardDescription>
            <CardTitle className="text-xl">What happened in this job</CardTitle>
          </CardHeader>
          <CardContent>
            {/* Activity is the main follow-up surface for running or failed work, so the live panel belongs at the top of this detail rail. */}
            <LiveProgressPanel className="mb-4" />
            {selectedRun ? (
              <div className="space-y-4">
                <div className="flex items-center justify-between gap-3">
                  <StatusBadge
                    label={selectedRun.status === "FAILED" ? "Needs attention" : selectedRun.status === "STARTED" ? "In progress" : "Completed"}
                    severity={selectedRun.status === "COMPLETED" ? "success" : selectedRun.status === "FAILED" ? "destructive" : "caution"}
                    dot
                  />
                  <Button variant="ghost" size="sm" onClick={() => setSelectedRun(null)}>
                    Clear
                  </Button>
                </div>

                <div className="rounded-2xl border bg-muted/20 p-4">
                  <p className="text-sm font-semibold">{formatJobName(selectedRun.operation_type)}</p>
                  <p className="mt-2 text-sm leading-6 text-muted-foreground">{getJobSummary(selectedRun)}</p>
                </div>

                <div className="grid gap-3">
                  <div className="rounded-2xl border bg-muted/20 p-4">
                    <p className="text-xs font-semibold uppercase tracking-[0.2em] text-muted-foreground">Started</p>
                    <p className="mt-2 text-sm">{new Date(selectedRun.started_at).toLocaleString()}</p>
                  </div>
                  <div className="rounded-2xl border bg-muted/20 p-4">
                    <p className="text-xs font-semibold uppercase tracking-[0.2em] text-muted-foreground">Finished</p>
                    <p className="mt-2 text-sm">
                      {selectedRun.completed_at ? new Date(selectedRun.completed_at).toLocaleString() : "Still running"}
                    </p>
                  </div>
                  <div className="rounded-2xl border bg-muted/20 p-4">
                    <p className="text-xs font-semibold uppercase tracking-[0.2em] text-muted-foreground">Duration</p>
                    <p className="mt-2 text-sm">{formatDuration(selectedRun.duration_ms)}</p>
                  </div>
                  {selectedRun.error_message ? (
                    <div className="rounded-2xl border border-destructive/20 bg-destructive/5 p-4">
                      <p className="text-xs font-semibold uppercase tracking-[0.2em] text-destructive">Failure message</p>
                      <p className="mt-2 text-sm text-foreground">{selectedRun.error_message}</p>
                    </div>
                  ) : null}
                </div>

                <Collapsible className="rounded-2xl border bg-background/80">
                  <CollapsibleTrigger asChild>
                    <button type="button" className="flex w-full items-center justify-between gap-3 px-4 py-3 text-left">
                      <div>
                        <p className="text-sm font-semibold">Technical details</p>
                        <p className="text-xs text-muted-foreground">Raw IDs and metadata for support or advanced troubleshooting</p>
                      </div>
                      <Activity className="h-4 w-4 text-muted-foreground" />
                    </button>
                  </CollapsibleTrigger>
                  <CollapsibleContent className="space-y-3 border-t px-4 py-4">
                    <div className="rounded-xl border bg-muted/20 p-3">
                      <p className="text-xs font-semibold uppercase tracking-[0.18em] text-muted-foreground">Job history ID</p>
                      <p className="mt-2 break-all font-mono text-xs">{selectedRun.operation_run_id}</p>
                    </div>
                    <div className="rounded-xl border bg-muted/20 p-3">
                      <p className="text-xs font-semibold uppercase tracking-[0.18em] text-muted-foreground">Linked durable run ID</p>
                      <p className="mt-2 break-all font-mono text-xs">{selectedRun.linked_run_id ?? "Not available"}</p>
                    </div>
                    {selectedRun.context || selectedRun.details ? (
                      <JsonViewer data={selectedRun.context ?? selectedRun.details ?? {}} title="Raw metadata" />
                    ) : null}
                  </CollapsibleContent>
                </Collapsible>
              </div>
            ) : (
              <div className="rounded-2xl border border-dashed bg-muted/20 p-6 text-center">
                <p className="text-sm font-medium">Pick a job to review</p>
                <p className="mt-1 text-sm text-muted-foreground">
                  Select a row to see a plain-English summary first, then open technical details only if you need them.
                </p>
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

function LibraryRulesTab() {
  const queryClient = useQueryClient();
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);
  const [draft, setDraft] = useState<PolicyUpdate | null>(null);
  const [newRoot, setNewRoot] = useState("");

  const policyQuery = useQuery({
    queryKey: queryKeys.policy,
    queryFn: async () => (await getPolicy()).data,
    staleTime: queryOptions.policy.staleTime,
  });

  const policy = (policyQuery.data as Policy | undefined) ?? null;

  useEffect(() => {
    if (!policy) return;
    setDraft({
      selected_policy: policy.canonical_priority.selected_policy,
      naming_strategy: policy.naming.strategy,
      preferred_roots: policy.canonical_priority.preferred_roots,
      integrity_scan_default_mode: policy.integrity.default_scan_mode,
      integrity_issue_min_confidence: policy.integrity.issue_min_confidence,
      integrity_notify_on_high_confidence: policy.integrity.notify_on_high_confidence,
      duplicate_reclaim_archive_root: policy.duplicate_reclaim.archive_root,
      duplicate_reclaim_default_retention_days: policy.duplicate_reclaim.default_retention_days,
      duplicate_reclaim_notify_on_reviewed_safe: policy.duplicate_reclaim.notify_on_reviewed_safe,
      integrity_quarantine_root: policy.retention.quarantine_root,
      integrity_quarantine_retention_days: policy.retention.quarantine_retention_days,
      recycle_bin_root: policy.retention.recycle_bin_root,
      recycle_purge_days: policy.retention.recycle_purge_days,
      automation_mode: policy.automation.mode,
      recanonicalization_enabled: policy.recanonicalization.enabled,
      version: policy.metadata.version,
    });
  }, [policy]);

  const handleSave = async () => {
    if (!draft) return;
    setSaving(true);
    setError(null);
    setSuccess(false);
    try {
      const res = await updatePolicy(draft);
      setDraft({
        selected_policy: res.data.canonical_priority.selected_policy,
        naming_strategy: res.data.naming.strategy,
        preferred_roots: res.data.canonical_priority.preferred_roots,
        integrity_scan_default_mode: res.data.integrity.default_scan_mode,
        integrity_issue_min_confidence: res.data.integrity.issue_min_confidence,
        integrity_notify_on_high_confidence: res.data.integrity.notify_on_high_confidence,
        duplicate_reclaim_archive_root: res.data.duplicate_reclaim.archive_root,
        duplicate_reclaim_default_retention_days: res.data.duplicate_reclaim.default_retention_days,
        duplicate_reclaim_notify_on_reviewed_safe: res.data.duplicate_reclaim.notify_on_reviewed_safe,
        integrity_quarantine_root: res.data.retention.quarantine_root,
        integrity_quarantine_retention_days: res.data.retention.quarantine_retention_days,
        recycle_bin_root: res.data.retention.recycle_bin_root,
        recycle_purge_days: res.data.retention.recycle_purge_days,
        automation_mode: res.data.automation.mode,
        recanonicalization_enabled: res.data.recanonicalization.enabled,
        version: res.data.metadata.version,
      });
      await invalidateReadsAfterPolicyUpdate(queryClient);
      setSuccess(true);
      setTimeout(() => setSuccess(false), 3000);
    } catch (err: unknown) {
      setError(getErrorMessage(err) || "Failed to update library rules");
    } finally {
      setSaving(false);
    }
  };

  const addRoot = () => {
    const trimmed = newRoot.trim();
    if (!trimmed || !draft || draft.preferred_roots.includes(trimmed)) return;
    setDraft((prev) =>
      prev
        ? {
            ...prev,
            preferred_roots: [...prev.preferred_roots, trimmed],
          }
        : prev,
    );
    setNewRoot("");
  };

  const removeRoot = (root: string) => {
    setDraft((prev) =>
      prev
        ? {
            ...prev,
            preferred_roots: prev.preferred_roots.filter((item) => item !== root),
          }
        : prev,
    );
  };

  const combinedError = error || getErrorMessage(policyQuery.error);
  const hasChanges =
    draft !== null &&
    policy !== null &&
    JSON.stringify(draft) !==
      JSON.stringify({
        selected_policy: policy.canonical_priority.selected_policy,
        naming_strategy: policy.naming.strategy,
        preferred_roots: policy.canonical_priority.preferred_roots,
        integrity_scan_default_mode: policy.integrity.default_scan_mode,
        integrity_issue_min_confidence: policy.integrity.issue_min_confidence,
        integrity_notify_on_high_confidence: policy.integrity.notify_on_high_confidence,
        duplicate_reclaim_archive_root: policy.duplicate_reclaim.archive_root,
        duplicate_reclaim_default_retention_days: policy.duplicate_reclaim.default_retention_days,
        duplicate_reclaim_notify_on_reviewed_safe: policy.duplicate_reclaim.notify_on_reviewed_safe,
        integrity_quarantine_root: policy.retention.quarantine_root,
        integrity_quarantine_retention_days: policy.retention.quarantine_retention_days,
        recycle_bin_root: policy.retention.recycle_bin_root,
        recycle_purge_days: policy.retention.recycle_purge_days,
        automation_mode: policy.automation.mode,
        recanonicalization_enabled: policy.recanonicalization.enabled,
        version: policy.metadata.version,
      });

  const decisionPreview = useMemo(
    () => policy?.tie_breaker_rules.effective_order.map(explainPolicyRule) ?? [],
    [policy],
  );

  if (policyQuery.isLoading && !policy) {
    return <div className="text-sm text-muted-foreground">Loading library rules…</div>;
  }

  if (!draft || !policy) {
    return <div className="space-y-6">{combinedError ? <ErrorAlert message={combinedError} onDismiss={() => setError(null)} /> : null}</div>;
  }

  const prefersRoots = draft.selected_policy === "PREFER_ROOT";

  return (
    <div className="space-y-6">
      <GuidanceCard
        title="Library Rules"
        description="Set the default library rules the app should use when it chooses the main version and builds canonical and duplicate filenames."
        whenToUse="Use this when duplicate groups look broadly right, but the saved defaults should steer future batches toward different main-file or naming behavior."
        example="Should the archive copy win? Should duplicates keep a shared family name? Should these changes follow through automatically?"
      />

      {combinedError ? <ErrorAlert message={combinedError} onDismiss={() => setError(null)} /> : null}
      {success ? <ErrorAlert message="Library rules saved successfully" severity="info" /> : null}

      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-5">
        <MetricCard
          title="Current rule"
          value={policyOptions.find((option) => option.value === draft.selected_policy)?.title ?? draft.selected_policy}
          subtitle="How the main version is chosen"
          icon={<ShieldCheck className="h-4 w-4" />}
        />
        <MetricCard
          title="Default naming"
          value={
            namingStrategyOptions.find((option) => option.value === draft.naming_strategy)?.title ??
            draft.naming_strategy
          }
          subtitle="How canonical and duplicate filenames are built by default"
          icon={<Fingerprint className="h-4 w-4" />}
        />
        <MetricCard
          title="Preferred folders"
          value={draft.preferred_roots.length}
          subtitle={prefersRoots ? "Used in the current rule" : "Saved for when folder preference is enabled"}
          icon={<FolderTree className="h-4 w-4" />}
        />
        <MetricCard
          title="Auto follow-through"
          value={draft.recanonicalization_enabled ? "On" : "Off"}
          subtitle="Whether rule changes can propagate automatically"
          icon={<Sparkles className="h-4 w-4" />}
        />
        <MetricCard
          title="Change state"
          value={hasChanges ? "Unsaved edits" : "In sync"}
          subtitle={`Rules version ${policy.metadata.version}`}
          icon={<GitCompareArrows className="h-4 w-4" />}
        />
        <MetricCard
          title="Integrity default"
          value={draft.integrity_scan_default_mode}
          subtitle={`Queue threshold ${(draft.integrity_issue_min_confidence * 100).toFixed(0)}%`}
          icon={<AlertTriangle className="h-4 w-4" />}
        />
        <MetricCard
          title="Reclaim retention"
          value={`${draft.duplicate_reclaim_default_retention_days} days`}
          subtitle={draft.duplicate_reclaim_notify_on_reviewed_safe ? "Notify when safe-to-reclaim" : "No reclaim notifications"}
          icon={<FolderClock className="h-4 w-4" />}
        />
        <MetricCard
          title="Recycle purge"
          value={`${draft.recycle_purge_days} days`}
          subtitle="Manual CTA only"
          icon={<Trash2 className="h-4 w-4" />}
        />
        <MetricCard
          title="Automation"
          value="Notify Only"
          subtitle="No file mutations run automatically"
          icon={<Workflow className="h-4 w-4" />}
        />
      </div>

      <Card className="rounded-[28px] border-border/70 shadow-sm">
        <CardHeader className="pb-3">
          <CardDescription>Main rule</CardDescription>
          <CardTitle className="text-xl">How should the app choose the main version?</CardTitle>
        </CardHeader>
        <CardContent className="grid gap-4">
          {policyOptions.map((option) => (
            <PolicyChoiceCard
              key={option.value}
              value={option.value}
              selected={draft.selected_policy === option.value}
              title={option.title}
              description={option.description}
              helper={option.helper}
              onSelect={(value) => setDraft((prev) => (prev ? { ...prev, selected_policy: value } : prev))}
            />
          ))}
        </CardContent>
      </Card>

      <Card className="rounded-[28px] border-border/70 shadow-sm">
        <CardHeader className="pb-3">
          <CardDescription>Default naming rule</CardDescription>
          <CardTitle className="text-xl">How should filenames be built after the main version is chosen?</CardTitle>
        </CardHeader>
        <CardContent className="grid gap-4">
          <p className="text-sm leading-6 text-muted-foreground">
            These are saved library defaults. The Organize wizard will start from them for each batch, then let you adjust owner, context, and naming strategy for a specific run if needed.
          </p>
          {namingStrategyOptions.map((option) => (
            <PolicyChoiceCard
              key={option.value}
              value={option.value}
              selected={draft.naming_strategy === option.value}
              title={option.title}
              description={option.description}
              helper={option.helper}
              onSelect={(value) => setDraft((prev) => (prev ? { ...prev, naming_strategy: value } : prev))}
            />
          ))}
        </CardContent>
      </Card>

      <div className="grid gap-4 xl:grid-cols-[minmax(0,1.2fr)_minmax(0,1fr)]">
        <Card className="rounded-[28px] border-border/70 shadow-sm">
          <CardHeader className="pb-3">
            <CardDescription>Folders to prefer</CardDescription>
            <CardTitle className="text-xl">Which folders should win when the same file appears twice?</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <p className="text-sm leading-6 text-muted-foreground">
              If you choose <span className="font-medium text-foreground">Prefer files from specific folders</span>,
              the app will favor copies from the folders listed here before using other tie-breakers.
            </p>
            <div className="flex flex-wrap gap-2">
              {draft.preferred_roots.map((root) => (
                <span
                  key={root}
                  className="inline-flex items-center gap-2 rounded-full border border-border/70 bg-background px-3 py-2 text-sm"
                >
                  <span className="font-mono text-xs">{root}</span>
                  <button type="button" onClick={() => removeRoot(root)} aria-label={`Remove ${root}`}>
                    <X className="h-3.5 w-3.5 text-muted-foreground hover:text-foreground" />
                  </button>
                </span>
              ))}
              {!draft.preferred_roots.length ? (
                <div className="rounded-2xl border border-dashed border-border/70 bg-muted/25 px-4 py-3 text-sm text-muted-foreground">
                  No preferred folders yet. Add a folder such as <span className="font-mono">/media/archive</span>.
                </div>
              ) : null}
            </div>
            <div className="flex gap-2">
              <Input
                value={newRoot}
                onChange={(event) => setNewRoot(event.target.value)}
                onKeyDown={(event) => event.key === "Enter" && addRoot()}
                placeholder="/media/archive"
                className="font-mono"
              />
              <Button type="button" variant="outline" onClick={addRoot}>
                <Plus className="mr-2 h-4 w-4" />
                Add folder
              </Button>
            </div>
            <div className="rounded-2xl border border-border/70 bg-background/80 p-4">
              <p className="text-sm font-semibold text-foreground">
                {prefersRoots ? "This rule is active now" : "This rule is saved, but not active"}
              </p>
              <p className="mt-1 text-sm leading-6 text-muted-foreground">
                {prefersRoots
                  ? "The app will currently prefer files from these folders whenever duplicate copies are compared."
                  : "These folders will be used if you switch the main rule to prefer files from specific folders."}
              </p>
            </div>
          </CardContent>
        </Card>

        <div className="space-y-4">
          <Card className="rounded-[28px] border-border/70 shadow-sm">
            <CardHeader className="pb-3">
              <CardDescription>Apply changes automatically</CardDescription>
              <CardTitle className="text-xl">Should the library follow through after you save?</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="flex items-center justify-between gap-4 rounded-[24px] border border-border/70 bg-background/80 p-4">
                <div>
                  <p className="text-sm font-semibold text-foreground">Automatic follow-through</p>
                  <p className="mt-1 text-sm leading-6 text-muted-foreground">
                    When turned on, the library can update main-file choices after you change these rules.
                  </p>
                </div>
                <Switch
                  checked={draft.recanonicalization_enabled}
                  onCheckedChange={(checked) =>
                    setDraft((prev) => (prev ? { ...prev, recanonicalization_enabled: checked } : prev))
                  }
                />
              </div>
              <div className="rounded-2xl border border-border/70 bg-background/80 p-4">
                <p className="text-sm font-semibold text-foreground">
                  {draft.recanonicalization_enabled ? "Automatic mode is on" : "Review-first mode is on"}
                </p>
                <p className="mt-1 text-sm leading-6 text-muted-foreground">
                  {draft.recanonicalization_enabled
                    ? "Use this when you trust the rule change and want the library to keep itself aligned."
                    : "Use this when you want to change the rule now but review downstream impact before main-file choices are updated."}
                </p>
              </div>
            </CardContent>
          </Card>

          <Card className="rounded-[28px] border-border/70 shadow-sm">
            <CardHeader className="pb-3">
              <CardDescription>How decisions are made right now</CardDescription>
              <CardTitle className="text-xl">Current decision order</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              {decisionPreview.map((item) => (
                <div key={item} className="flex items-start gap-3 rounded-2xl border border-border/70 bg-background/80 p-4">
                  <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-primary" />
                  <p className="text-sm leading-6 text-foreground">{item}</p>
                </div>
              ))}
            </CardContent>
          </Card>
        </div>
      </div>

      <div className="grid gap-4 xl:grid-cols-3">
        <Card className="rounded-[28px] border-border/70 shadow-sm">
          <CardHeader className="pb-3">
            <CardDescription>Integrity Defaults</CardDescription>
            <CardTitle className="text-xl">How should integrity review start?</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-2">
              <p className="text-sm font-semibold text-foreground">Default scan mode</p>
              <div className="flex gap-2">
                {(["FAST", "DEEP"] as const).map((mode) => (
                  <Button
                    key={mode}
                    type="button"
                    variant={draft.integrity_scan_default_mode === mode ? "default" : "outline"}
                    onClick={() => setDraft((prev) => (prev ? { ...prev, integrity_scan_default_mode: mode } : prev))}
                  >
                    {mode}
                  </Button>
                ))}
              </div>
            </div>
            <div className="space-y-2">
              <Label htmlFor="integrity-min-confidence">Queue threshold</Label>
              <Input
                id="integrity-min-confidence"
                type="number"
                min="0"
                max="1"
                step="0.01"
                value={draft.integrity_issue_min_confidence}
                onChange={(event) =>
                  setDraft((prev) =>
                    prev ? { ...prev, integrity_issue_min_confidence: Number(event.target.value || 0) } : prev,
                  )
                }
              />
              <p className="text-xs text-muted-foreground">Unreviewed issues at or above this confidence are highlighted as high-confidence recommendations.</p>
            </div>
            <div className="flex items-center justify-between gap-4 rounded-[24px] border border-border/70 bg-background/80 p-4">
              <div>
                <p className="text-sm font-semibold text-foreground">Notify on high-confidence issues</p>
                <p className="mt-1 text-sm leading-6 text-muted-foreground">Show stronger recommendations, but do not quarantine files automatically.</p>
              </div>
              <Switch
                checked={draft.integrity_notify_on_high_confidence}
                onCheckedChange={(checked) =>
                  setDraft((prev) => (prev ? { ...prev, integrity_notify_on_high_confidence: checked } : prev))
                }
              />
            </div>
          </CardContent>
        </Card>

        <Card className="rounded-[28px] border-border/70 shadow-sm">
          <CardHeader className="pb-3">
            <CardDescription>Reclaim Defaults</CardDescription>
            <CardTitle className="text-xl">How should duplicate reclaim be prepared?</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="reclaim-archive-root">Archive root</Label>
              <Input
                id="reclaim-archive-root"
                value={draft.duplicate_reclaim_archive_root}
                onChange={(event) =>
                  setDraft((prev) => (prev ? { ...prev, duplicate_reclaim_archive_root: event.target.value } : prev))
                }
                className="font-mono"
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="reclaim-retention-days">Default retention days</Label>
              <Input
                id="reclaim-retention-days"
                type="number"
                min="1"
                step="1"
                value={draft.duplicate_reclaim_default_retention_days}
                onChange={(event) =>
                  setDraft((prev) =>
                    prev ? { ...prev, duplicate_reclaim_default_retention_days: Number(event.target.value || 1) } : prev,
                  )
                }
              />
            </div>
            <div className="flex items-center justify-between gap-4 rounded-[24px] border border-border/70 bg-background/80 p-4">
              <div>
                <p className="text-sm font-semibold text-foreground">Notify when reviewed-safe groups are ready</p>
                <p className="mt-1 text-sm leading-6 text-muted-foreground">Surface reclaim-ready groups clearly, but keep the archive move manual.</p>
              </div>
              <Switch
                checked={draft.duplicate_reclaim_notify_on_reviewed_safe}
                onCheckedChange={(checked) =>
                  setDraft((prev) => (prev ? { ...prev, duplicate_reclaim_notify_on_reviewed_safe: checked } : prev))
                }
              />
            </div>
          </CardContent>
        </Card>

        <Card className="rounded-[28px] border-border/70 shadow-sm">
          <CardHeader className="pb-3">
            <CardDescription>Retention Defaults</CardDescription>
            <CardTitle className="text-xl">Where should reversible file actions live?</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="integrity-quarantine-root">Integrity quarantine root</Label>
              <Input
                id="integrity-quarantine-root"
                value={draft.integrity_quarantine_root}
                onChange={(event) =>
                  setDraft((prev) => (prev ? { ...prev, integrity_quarantine_root: event.target.value } : prev))
                }
                className="font-mono"
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="recycle-bin-root">Recycle bin root</Label>
              <Input
                id="recycle-bin-root"
                value={draft.recycle_bin_root}
                onChange={(event) =>
                  setDraft((prev) => (prev ? { ...prev, recycle_bin_root: event.target.value } : prev))
                }
                className="font-mono"
              />
            </div>
            <div className="grid gap-3 sm:grid-cols-2">
              <div className="space-y-2">
                <Label htmlFor="quarantine-retention-days">Quarantine retention days</Label>
                <Input
                  id="quarantine-retention-days"
                  type="number"
                  min="1"
                  step="1"
                  value={draft.integrity_quarantine_retention_days}
                  onChange={(event) =>
                    setDraft((prev) =>
                      prev ? { ...prev, integrity_quarantine_retention_days: Number(event.target.value || 1) } : prev,
                    )
                  }
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="recycle-purge-days">Recycle purge days</Label>
                <Input
                  id="recycle-purge-days"
                  type="number"
                  min="1"
                  step="1"
                  value={draft.recycle_purge_days}
                  onChange={(event) =>
                    setDraft((prev) => (prev ? { ...prev, recycle_purge_days: Number(event.target.value || 1) } : prev))
                  }
                />
              </div>
            </div>
          </CardContent>
        </Card>
      </div>

      <Card className="rounded-[28px] border-border/70 shadow-sm">
        <CardHeader className="pb-3">
          <CardDescription>Automation Status</CardDescription>
          <CardTitle className="text-xl">Notify only</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="flex items-center gap-2">
            <StatusBadge label={draft.automation_mode.replaceAll("_", " ")} severity="info" />
            <StatusBadge label="Manual file actions only" severity="success" />
          </div>
          <p className="text-sm leading-6 text-muted-foreground">
            These settings control defaults, recommendations, and preselected values. They do not quarantine, reclaim, recycle, or purge files automatically.
          </p>
        </CardContent>
      </Card>

      <Collapsible className="rounded-[28px] border border-border/70 bg-card/95 shadow-sm">
        <CollapsibleTrigger asChild>
          <button type="button" className="flex w-full items-center justify-between gap-3 px-6 py-5 text-left">
            <div>
              <p className="text-sm font-semibold text-foreground">Technical details</p>
              <p className="mt-1 text-sm text-muted-foreground">
                Raw policy identifiers, deterministic order, version, and update metadata.
              </p>
            </div>
            <ChevronDown className="h-4 w-4 text-muted-foreground" />
          </button>
        </CollapsibleTrigger>
        <CollapsibleContent className="space-y-4 border-t px-6 py-5">
          <div className="grid gap-4 md:grid-cols-2">
            <div className="rounded-2xl border border-border/70 bg-background/80 p-4">
              <p className="text-xs font-semibold uppercase tracking-[0.22em] text-muted-foreground">Policy name</p>
              <p className="mt-2 font-mono text-sm text-foreground">{policy.tie_breaker_rules.policy_name}</p>
            </div>
            <div className="rounded-2xl border border-border/70 bg-background/80 p-4">
              <p className="text-xs font-semibold uppercase tracking-[0.22em] text-muted-foreground">Policy version</p>
              <p className="mt-2 font-mono text-sm text-foreground">{policy.tie_breaker_rules.policy_version}</p>
            </div>
            <div className="rounded-2xl border border-border/70 bg-background/80 p-4">
              <p className="text-xs font-semibold uppercase tracking-[0.22em] text-muted-foreground">Rules version</p>
              <p className="mt-2 font-mono text-sm text-foreground">{policy.metadata.version}</p>
            </div>
            <div className="rounded-2xl border border-border/70 bg-background/80 p-4">
              <p className="text-xs font-semibold uppercase tracking-[0.22em] text-muted-foreground">Updated at</p>
              <p className="mt-2 text-sm text-foreground">{formatPolicyUpdatedAt(policy.metadata.updated_at)}</p>
            </div>
          </div>
          <div className="rounded-2xl border border-border/70 bg-background/80 p-4">
            <p className="text-xs font-semibold uppercase tracking-[0.22em] text-muted-foreground">Deterministic decision order</p>
            <div className="mt-3 space-y-2">
              {policy.tie_breaker_rules.effective_order.map((rule) => (
                <div key={rule} className="rounded-xl border border-border/70 bg-muted/20 px-3 py-2 font-mono text-xs text-foreground">
                  {rule}
                </div>
              ))}
            </div>
          </div>
        </CollapsibleContent>
      </Collapsible>

      <Card className="rounded-[28px] border-border/70 shadow-sm">
        <CardContent className="flex flex-col gap-4 p-5 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <p className="text-sm font-semibold text-foreground">
              {hasChanges ? "You have unsaved changes" : "No changes waiting to be saved"}
            </p>
            <p className="mt-1 text-sm text-muted-foreground">
              {hasChanges
                ? "Review your rule choice, preferred folders, and follow-through setting before saving."
                : "Your saved library rules are in sync with the current screen."}
            </p>
          </div>
          <Button onClick={handleSave} disabled={saving || !hasChanges} size="lg" className="sm:min-w-56">
            {saving ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Save className="mr-2 h-4 w-4" />}
            {saving ? "Saving rules" : hasChanges ? "Save library rules" : "No changes to save"}
          </Button>
        </CardContent>
      </Card>
    </div>
  );
}

function FileHistoryTab() {
  const [error, setError] = useState<string | null>(null);
  const [task, setTask] = useState<FileHistoryTask>("history");
  const [queryInput, setQueryInput] = useState("");
  const [queryResults, setQueryResults] = useState<MediaFileRecord[]>([]);
  const [selectedRecord, setSelectedRecord] = useState<MediaFileRecord | null>(null);
  const [queryLoading, setQueryLoading] = useState(false);

  const analyticsQuery = useQuery({
    queryKey: queryKeys.analytics,
    queryFn: async () => (await getAnalytics()).data,
    staleTime: queryOptions.analytics.staleTime,
  });

  const analytics = (analyticsQuery.data as AnalyticsSummary | undefined) ?? null;

  useEffect(() => {
    if (!selectedRecord && queryResults.length > 0) {
      setSelectedRecord(queryResults[0]);
    }
  }, [queryResults, selectedRecord]);

  const tasks = [
    {
      id: "history" as const,
      title: "I know the file path",
      description: "View a file's history when you know where it lived on disk.",
      helper: "Good for questions like “Has this exact path existed before?”",
      icon: <History className="h-4 w-4" />,
    },
    {
      id: "hash" as const,
      title: "I know part of the fingerprint",
      description: "Find records using part of a file fingerprint if the path changed.",
      helper: "A fingerprint is the unique hash value saved for a file.",
      icon: <Fingerprint className="h-4 w-4" />,
    },
    {
      id: "status" as const,
      title: "I want to browse by file state",
      description: "See files by state such as processed or deleted.",
      helper: "Use one of the built-in examples if you are unsure what to type.",
      icon: <Workflow className="h-4 w-4" />,
    },
    {
      id: "reappearances" as const,
      title: "I want to see files that came back",
      description: "Check whether a path was deleted before and later appeared again.",
      helper: "Useful for repeated imports or folders that change over time.",
      icon: <FolderClock className="h-4 w-4" />,
    },
  ];

  const taskHelp = useMemo(() => {
    if (task === "hash") {
      return {
        label: "File fingerprint",
        placeholder: "Example: a1b2c3d4",
        helper: "Paste the first part of the file fingerprint. You do not need the entire value.",
        buttonLabel: "Find file",
      };
    }
    if (task === "status") {
      return {
        label: "File state",
        placeholder: "Example: PROCESSED",
        helper: "Type a file state such as INGESTED, PROCESSED, or DELETED.",
        buttonLabel: "Browse state",
      };
    }
    if (task === "reappearances") {
      return {
        label: "File path",
        placeholder: "Example: /media/events/IMG_0001.JPG",
        helper: "Enter the path you want to check for deleted-then-returned history.",
        buttonLabel: "Check returned files",
      };
    }
    return {
      label: "File path",
      placeholder: "Example: /media/events/IMG_0001.JPG",
      helper: "Enter the path you want to investigate. This is the best first step when you know the file location.",
      buttonLabel: "View history",
    };
  }, [task]);

  const executeQuery = async () => {
    setQueryLoading(true);
    setQueryResults([]);
    setSelectedRecord(null);
    setError(null);

    try {
      if (task === "hash") {
        const response = await getMediaByHash(queryInput);
        setQueryResults(response.data);
      } else if (task === "history") {
        const response = await getMediaHistory(queryInput);
        setQueryResults(response.data);
      } else if (task === "status") {
        const response = await getMediaByStatus(queryInput.toUpperCase());
        setQueryResults(response.data.items);
      } else {
        const response = await getReappearances(queryInput);
        setQueryResults(response.data.items);
      }
    } catch (err: unknown) {
      setError(getErrorMessage(err) || "Search failed");
    } finally {
      setQueryLoading(false);
    }
  };

  const columns = [
    {
      key: "current_path",
      header: "File",
      render: (record: MediaFileRecord) => (
        <div>
          <p className="truncate font-medium text-foreground">{record.current_path}</p>
          <p className="truncate text-xs text-muted-foreground">
            First seen {record.discovered_at ? new Date(record.discovered_at).toLocaleDateString() : "unknown"}
          </p>
        </div>
      ),
    },
    {
      key: "status",
      header: "State",
      render: (record: MediaFileRecord) => (
        <StatusBadge label={formatFileState(record.status)} severity={record.status === "DELETED" ? "destructive" : "neutral"} />
      ),
    },
    {
      key: "size_bytes",
      header: "Size",
      render: (record: MediaFileRecord) => formatSize(record.size_bytes),
    },
  ];

  const combinedError = error || getErrorMessage(analyticsQuery.error);

  return (
    <div className="space-y-6">
      <GuidanceCard
        title="File History"
        description="Look up what the system knows about a file without needing to understand the underlying ledger model."
        whenToUse="Use this when you know a path, part of a file fingerprint, or want to browse files by their current state."
        example="What do we know about this file? Has this path existed before? Was this file deleted and later seen again?"
      />

      {combinedError ? <ErrorAlert message={combinedError} onDismiss={() => setError(null)} /> : null}

      <div className="grid gap-3 md:grid-cols-3">
        <MetricCard
          title="Tracked files"
          value={analytics?.total_records ?? 0}
          subtitle="Records currently available for lookup"
          icon={<FileSearch className="h-4 w-4" />}
          loading={analyticsQuery.isLoading}
        />
        <MetricCard
          title="Average file size"
          value={analytics ? formatSize(analytics.avg_file_size) : "—"}
          subtitle="Helpful context while reviewing file records"
          icon={<Activity className="h-4 w-4" />}
          loading={analyticsQuery.isLoading}
        />
        <MetricCard
          title="Deleted files"
          value={analytics?.by_status?.DELETED ?? 0}
          subtitle="A quick signal for how much deleted history exists"
          icon={<XCircle className="h-4 w-4" />}
          loading={analyticsQuery.isLoading}
        />
      </div>

      <div className="grid gap-6 xl:grid-cols-[minmax(0,1.4fr)_24rem]">
        <div className="space-y-6">
          <Card className="rounded-[28px] border-border/70 shadow-sm">
            <CardHeader className="pb-3">
              <CardDescription>Choose how you want to look up a file</CardDescription>
              <CardTitle className="text-xl">Find a file in the way that feels natural</CardTitle>
            </CardHeader>
            <CardContent className="grid gap-3 md:grid-cols-2">
              {tasks.map((item) => {
                const active = item.id === task;
                return (
                  <button
                    key={item.id}
                    type="button"
                    onClick={() => {
                      setTask(item.id);
                      setQueryInput("");
                      setQueryResults([]);
                      setSelectedRecord(null);
                      setError(null);
                    }}
                    className={`rounded-2xl border p-4 text-left transition-colors ${
                      active
                        ? "border-primary/30 bg-primary/8 shadow-sm"
                        : "border-border/70 bg-background/80 hover:border-primary/20 hover:bg-primary/5"
                    }`}
                  >
                    <div className="flex items-start gap-3">
                      <div className="rounded-xl border border-border/70 bg-card p-2">{item.icon}</div>
                      <div className="min-w-0">
                        <p className="text-sm font-semibold">{item.title}</p>
                        <p className="mt-1 text-sm leading-6 text-muted-foreground">{item.description}</p>
                        <p className="mt-2 text-xs text-muted-foreground">{item.helper}</p>
                      </div>
                    </div>
                  </button>
                );
              })}
            </CardContent>
          </Card>

          <Card className="rounded-[28px] border-border/70 shadow-sm">
            <CardHeader className="pb-3">
              <CardDescription>{tasks.find((item) => item.id === task)?.title}</CardDescription>
              <CardTitle className="text-xl">{taskHelp.buttonLabel}</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="space-y-2">
                <label className="text-xs font-semibold uppercase tracking-[0.2em] text-muted-foreground">{taskHelp.label}</label>
                <Input
                  value={queryInput}
                  onChange={(event) => setQueryInput(event.target.value)}
                  placeholder={taskHelp.placeholder}
                  className={task === "hash" ? "font-mono" : undefined}
                />
                <p className="text-sm text-muted-foreground">{taskHelp.helper}</p>
              </div>

              {task === "status" ? (
                <div className="flex flex-wrap gap-2">
                  {STATUS_EXAMPLES.map((status) => (
                    <Button key={status} type="button" variant="outline" size="sm" onClick={() => setQueryInput(status)}>
                      {status}
                    </Button>
                  ))}
                </div>
              ) : null}

              <div className="flex flex-wrap gap-3">
                <Button onClick={executeQuery} disabled={queryLoading || !queryInput.trim()}>
                  <Search className="mr-2 h-4 w-4" />
                  {taskHelp.buttonLabel}
                </Button>
                {task === "hash" ? (
                  <p className="text-sm text-muted-foreground">Tip: you can paste only the beginning of the fingerprint.</p>
                ) : null}
              </div>

              <DataTable
                columns={columns}
                data={queryResults}
                loading={queryLoading}
                emptyMessage="No file records yet. Run a search above to see matching file history."
                onRowClick={setSelectedRecord}
              />
            </CardContent>
          </Card>
        </div>

        <Card className="rounded-[28px] border-border/70 shadow-sm xl:sticky xl:top-6 xl:self-start">
          <CardHeader className="pb-3">
            <CardDescription>Selected file</CardDescription>
            <CardTitle className="text-xl">What we know about this file</CardTitle>
          </CardHeader>
          <CardContent>
            {selectedRecord ? (
              <div className="space-y-4">
                <div className="rounded-2xl border bg-muted/20 p-4">
                  <p className="truncate text-sm font-semibold text-foreground">{selectedRecord.current_path}</p>
                  <p className="mt-2 text-sm leading-6 text-muted-foreground">
                    This record is currently marked as {formatFileState(selectedRecord.status)} and was first seen{" "}
                    {selectedRecord.discovered_at ? new Date(selectedRecord.discovered_at).toLocaleString() : "at an unknown time"}.
                  </p>
                </div>

                <div className="grid gap-3">
                  <div className="rounded-2xl border bg-muted/20 p-4">
                    <p className="text-xs font-semibold uppercase tracking-[0.2em] text-muted-foreground">File state</p>
                    <div className="mt-2">
                      <StatusBadge label={formatFileState(selectedRecord.status)} severity={selectedRecord.status === "DELETED" ? "destructive" : "neutral"} />
                    </div>
                  </div>
                  <div className="rounded-2xl border bg-muted/20 p-4">
                    <p className="text-xs font-semibold uppercase tracking-[0.2em] text-muted-foreground">File size</p>
                    <p className="mt-2 text-sm">{formatSize(selectedRecord.size_bytes)}</p>
                  </div>
                  <div className="rounded-2xl border bg-muted/20 p-4">
                    <p className="text-xs font-semibold uppercase tracking-[0.2em] text-muted-foreground">First seen</p>
                    <p className="mt-2 text-sm">{selectedRecord.discovered_at ? new Date(selectedRecord.discovered_at).toLocaleString() : "Unknown"}</p>
                  </div>
                  <div className="rounded-2xl border bg-muted/20 p-4">
                    <p className="text-xs font-semibold uppercase tracking-[0.2em] text-muted-foreground">Last ingested</p>
                    <p className="mt-2 text-sm">{selectedRecord.ingested_at ? new Date(selectedRecord.ingested_at).toLocaleString() : "Not available"}</p>
                  </div>
                </div>

                <Collapsible className="rounded-2xl border bg-background/80">
                  <CollapsibleTrigger asChild>
                    <button type="button" className="flex w-full items-center justify-between gap-3 px-4 py-3 text-left">
                      <div>
                        <p className="text-sm font-semibold">Technical details</p>
                        <p className="text-xs text-muted-foreground">Original paths and the stored fingerprint for advanced review</p>
                      </div>
                      <FileSearch className="h-4 w-4 text-muted-foreground" />
                    </button>
                  </CollapsibleTrigger>
                  <CollapsibleContent className="space-y-3 border-t px-4 py-4">
                    <div className="rounded-xl border bg-muted/20 p-3">
                      <p className="text-xs font-semibold uppercase tracking-[0.18em] text-muted-foreground">Current path</p>
                      <p className="mt-2 break-all font-mono text-xs">{selectedRecord.current_path}</p>
                    </div>
                    <div className="rounded-xl border bg-muted/20 p-3">
                      <p className="text-xs font-semibold uppercase tracking-[0.18em] text-muted-foreground">Discovered path</p>
                      <p className="mt-2 break-all font-mono text-xs">{selectedRecord.discovered_path}</p>
                    </div>
                    <div className="rounded-xl border bg-muted/20 p-3">
                      <p className="text-xs font-semibold uppercase tracking-[0.18em] text-muted-foreground">File fingerprint</p>
                      <p className="mt-2 break-all font-mono text-xs">{selectedRecord.hash_sha256}</p>
                    </div>
                  </CollapsibleContent>
                </Collapsible>
              </div>
            ) : (
              <div className="rounded-2xl border border-dashed bg-muted/20 p-6 text-center">
                <p className="text-sm font-medium">Search for a file to begin</p>
                <p className="mt-1 text-sm text-muted-foreground">
                  Once you run a search, select a result to see a calmer explanation of the file record.
                </p>
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

function IntegrityCheckTab() {
  const [error, setError] = useState<string | null>(null);
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

  const executeAudit = async () => {
    setAuditLoading(true);
    setAuditResults([]);
    setError(null);

    try {
      const response = await getHashAudit({
        sample_limit: Number(auditSampleLimit),
        root_path: auditRootPath || undefined,
      });
      setAuditResults(response.data);
    } catch (err: unknown) {
      setError(getErrorMessage(err) || "Integrity check failed");
    } finally {
      setAuditLoading(false);
    }
  };

  const auditColumns = [
    {
      key: "path",
      header: "File",
      render: (row: HashAuditResult) => (
        <div>
          <p className="truncate font-medium text-foreground">{row.path}</p>
          <p className="text-xs text-muted-foreground">{row.audit_note}</p>
        </div>
      ),
    },
    {
      key: "status",
      header: "Result",
      render: (row: HashAuditResult) => (
        <StatusBadge
          label={formatFileState(row.status)}
          severity={row.status.toUpperCase().includes("MISMATCH") ? "destructive" : "neutral"}
        />
      ),
    },
    {
      key: "hash",
      header: "Fingerprint",
      className: "font-mono text-xs",
      render: (row: HashAuditResult) => `${row.hash.slice(0, 16)}…`,
    },
  ];

  const combinedError = error || getErrorMessage(analyticsQuery.error);

  return (
    <div className="space-y-6">
      <GuidanceCard
        title="Integrity Check"
        description="Run a read-only health check on stored file fingerprints when you want extra confidence that file records still line up with the files on disk."
        whenToUse="Use this only when you are troubleshooting or validating the library after unexpected changes. Most users will not need it every day."
        example="Can I check whether file records look healthy? Do any fingerprints look missing or mismatched?"
      />

      {combinedError ? <ErrorAlert message={combinedError} onDismiss={() => setError(null)} /> : null}

      <div className="grid gap-3 md:grid-cols-3">
        <MetricCard
          title="Tracked files"
          value={analytics?.total_records ?? 0}
          subtitle="Overall records available in the library history"
          icon={<ShieldCheck className="h-4 w-4" />}
          loading={analyticsQuery.isLoading}
        />
        <MetricCard
          title="Processed files"
          value={analytics?.by_status?.PROCESSED ?? 0}
          subtitle="Files currently marked as processed"
          icon={<CheckCircle2 className="h-4 w-4" />}
          loading={analyticsQuery.isLoading}
        />
        <MetricCard
          title="Deleted history"
          value={analytics?.by_status?.DELETED ?? 0}
          subtitle="Deleted rows are skipped during integrity review"
          icon={<XCircle className="h-4 w-4" />}
          loading={analyticsQuery.isLoading}
        />
      </div>

      <Card className="rounded-[28px] border-border/70 shadow-sm">
        <CardHeader className="pb-3">
          <CardDescription>Read-only troubleshooting tool</CardDescription>
          <CardTitle className="text-xl">Check library integrity</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid gap-4 md:grid-cols-[14rem_minmax(0,1fr)_auto] md:items-end">
            <div className="space-y-2">
              <label className="text-xs font-semibold uppercase tracking-[0.2em] text-muted-foreground">How many files to check</label>
              <Input value={auditSampleLimit} onChange={(event) => setAuditSampleLimit(event.target.value)} inputMode="numeric" />
              <p className="text-sm text-muted-foreground">Start with a smaller number if you are just spot-checking.</p>
            </div>
            <div className="space-y-2">
              <label className="text-xs font-semibold uppercase tracking-[0.2em] text-muted-foreground">Folder to check</label>
              <Input value={auditRootPath} onChange={(event) => setAuditRootPath(event.target.value)} placeholder="Optional: /media/library" />
              <p className="text-sm text-muted-foreground">Leave this blank to check across the full tracked library.</p>
            </div>
            <Button onClick={executeAudit} disabled={auditLoading}>
              <ShieldCheck className="mr-2 h-4 w-4" />
              Run Integrity Check
            </Button>
          </div>

          <DataTable
            columns={auditColumns}
            data={auditResults}
            loading={auditLoading}
            emptyMessage="No integrity results yet. Run a check above when you need a health review."
          />
        </CardContent>
      </Card>
    </div>
  );
}

function SystemHealthTab() {
  const queryClient = useQueryClient();
  const [includeCurrentDay, setIncludeCurrentDay] = useState(false);
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
  const reconcileMutation = useMutation({
    mutationFn: () => reconcileStaleOperationRuns({ include_current_day: includeCurrentDay }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.adminObservabilitySummary });
      void queryClient.invalidateQueries({ queryKey: queryKeys.adminObservabilityRuns({ limit: 25 }) });
      void queryClient.invalidateQueries({ queryKey: queryKeys.adminObservabilityFailures(20) });
      void queryClient.invalidateQueries({ queryKey: queryKeys.runsRoot });
    },
  });
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
    return <div className="text-sm text-muted-foreground">Loading system health data…</div>;
  }

  const error = summaryQuery.error || runsQuery.error || failuresQuery.error || seriesQuery.error || reconcileMutation.error;
  if (error instanceof Error) {
    return <ErrorAlert message={error.message} />;
  }

  const reconcileResult = reconcileMutation.data?.data as OperationRunReconcileResult | undefined;

  return (
    <div className="space-y-6">
      <GuidanceCard
        title="System Health"
        description="Review the broader technical picture when the simpler activity or file-history views are not enough."
        whenToUse="Use this when you are diagnosing patterns, checking observability integrations, or trying to understand whether the system is broadly healthy."
        example="Are failures spiking? Is latency trending upward? Are monitoring links configured?"
      />

      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <AdminMetricCard title="Metrics" value={summary?.metrics_enabled ? "Enabled" : "Disabled"} hint="Prometheus scrape surface" />
        <AdminMetricCard title="24h failures" value={String(summary?.recent_failure_count ?? 0)} hint="Durable failure events" />
        <AdminMetricCard title="Avg apply latency" value={`${Number(summary?.latest_metrics?.apply_time_ms ?? 0).toFixed(1)} ms`} hint="Latest persisted perf artifact" />
        <AdminMetricCard title="Cache hit rate" value={`${Number(summary?.latest_metrics?.cache_hit_rate ?? 0).toFixed(1)}%`} hint="Latest persisted cache signal" />
      </div>

      <Card className="rounded-[28px] border-border/70 shadow-sm">
        <CardHeader>
          <CardTitle className="flex items-center gap-2"><RefreshCw className="h-4 w-4" /> Reconcile stale operation runs</CardTitle>
          <CardDescription>Mark historical STARTED operation runs as failed when they were left incomplete by an interrupted process.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div className="flex items-start gap-3">
              <Checkbox
                id="include-current-day-runs"
                checked={includeCurrentDay}
                onCheckedChange={(checked) => setIncludeCurrentDay(checked === true)}
              />
              <div className="space-y-1">
                <Label htmlFor="include-current-day-runs">Include today&apos;s STARTED runs</Label>
                <p className="text-sm text-muted-foreground">
                  Leave this off for the safe default. Turn it on only when you intentionally want to fail current-day audit rows too.
                </p>
              </div>
            </div>
            <Button onClick={() => reconcileMutation.mutate()} disabled={reconcileMutation.isPending}>
              {reconcileMutation.isPending ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <RefreshCw className="mr-2 h-4 w-4" />}
              Reconcile Stale Runs
            </Button>
          </div>

          {reconcileResult ? (
            <div className="rounded-xl border bg-muted/20 p-4 text-sm">
              <div className="flex flex-wrap gap-x-4 gap-y-2">
                <span>Cutoff: {new Date(reconcileResult.cutoff).toLocaleString()}</span>
                <span>Scanned: {reconcileResult.scanned_count}</span>
                <span>Updated: {reconcileResult.updated_count}</span>
                <span>Included today: {reconcileResult.include_current_day ? "Yes" : "No"}</span>
              </div>
            </div>
          ) : null}
        </CardContent>
      </Card>

      <div className="grid gap-4 xl:grid-cols-2">
        <Card className="rounded-[28px] border-border/70 shadow-sm">
          <CardHeader>
            <CardTitle className="flex items-center gap-2"><Bar className="h-4 w-4" /> Operation volume</CardTitle>
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

        <Card className="rounded-[28px] border-border/70 shadow-sm">
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
        <Card className="rounded-[28px] border-border/70 shadow-sm">
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

        <Card className="rounded-[28px] border-border/70 shadow-sm">
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

      <Card className="rounded-[28px] border-border/70 shadow-sm">
        <CardHeader>
          <CardTitle>Recent technical operation feed</CardTitle>
          <CardDescription>Shared durable operation log behind the health view.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          {(runsQuery.data?.data as Run[] | undefined)?.slice(0, 12).map((run) => (
            <div key={run.operation_run_id} className="flex flex-wrap items-center justify-between gap-3 rounded-md border p-3">
              <div>
                <div className="flex flex-wrap items-center gap-2">
                  <div className="font-medium">{run.operation_type}</div>
                  {typeof run.context?.trigger === "string" ? (
                    <span className="rounded-full border border-border/70 bg-muted px-2 py-0.5 text-[11px] font-semibold uppercase tracking-[0.16em] text-muted-foreground">
                      {String(run.context.trigger).replaceAll("_", " ")}
                    </span>
                  ) : null}
                </div>
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
      <GuidanceCard
        title="Performance Lab"
        description="Queue synthetic benchmarks for technical validation when you want to measure admin-side performance without touching real filesystem work."
        whenToUse="Use this in dev or test when you are validating system behavior, not as part of day-to-day operation."
        example="How quickly does metadata work run at this scale? What happened in the last benchmark?"
      />

      {benchmarkError ? <ErrorAlert message={benchmarkError} /> : null}

      <div className="grid gap-4 xl:grid-cols-2">
        <Card className="rounded-[28px] border-border/70 shadow-sm">
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

        <Card className="rounded-[28px] border-border/70 shadow-sm">
          <CardHeader>
            <CardTitle>Discovery benchmark</CardTitle>
            <CardDescription>Synthetic canonical and tag query benchmark for discovery-style reads.</CardDescription>
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
        <Card className="rounded-[28px] border-border/70 shadow-sm">
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
              <div key={run.operation_run_id} className="flex flex-wrap items-center justify-between gap-3 rounded-md border p-3">
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

        <Card className="rounded-[28px] border-border/70 shadow-sm">
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
    } catch (err: unknown) {
      setError(getErrorMessage(err) || "Preview failed");
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
    } catch (err: unknown) {
      setError(getErrorMessage(err) || "Reset failed");
    } finally {
      setLoading(false);
      setConfirmOpen(false);
    }
  };

  return (
    <div className="space-y-6">
      <GuidanceCard
        title="Reset Library Data"
        description="Preview or clear database-backed library data in dev and test when you need a controlled reset of the working environment."
        whenToUse="Use this only when you explicitly want to destroy current working data. Most users should never need this tab."
        example="Can I preview what would be cleared? Do I need a clean test environment?"
      />

      {error ? <ErrorAlert message={error} onDismiss={() => setError(null)} /> : null}

      <div className="rounded-[28px] border-2 border-destructive/30 bg-destructive/5 p-6 shadow-sm">
        <div className="space-y-4">
          <div className="flex items-start gap-3">
            <div className="rounded-xl bg-destructive/10 p-2">
              <AlertTriangle className="h-6 w-6 text-destructive" />
            </div>
            <div>
              <h2 className="text-lg font-bold">Danger zone</h2>
              <p className="text-sm text-muted-foreground">
                Permanently delete all data from the media pipeline database. This cannot be undone.
              </p>
            </div>
          </div>

          <div className="flex flex-wrap gap-3">
            <Button variant="outline" onClick={handleDryRun} disabled={loading}>
              {loading && !confirmOpen ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Eye className="mr-2 h-4 w-4" />}
              Preview reset
            </Button>
            <Button variant="destructive" onClick={() => setConfirmOpen(true)} disabled={loading || !preview}>
              <Trash2 className="mr-2 h-4 w-4" />
              Execute reset
            </Button>
          </div>

          {preview ? (
            <div className="space-y-3">
              <h3 className="text-sm font-semibold">Affected tables</h3>
              <div className="grid gap-2 md:grid-cols-2">
                {preview.affected_tables.map((table) => (
                  <div key={table} className="flex items-center justify-between rounded-md border bg-card p-3">
                    <span className="font-mono text-sm">{table}</span>
                    <span className="text-xs font-mono font-bold text-destructive">planned</span>
                  </div>
                ))}
              </div>
            </div>
          ) : null}

          {result ? (
            <div className="space-y-3">
              <ErrorAlert message={result.message} severity={result.success ? "info" : "error"} />
              <JsonViewer data={result} title="Reset result" />
            </div>
          ) : null}
        </div>
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
            <ul className="mt-1 list-inside list-disc">
              {preview.affected_tables.map((table) => (
                <li key={table} className="font-mono text-xs">{table}</li>
              ))}
            </ul>
          </div>
        ) : null}
      </ConfirmDialog>
    </div>
  );
}

export default function AdminPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const tab = getAdminTab(searchParams.get("tab"));

  const updateTab = (nextTab: AdminTab) => {
    const nextParams = new URLSearchParams(searchParams);
    nextParams.set("tab", nextTab);
    setSearchParams(nextParams);
  };

  return (
    <div className="mx-auto flex max-w-7xl flex-col gap-6 p-6">
      <TopSurfaceHeader
        badge="Admin Workspace"
        title="Review what happened, investigate files, and use advanced tools only when you need them."
        description="This is one integrated workspace now. Start with the simpler review tools, then move into health checks, benchmarks, or reset only when the situation calls for it."
        icon={Sparkles}
        className="rounded-[30px]"
      >
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          <button
            type="button"
            onClick={() => updateTab("activity")}
            className="rounded-2xl border border-border/70 bg-background/85 p-4 text-left shadow-sm transition-colors hover:bg-primary/5"
          >
            <p className="text-xs font-semibold uppercase tracking-[0.2em] text-muted-foreground">Start here</p>
            <p className="mt-2 text-base font-semibold">Activity</p>
            <p className="mt-1 text-sm text-muted-foreground">Review recent jobs and failures first.</p>
          </button>
          <button
            type="button"
            onClick={() => updateTab("file-history")}
            className="rounded-2xl border border-border/70 bg-background/85 p-4 text-left shadow-sm transition-colors hover:bg-primary/5"
          >
            <p className="text-xs font-semibold uppercase tracking-[0.2em] text-muted-foreground">Find answers</p>
            <p className="mt-2 text-base font-semibold">File History</p>
            <p className="mt-1 text-sm text-muted-foreground">Investigate a file by path, fingerprint, or state.</p>
          </button>
          <button
            type="button"
            onClick={() => updateTab("library-rules")}
            className="rounded-2xl border border-border/70 bg-background/85 p-4 text-left shadow-sm transition-colors hover:bg-primary/5"
          >
            <p className="text-xs font-semibold uppercase tracking-[0.2em] text-muted-foreground">Set behavior</p>
            <p className="mt-2 text-base font-semibold">Library Rules</p>
            <p className="mt-1 text-sm text-muted-foreground">Choose which copy should stay primary.</p>
          </button>
          <button
            type="button"
            onClick={() => updateTab("system-health")}
            className="rounded-2xl border border-border/70 bg-background/85 p-4 text-left shadow-sm transition-colors hover:bg-primary/5"
          >
            <p className="text-xs font-semibold uppercase tracking-[0.2em] text-muted-foreground">Advanced</p>
            <p className="mt-2 text-base font-semibold">System Health</p>
            <p className="mt-1 text-sm text-muted-foreground">Check broader health and monitoring signals.</p>
          </button>
          <button
            type="button"
            onClick={() => updateTab("reset")}
            className="rounded-2xl border border-destructive/25 bg-background/85 p-4 text-left shadow-sm transition-colors hover:bg-destructive/5"
          >
            <p className="text-xs font-semibold uppercase tracking-[0.2em] text-destructive">Danger zone</p>
            <p className="mt-2 text-base font-semibold">Reset</p>
            <p className="mt-1 text-sm text-muted-foreground">Preview or clear data only in controlled environments.</p>
          </button>
        </div>
      </TopSurfaceHeader>

      <Tabs value={tab} onValueChange={(value) => updateTab(value as AdminTab)} className="space-y-4">
        <TabsList className="flex h-auto w-full flex-wrap justify-start gap-1 rounded-2xl p-1">
          <TabsTrigger value="overview">Overview</TabsTrigger>
          <TabsTrigger value="activity">Activity</TabsTrigger>
          <TabsTrigger value="library-rules">Library Rules</TabsTrigger>
          <TabsTrigger value="file-history">File History</TabsTrigger>
          <TabsTrigger value="integrity-check">Integrity Check</TabsTrigger>
          <TabsTrigger value="system-health">System Health</TabsTrigger>
          <TabsTrigger value="benchmarks">Performance Lab</TabsTrigger>
          <TabsTrigger value="reset">Reset</TabsTrigger>
        </TabsList>

        <TabsContent value="overview"><OverviewTab setTab={updateTab} /></TabsContent>
        <TabsContent value="activity"><ActivityTab /></TabsContent>
        <TabsContent value="library-rules"><LibraryRulesTab /></TabsContent>
        <TabsContent value="file-history"><FileHistoryTab /></TabsContent>
        <TabsContent value="integrity-check"><IntegrityCheckTab /></TabsContent>
        <TabsContent value="system-health"><SystemHealthTab /></TabsContent>
        <TabsContent value="benchmarks"><BenchmarksTab /></TabsContent>
        <TabsContent value="reset"><ResetTab /></TabsContent>
      </Tabs>
    </div>
  );
}
