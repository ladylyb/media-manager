import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, Loader2, ShieldCheck, ShieldOff } from "lucide-react";

import { LiveProgressPanel } from "@/components/progress/LiveProgressPanel";
import { ErrorAlert } from "@/components/ErrorAlert";
import { TopSurfaceHeader } from "@/components/layout/TopSurfaceHeader";
import { StatusBadge } from "@/components/StatusBadge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Skeleton } from "@/components/ui/skeleton";
import { WizardResultConsole } from "@/components/wizard/WizardResultConsole";
import {
  getIntegrityDashboard,
  getIntegrityFile,
  getIntegrityIssues,
  getIntegrityQuarantineItems,
  getPolicy,
  quarantineIntegrityFile,
  restoreIntegrityFile,
  setIntegrityReview,
  startIntegrityScan,
} from "@/lib/api/endpoints";
import { queryKeys } from "@/lib/api/queryKeys";
import type { IntegrityDashboard, IntegrityFileDetail, IntegrityIssue, IntegrityQuarantineItem, Policy } from "@/types";

type IssueFilter = "ALL" | "BROKEN" | "SUSPECT";
type IntegrityScanResult = {
  run_id: string;
  status?: string;
  scan_mode: "FAST" | "DEEP";
  eligible_file_count?: number;
  scanned_count: number;
  issues_found: number;
};
type IntegrityScanFeedback = {
  runId?: string;
  mode: "FAST" | "DEEP";
  phase: "running" | "completed" | "failed";
  eligible_file_count?: number;
  scanned_count?: number;
  issues_found?: number;
  message?: string;
};

function basename(path: string) {
  const parts = path.split(/[\\/]/).filter(Boolean);
  return parts.at(-1) ?? path;
}

function statusTone(status: IntegrityIssue["status"]) {
  if (status === "BROKEN") return "text-red-700 bg-red-50 border-red-200";
  if (status === "SUSPECT") return "text-amber-700 bg-amber-50 border-amber-200";
  return "text-emerald-700 bg-emerald-50 border-emerald-200";
}

function formatScanMode(mode: "FAST" | "DEEP") {
  return mode === "DEEP" ? "Deep" : "Quick";
}

function StatCard({
  title,
  value,
  helper,
}: {
  title: string;
  value: string | number;
  helper: string;
}) {
  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-sm text-muted-foreground">{title}</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="text-3xl font-semibold">{value}</div>
        <p className="mt-1 text-xs text-muted-foreground">{helper}</p>
      </CardContent>
    </Card>
  );
}

