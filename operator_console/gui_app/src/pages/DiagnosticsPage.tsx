import { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link, useSearchParams } from "react-router-dom";
import {
  Activity,
  AlertTriangle,
  ArrowRight,
  CheckCircle2,
  Clock3,
  FileSearch,
  Fingerprint,
  FolderClock,
  History,
  Search,
  ShieldCheck,
  Workflow,
  XCircle,
} from "lucide-react";

import { DataTable } from "@/components/DataTable";
import { ErrorAlert } from "@/components/ErrorAlert";
import { JsonViewer } from "@/components/JsonViewer";
import { MetricCard } from "@/components/MetricCard";
import { StatusBadge } from "@/components/StatusBadge";
import { TopSurfaceHeader } from "@/components/layout/TopSurfaceHeader";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { Input } from "@/components/ui/input";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  getAnalytics,
  getHashAudit,
  getMediaByHash,
  getMediaByStatus,
  getMediaHistory,
  getReappearances,
  getRuns,
} from "@/lib/api/endpoints";
import { queryKeys } from "@/lib/api/queryKeys";
import { queryOptions } from "@/lib/api/queryOptions";
import type { AnalyticsSummary, HashAuditResult, MediaFileRecord, PaginatedResponse, Run } from "@/types";

type DiagnosticsTab = "activity" | "file-history" | "integrity-check";
type FileHistoryTask = "history" | "hash" | "status" | "reappearances";

const VALID_TABS: DiagnosticsTab[] = ["activity", "file-history", "integrity-check"];
const STATUS_EXAMPLES = ["INGESTED", "PROCESSED", "DELETED"] as const;

function getErrorMessage(err: unknown): string | null {
  if (!err) return null;
  if (err instanceof Error) return err.message;
  return String(err);
}