export default function IntegrityPage() {
  const queryClient = useQueryClient();
  const [filter, setFilter] = useState<IssueFilter>("ALL");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [scanFeedback, setScanFeedback] = useState<IntegrityScanFeedback | null>(null);

  const dashboardQuery = useQuery({
    queryKey: queryKeys.integrityDashboard,
    queryFn: async () => (await getIntegrityDashboard()).data as IntegrityDashboard,
  });
  const policyQuery = useQuery({
    queryKey: queryKeys.policy,
    queryFn: async () => (await getPolicy()).data,
  });

  const issuesQuery = useQuery({
    queryKey: queryKeys.integrityIssues({ status: filter === "ALL" ? undefined : filter, page: 1, limit: 100 }),
    queryFn: async () =>
      (
        await getIntegrityIssues({
          status: filter === "ALL" ? undefined : filter,
          page: 1,
          limit: 100,
        })
      ).data,
  });

  const issues = (issuesQuery.data?.items ?? []) as IntegrityIssue[];
  const policy = (policyQuery.data as Policy | undefined) ?? null;
  const selectedIssue = issues.find((item) => item.check_id === selectedId) ?? issues[0] ?? null;

  useEffect(() => {
    if (!issues.length) {
      setSelectedId(null);
      return;
    }
    if (!selectedId || !issues.some((item) => item.check_id === selectedId)) {
      setSelectedId(issues[0].check_id);
    }
  }, [issues, selectedId]);

  const detailQuery = useQuery({
    queryKey: queryKeys.integrityFile(selectedIssue?.check_id ?? "idle"),
    queryFn: async () => (await getIntegrityFile(selectedIssue?.check_id ?? "")).data as IntegrityFileDetail,
    enabled: Boolean(selectedIssue?.check_id),
  });

  const quarantineQuery = useQuery({
    queryKey: queryKeys.integrityQuarantine(1, 50),
    queryFn: async () => (await getIntegrityQuarantineItems({ page: 1, limit: 50 })).data,
  });

  const scanMutation = useMutation({
    mutationFn: (mode: "FAST" | "DEEP") => startIntegrityScan({ mode }),
    onMutate: (mode) => {
      setScanFeedback({ mode, phase: "running" });
      return { mode };
    },
    onSuccess: (response) => {
      const payload = (response?.data ?? {}) as Partial<IntegrityScanResult>;
      const scanResult: IntegrityScanResult = {
        run_id: String(payload.run_id ?? ""),
        status: payload.status ? String(payload.status) : undefined,
        scan_mode: payload.scan_mode === "DEEP" ? "DEEP" : "FAST",
        eligible_file_count:
          typeof payload.eligible_file_count === "number" ? Number(payload.eligible_file_count) : undefined,
        scanned_count: Number(payload.scanned_count ?? 0),
        issues_found: Number(payload.issues_found ?? 0),
      };
      setScanFeedback({
        runId: scanResult.run_id,
        mode: scanResult.scan_mode,
        phase: "completed",
        eligible_file_count: scanResult.eligible_file_count,
        scanned_count: scanResult.scanned_count,
        issues_found: scanResult.issues_found,
      });
      void queryClient.invalidateQueries({ queryKey: queryKeys.integrityDashboard });
      void queryClient.invalidateQueries({ queryKey: ["integrity", "issues"] });
      if (selectedIssue?.check_id) {
        void queryClient.invalidateQueries({ queryKey: queryKeys.integrityFile(selectedIssue.check_id) });
      }
    },
    onError: (error, _mode, context) => {
      const activeMode = context?.mode ?? "FAST";
      setScanFeedback({
        mode: activeMode,
        phase: "failed",
        message: error instanceof Error ? error.message : String(error),
      });
    },
  });

  const reviewMutation = useMutation({
    mutationFn: ({ checkId, decision }: { checkId: string; decision: "MARK_OK" | "IGNORE" }) =>
      setIntegrityReview({ check_id: checkId, decision }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.integrityDashboard });
      void queryClient.invalidateQueries({ queryKey: ["integrity", "issues"] });
      if (selectedIssue?.check_id) {
        void queryClient.invalidateQueries({ queryKey: queryKeys.integrityFile(selectedIssue.check_id) });
      }
    },
  });

  const quarantineMutation = useMutation({
    mutationFn: (checkId: string) => quarantineIntegrityFile({ check_id: checkId }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.integrityDashboard });
      void queryClient.invalidateQueries({ queryKey: ["integrity", "issues"] });
      void queryClient.invalidateQueries({ queryKey: ["integrity", "quarantine"] });
    },
  });

  const restoreMutation = useMutation({
    mutationFn: (fileInstanceId: string) => restoreIntegrityFile({ file_instance_id: fileInstanceId }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.integrityDashboard });
      void queryClient.invalidateQueries({ queryKey: ["integrity", "issues"] });
      void queryClient.invalidateQueries({ queryKey: ["integrity", "quarantine"] });
    },
  });

  const detail = detailQuery.data as IntegrityFileDetail | undefined;
  const quarantineItems = (quarantineQuery.data?.items ?? []) as IntegrityQuarantineItem[];
  const selectedQuarantine = selectedIssue
    ? quarantineItems.find((item) => item.file_instance_id === selectedIssue.file_instance_id) ?? null
    : null;
  const newIssuesCount = useMemo(
    () => issues.filter((item) => !item.reviewed_decision && item.status !== "OK").length,
    [issues],
  );
  const runningMode = scanMutation.isPending ? scanFeedback?.mode ?? null : null;
  const quickLabel = runningMode === "FAST" ? "Running Quick Scan..." : "Quick Scan";
  const deepLabel = runningMode === "DEEP" ? "Running Deep Scan..." : "Deep Scan";
  const scanModeLabel = scanFeedback ? `${formatScanMode(scanFeedback.mode)} scan` : "Scan";
  const scanStatusBadge =
    scanFeedback?.phase === "running"
      ? { label: "Scan Running", severity: "info" as const, dot: true }
      : scanFeedback?.phase === "completed"
        ? { label: "Scan Complete", severity: "success" as const, dot: true }
        : scanFeedback?.phase === "failed"
          ? { label: "Scan Failed", severity: "destructive" as const, dot: true }
          : { label: "Ready", severity: "neutral" as const, dot: false };
  const scanMetrics =
    scanFeedback?.phase === "completed"
      ? [
          {
            label: "Mode used",
            value: formatScanMode(scanFeedback.mode),
          },
          ...(scanFeedback.eligible_file_count != null
            ? [
                {
                  label: "Eligible files",
                  value: scanFeedback.eligible_file_count,
                },
              ]
            : []),
          ...(scanFeedback.scanned_count != null
            ? [
                {
                  label: "Files scanned",
                  value: scanFeedback.scanned_count,
                },
              ]
            : []),
          ...(scanFeedback.issues_found != null
            ? [
                {
                  label: "Issues found",
                  value: scanFeedback.issues_found,
                },
              ]
            : []),
        ]
      : [];
  const scanSummaryLines =
    scanFeedback?.phase === "completed"
      ? [
          `${scanModeLabel} completed and refreshed the dashboard, review queue, and selected file detail.`,
          ...(scanFeedback.scanned_count === 0 ? ["No eligible active files were scanned."] : []),
        ]
      : scanFeedback?.phase === "failed"
        ? [
            `${scanModeLabel} failed before the page could refresh with new results.`,
            scanFeedback.message ?? "Unknown error",
          ]
        : [];

  return (
    <div className="space-y-6 p-6">
      <TopSurfaceHeader
        badge="Integrity"
        title="Integrity Review"
        description="Read-only scan results for playback and file-health issues."
      >
        <div className="flex flex-col items-end gap-2">
          {policy ? (
            <p className="text-xs text-muted-foreground">
              Saved default scan mode: {policy.integrity.default_scan_mode === "DEEP" ? "Deep" : "Quick"}
            </p>
          ) : null}
          <p className="text-xs text-muted-foreground">
            Quick Scan: readability and probe checks
          </p>
          <p className="text-xs text-muted-foreground">
            Deep Scan: quick scan plus decode-level verification on eligible active files
          </p>
          <div className="flex gap-2">
            <Button
              variant="outline"
              onClick={() => scanMutation.mutate("FAST")}
              disabled={scanMutation.isPending}
            >
              {runningMode === "FAST" ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}
              {quickLabel}
            </Button>
            <Button onClick={() => scanMutation.mutate("DEEP")} disabled={scanMutation.isPending}>
              {runningMode === "DEEP" ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}
              {deepLabel}
            </Button>
          </div>
        </div>
      </TopSurfaceHeader>

      <Card>
        <CardHeader className="space-y-3">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div className="space-y-1">
              <CardTitle>Integrity Scan Status</CardTitle>
              <p className="text-sm text-muted-foreground">
                This is the one place to check what just started, what is running now, and how the scan finished.
              </p>
            </div>
            <StatusBadge
              label={scanStatusBadge.label}
              severity={scanStatusBadge.severity}
              dot={scanStatusBadge.dot}
            />
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          {!scanFeedback ? (
            <div className="rounded-xl border border-dashed bg-background/70 p-4 text-sm text-muted-foreground">
              Start a Quick Scan or Deep Scan above. Live activity and the latest scan summary will appear here.
            </div>
          ) : null}

          {scanFeedback?.phase === "running" ? (
            <div className="space-y-4">
              <div className="rounded-xl border bg-primary/[0.04] p-4">
                <p className="text-[11px] font-semibold uppercase tracking-[0.2em] text-primary/80">
                  What&apos;s Happening Now
                </p>
                <p className="mt-3 text-sm text-foreground">{scanModeLabel} started.</p>
                <p className="mt-2 text-sm text-muted-foreground">
                  Stay on this panel to follow the scan. Recent scan activity and any available log updates will appear below.
                </p>
              </div>
              <LiveProgressPanel operationKind="integrity" operationStatus="running" />
            </div>
          ) : null}

          {scanFeedback?.phase === "completed" ? (
            <WizardResultConsole
              title="Integrity Scan Result"
              status="success"
              metrics={scanMetrics}
              references={
                scanFeedback.runId
                  ? [
                      {
                        label: "Run ID",
                        value: scanFeedback.runId,
                        helperText: "This scan result is already reflected in the refreshed review queue below.",
                        copyable: true,
                      },
                    ]
                  : []
              }
              summaryLines={scanSummaryLines}
              nextStepHint="Review the queue and selected file detail below to understand which files need attention."
              payload={scanFeedback}
              technicalDetailsMode="modal"
            />
          ) : null}

          {scanFeedback?.phase === "failed" ? (
            <WizardResultConsole
              title="Integrity Scan Result"
              status="failed"
              metrics={[
                {
                  label: "Mode used",
                  value: formatScanMode(scanFeedback.mode),
                },
              ]}
              summaryLines={scanSummaryLines}
              nextStepHint="You can retry the scan from the buttons above after addressing the reported issue."
              nextStepTone="caution"
              payload={scanFeedback}
              technicalDetailsMode="modal"
            />
          ) : null}
        </CardContent>
      </Card>

      {(dashboardQuery.error || issuesQuery.error || detailQuery.error || quarantineQuery.error) && (
        <ErrorAlert
          message={
            String(
              dashboardQuery.error?.message ??
                issuesQuery.error?.message ??
                detailQuery.error?.message ??
                quarantineQuery.error?.message ??
                "Unable to load integrity data.",
            )
          }
        />
      )}

      <div className="grid gap-4 md:grid-cols-5">
        <StatCard
          title="Files Scanned"
          value={dashboardQuery.data?.total_files_scanned ?? 0}
          helper={dashboardQuery.data?.last_scan_at ? `Last scan ${new Date(dashboardQuery.data.last_scan_at).toLocaleString()}` : "No scan yet"}
        />
        <StatCard title="Playback Issues" value={dashboardQuery.data?.playback_issues ?? 0} helper="Broken and suspect files needing review." />
        <StatCard title="Broken" value={dashboardQuery.data?.broken_count ?? 0} helper="Highest confidence integrity failures." />
        <StatCard title="Reviewed" value={(dashboardQuery.data?.ignored_count ?? 0) + (dashboardQuery.data?.marked_ok_count ?? 0)} helper="Ignored or marked OK by operators." />
        <StatCard
          title="High-Confidence Queue"
          value={dashboardQuery.data?.high_confidence_unresolved_count ?? 0}
          helper={
            policy
              ? `Unreviewed issues at or above ${(policy.integrity.issue_min_confidence * 100).toFixed(0)}% confidence.`
              : "Unreviewed high-confidence issues."
          }
        />
      </div>

      <div className="grid gap-4 xl:grid-cols-[1.15fr_0.85fr]">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between">
            <div>
              <CardTitle>Review Queue</CardTitle>
              <p className="mt-1 text-sm text-muted-foreground">{newIssuesCount} files still need attention.</p>
            </div>
            <div className="flex gap-2">
              {(["ALL", "BROKEN", "SUSPECT"] as IssueFilter[]).map((value) => (
                <Button
                  key={value}
                  size="sm"
                  variant={filter === value ? "default" : "outline"}
                  onClick={() => setFilter(value)}
                >
                  {value === "ALL" ? "All" : value === "BROKEN" ? "Broken" : "Suspect"}
                </Button>
              ))}
            </div>
          </CardHeader>
          <CardContent>
            {issuesQuery.isLoading ? (
              <div className="space-y-3">
                {Array.from({ length: 5 }).map((_, index) => (
                  <Skeleton key={index} className="h-20 w-full rounded-xl" />
                ))}
              </div>
            ) : !issues.length ? (
              <div className="rounded-xl border border-dashed p-8 text-center text-sm text-muted-foreground">
                No integrity issues match this filter.
              </div>
            ) : (
              <ScrollArea className="h-[34rem] pr-4">
                <div className="space-y-3">
                  {issues.map((issue) => (
                    <button
                      key={issue.check_id}
                      type="button"
                      onClick={() => setSelectedId(issue.check_id)}
                      className={`w-full rounded-xl border p-4 text-left transition ${selectedIssue?.check_id === issue.check_id ? "border-primary bg-primary/5" : "hover:border-primary/40"}`}
                    >
                      <div className="flex items-start justify-between gap-4">
                        <div>
                          <p className="font-medium">{basename(issue.absolute_path)}</p>
                          <p className="mt-1 text-xs text-muted-foreground">{issue.absolute_path}</p>
                        </div>
                        <span className={`rounded-full border px-2.5 py-1 text-xs font-medium ${statusTone(issue.status)}`}>
                          {issue.status}
                        </span>
                      </div>
                      <div className="mt-3 flex flex-wrap gap-2 text-xs text-muted-foreground">
                        <span>Confidence {issue.confidence.toFixed(2)}</span>
                        {issue.signal_types.map((signal) => (
                          <span key={signal} className="rounded-full bg-muted px-2 py-1">
                            {signal}
                          </span>
                        ))}
                        {issue.reviewed_decision ? (
                          <span className="rounded-full bg-emerald-100 px-2 py-1 text-emerald-800">
                            {issue.reviewed_decision}
                          </span>
                        ) : null}
                      </div>
                    </button>
                  ))}
                </div>
              </ScrollArea>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>File Detail</CardTitle>
          </CardHeader>
          <CardContent>
            {!selectedIssue ? (
              <div className="rounded-xl border border-dashed p-8 text-center text-sm text-muted-foreground">
                Select an issue to inspect signals and review it.
              </div>
            ) : detailQuery.isLoading ? (
              <div className="space-y-3">
                <Skeleton className="h-8 w-48" />
                <Skeleton className="h-32 w-full" />
                <Skeleton className="h-40 w-full" />
              </div>
            ) : detail ? (
              <div className="space-y-4">
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <p className="text-lg font-semibold">{basename(detail.absolute_path)}</p>
                    <p className="mt-1 text-xs text-muted-foreground">{detail.absolute_path}</p>
                  </div>
                  <div className={`rounded-full border px-3 py-1 text-xs font-medium ${statusTone(detail.status)}`}>
                    {detail.status}
                  </div>
                </div>

                <div className="grid gap-3 sm:grid-cols-2">
                  <div className="rounded-xl bg-muted/50 p-3">
                    <p className="text-xs uppercase tracking-wide text-muted-foreground">Confidence</p>
                    <p className="mt-1 text-xl font-semibold">{detail.confidence.toFixed(2)}</p>
                  </div>
                  <div className="rounded-xl bg-muted/50 p-3">
                    <p className="text-xs uppercase tracking-wide text-muted-foreground">Probe / Decode</p>
                    <p className="mt-1 text-sm font-medium">{detail.probe_status ?? "N/A"} / {detail.decode_status ?? "N/A"}</p>
                  </div>
                </div>

                <div className="flex flex-wrap gap-2">
                  <Button
                    variant="outline"
                    onClick={() => reviewMutation.mutate({ checkId: detail.check_id, decision: "MARK_OK" })}
                    disabled={reviewMutation.isPending}
                  >
                    <ShieldCheck className="mr-2 h-4 w-4" />
                    Mark as OK
                  </Button>
                  <Button
                    variant="outline"
                    onClick={() => reviewMutation.mutate({ checkId: detail.check_id, decision: "IGNORE" })}
                    disabled={reviewMutation.isPending}
                  >
                    <ShieldOff className="mr-2 h-4 w-4" />
                    Ignore
                  </Button>
                  {selectedQuarantine?.quarantine_status === "QUARANTINED" ? (
                    <Button
                      onClick={() => restoreMutation.mutate(detail.file_instance_id)}
                      disabled={restoreMutation.isPending}
                    >
                      Restore
                    </Button>
                  ) : (
                    <Button
                      onClick={() => quarantineMutation.mutate(detail.check_id)}
                      disabled={quarantineMutation.isPending}
                    >
                      Quarantine
                    </Button>
                  )}
                </div>

                <div className="rounded-xl border bg-muted/20 p-4 text-sm text-muted-foreground">
                  {selectedQuarantine ? (
                    <>
                      <p>Status: {selectedQuarantine.quarantine_status}</p>
                      <p className="mt-1 break-all">Path: {selectedQuarantine.quarantine_path}</p>
                    </>
                  ) : (
                    <p>This file has not been quarantined.</p>
                  )}
                </div>

                <div className="space-y-3">
                  {detail.signals.map((signal) => (
                    <div key={`${signal.signal_type}-${signal.created_at}`} className="rounded-xl border p-3">
                      <div className="flex items-center gap-2">
                        <AlertTriangle className="h-4 w-4 text-amber-600" />
                        <p className="font-medium">{signal.signal_type}</p>
                      </div>
                      <p className="mt-1 text-xs uppercase tracking-wide text-muted-foreground">{signal.severity}</p>
                      <pre className="mt-2 overflow-x-auto rounded-lg bg-muted p-3 text-xs">
                        {JSON.stringify(signal.details, null, 2)}
                      </pre>
                    </div>
                  ))}
                </div>
              </div>
            ) : (
              <div className="rounded-xl border border-dashed p-8 text-center text-sm text-muted-foreground">
                No detail available for this issue.
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