function getDiagnosticsTab(value: string | null): DiagnosticsTab {
  return VALID_TABS.includes(value as DiagnosticsTab) ? (value as DiagnosticsTab) : "activity";
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

function formatFileState(status: string) {
  return status.toLowerCase().replace(/_/g, " ");
}

function formatSize(sizeBytes: number) {
  if (sizeBytes < 1024) return `${sizeBytes} B`;
  if (sizeBytes < 1024 * 1024) return `${(sizeBytes / 1024).toFixed(1)} KB`;
  return `${(sizeBytes / (1024 * 1024)).toFixed(1)} MB`;
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
        <div>
          <p className="text-sm font-semibold text-foreground">{title}</p>
        </div>
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

  const handleSelect = (run: Run) => {
    setSelectedRun(run);
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
              onRowClick={handleSelect}
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
                <span className="text-xs text-muted-foreground">
                  Page {page} of {totalPages}
                </span>
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
                    <p className="text-xs font-semibold uppercase tracking-[0.2em] text-muted-foreground">
                      Started
                    </p>
                    <p className="mt-2 text-sm">{new Date(selectedRun.started_at).toLocaleString()}</p>
                  </div>
                  <div className="rounded-2xl border bg-muted/20 p-4">
                    <p className="text-xs font-semibold uppercase tracking-[0.2em] text-muted-foreground">
                      Finished
                    </p>
                    <p className="mt-2 text-sm">
                      {selectedRun.completed_at ? new Date(selectedRun.completed_at).toLocaleString() : "Still running"}
                    </p>
                  </div>
                  <div className="rounded-2xl border bg-muted/20 p-4">
                    <p className="text-xs font-semibold uppercase tracking-[0.2em] text-muted-foreground">
                      Duration
                    </p>
                    <p className="mt-2 text-sm">{formatDuration(selectedRun.duration_ms)}</p>
                  </div>
                  {selectedRun.error_message ? (
                    <div className="rounded-2xl border border-destructive/20 bg-destructive/5 p-4">
                      <p className="text-xs font-semibold uppercase tracking-[0.2em] text-destructive">
                        Failure message
                      </p>
                      <p className="mt-2 text-sm text-foreground">{selectedRun.error_message}</p>
                    </div>
                  ) : null}
                </div>

                <Collapsible className="rounded-2xl border bg-background/80">
                  <CollapsibleTrigger asChild>
                    <button
                      type="button"
                      className="flex w-full items-center justify-between gap-3 px-4 py-3 text-left"
                    >
                      <div>
                        <p className="text-sm font-semibold">Technical details</p>
                        <p className="text-xs text-muted-foreground">
                          Raw IDs and metadata for support or advanced troubleshooting
                        </p>
                      </div>
                      <Activity className="h-4 w-4 text-muted-foreground" />
                    </button>
                  </CollapsibleTrigger>
                  <CollapsibleContent className="space-y-3 border-t px-4 py-4">
                    <div className="rounded-xl border bg-muted/20 p-3">
                      <p className="text-xs font-semibold uppercase tracking-[0.18em] text-muted-foreground">
                        Job history ID
                      </p>
                      <p className="mt-2 break-all font-mono text-xs">{selectedRun.operation_run_id}</p>
                    </div>
                    <div className="rounded-xl border bg-muted/20 p-3">
                      <p className="text-xs font-semibold uppercase tracking-[0.18em] text-muted-foreground">
                        Linked durable run ID
                      </p>
                      <p className="mt-2 break-all font-mono text-xs">{selectedRun.linked_run_id ?? "Not available"}</p>
                    </div>
                    {selectedRun.context || selectedRun.details ? (
                      <JsonViewer
                        data={selectedRun.context ?? selectedRun.details ?? {}}
                        title="Raw metadata"
                      />
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
        helper:
          "Paste the first part of the file fingerprint. You do not need the entire value.",
        buttonLabel: "Find file",
      };
    }
    if (task === "status") {
      return {
        label: "File state",
        placeholder: "Example: PROCESSED",
        helper:
          "Type a file state such as INGESTED, PROCESSED, or DELETED.",
        buttonLabel: "Browse state",
      };
    }
    if (task === "reappearances") {
      return {
        label: "File path",
        placeholder: "Example: /media/events/IMG_0001.JPG",
        helper:
          "Enter the path you want to check for deleted-then-returned history.",
        buttonLabel: "Check returned files",
      };
    }
    return {
      label: "File path",
      placeholder: "Example: /media/events/IMG_0001.JPG",
      helper:
        "Enter the path you want to investigate. This is the best first step when you know the file location.",
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
        <StatusBadge
          label={formatFileState(record.status)}
          severity={record.status === "DELETED" ? "destructive" : "neutral"}
        />
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
                <label className="text-xs font-semibold uppercase tracking-[0.2em] text-muted-foreground">
                  {taskHelp.label}
                </label>
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
                    <Button
                      key={status}
                      type="button"
                      variant="outline"
                      size="sm"
                      onClick={() => setQueryInput(status)}
                    >
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
                  <p className="text-sm text-muted-foreground">
                    Tip: you can paste only the beginning of the fingerprint.
                  </p>
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
                    <p className="text-xs font-semibold uppercase tracking-[0.2em] text-muted-foreground">
                      File state
                    </p>
                    <div className="mt-2">
                      <StatusBadge
                        label={formatFileState(selectedRecord.status)}
                        severity={selectedRecord.status === "DELETED" ? "destructive" : "neutral"}
                      />
                    </div>
                  </div>
                  <div className="rounded-2xl border bg-muted/20 p-4">
                    <p className="text-xs font-semibold uppercase tracking-[0.2em] text-muted-foreground">
                      File size
                    </p>
                    <p className="mt-2 text-sm">{formatSize(selectedRecord.size_bytes)}</p>
                  </div>
                  <div className="rounded-2xl border bg-muted/20 p-4">
                    <p className="text-xs font-semibold uppercase tracking-[0.2em] text-muted-foreground">
                      First seen
                    </p>
                    <p className="mt-2 text-sm">
                      {selectedRecord.discovered_at ? new Date(selectedRecord.discovered_at).toLocaleString() : "Unknown"}
                    </p>
                  </div>
                  <div className="rounded-2xl border bg-muted/20 p-4">
                    <p className="text-xs font-semibold uppercase tracking-[0.2em] text-muted-foreground">
                      Last ingested
                    </p>
                    <p className="mt-2 text-sm">
                      {selectedRecord.ingested_at ? new Date(selectedRecord.ingested_at).toLocaleString() : "Not available"}
                    </p>
                  </div>
                </div>

                <Collapsible className="rounded-2xl border bg-background/80">
                  <CollapsibleTrigger asChild>
                    <button
                      type="button"
                      className="flex w-full items-center justify-between gap-3 px-4 py-3 text-left"
                    >
                      <div>
                        <p className="text-sm font-semibold">Technical details</p>
                        <p className="text-xs text-muted-foreground">
                          Original paths and the stored fingerprint for advanced review
                        </p>
                      </div>
                      <FileSearch className="h-4 w-4 text-muted-foreground" />
                    </button>
                  </CollapsibleTrigger>
                  <CollapsibleContent className="space-y-3 border-t px-4 py-4">
                    <div className="rounded-xl border bg-muted/20 p-3">
                      <p className="text-xs font-semibold uppercase tracking-[0.18em] text-muted-foreground">
                        Current path
                      </p>
                      <p className="mt-2 break-all font-mono text-xs">{selectedRecord.current_path}</p>
                    </div>
                    <div className="rounded-xl border bg-muted/20 p-3">
                      <p className="text-xs font-semibold uppercase tracking-[0.18em] text-muted-foreground">
                        Discovered path
                      </p>
                      <p className="mt-2 break-all font-mono text-xs">{selectedRecord.discovered_path}</p>
                    </div>
                    <div className="rounded-xl border bg-muted/20 p-3">
                      <p className="text-xs font-semibold uppercase tracking-[0.18em] text-muted-foreground">
                        File fingerprint
                      </p>
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
              <label className="text-xs font-semibold uppercase tracking-[0.2em] text-muted-foreground">
                How many files to check
              </label>
              <Input
                value={auditSampleLimit}
                onChange={(event) => setAuditSampleLimit(event.target.value)}
                inputMode="numeric"
              />
              <p className="text-sm text-muted-foreground">
                Start with a smaller number if you are just spot-checking.
              </p>
            </div>
            <div className="space-y-2">
              <label className="text-xs font-semibold uppercase tracking-[0.2em] text-muted-foreground">
                Folder to check
              </label>
              <Input
                value={auditRootPath}
                onChange={(event) => setAuditRootPath(event.target.value)}
                placeholder="Optional: /media/library"
              />
              <p className="text-sm text-muted-foreground">
                Leave this blank to check across the full tracked library.
              </p>
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

export default function DiagnosticsPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const tab = getDiagnosticsTab(searchParams.get("tab"));

  const updateTab = (nextTab: DiagnosticsTab) => {
    const nextParams = new URLSearchParams(searchParams);
    nextParams.set("tab", nextTab);
    setSearchParams(nextParams);
  };

  return (
    <div className="mx-auto flex max-w-7xl flex-col gap-6 p-6">
      <TopSurfaceHeader
        badge="Admin Diagnostics"
        title="Check recent activity and investigate file records with confidence."
        description="This area brings together recent jobs, file history, and integrity checks in one calmer workspace for admins and support users."
        icon={ShieldCheck}
        className="rounded-[30px]"
      >
        <div className="flex flex-wrap gap-3">
          <Button size="sm" onClick={() => updateTab("activity")}>
            Open Activity
          </Button>
          <Button size="sm" variant="outline" onClick={() => updateTab("file-history")}>
            Find a File
          </Button>
          <Button asChild size="sm" variant="ghost">
            <Link to="/admin">
              Back to Admin
              <ArrowRight className="ml-2 h-4 w-4" />
            </Link>
          </Button>
        </div>
      </TopSurfaceHeader>

      <Tabs value={tab} onValueChange={(value) => updateTab(value as DiagnosticsTab)} className="space-y-4">
        <TabsList className="grid w-full max-w-2xl grid-cols-3">
          <TabsTrigger value="activity">Activity</TabsTrigger>
          <TabsTrigger value="file-history">File History</TabsTrigger>
          <TabsTrigger value="integrity-check">Integrity Check</TabsTrigger>
        </TabsList>
        <TabsContent value="activity">
          <ActivityTab />
        </TabsContent>
        <TabsContent value="file-history">
          <FileHistoryTab />
        </TabsContent>
        <TabsContent value="integrity-check">
          <IntegrityCheckTab />
        </TabsContent>
      </Tabs>
    </div>
  );
}
