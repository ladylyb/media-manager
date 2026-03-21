import { ChevronDown, ChevronUp } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { useLiveLogs } from "@/hooks/useLiveLogs";
import { StatusBadge } from "@/components/StatusBadge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { Progress } from "@/components/ui/progress";
import { resolveOperationDisplayState } from "@/lib/logs/resolveOperationDisplayState";
import { cn } from "@/lib/utils";
import { getLogLineTone } from "@/lib/logs/parseProgressLogs";
import type { ProgressOperationKind, ProgressOperationStatus } from "@/types/logs";

function formatOperationName(kind: ProgressOperationKind) {
  if (kind === "ingest") return "INGEST";
  if (kind === "plan") return "PLAN";
  if (kind === "apply") return "APPLY";
  if (kind === "canonical") return "CANONICAL";
  if (kind === "tag") return "TAG";
  return null;
}

function formatHeaderLabel(kind: ProgressOperationKind, status: ProgressOperationStatus) {
  const name = formatOperationName(kind);
  if (name && status === "running") return `[ ${name} RUNNING ]`;
  if (name && status === "finalizing") return `[ FINALIZING ${name} ]`;
  if (name && status === "completed") return `[ ${name} COMPLETE ]`;
  if (name && status === "error") return `[ ${name} FAILED ]`;
  if (name && status === "idle") return `[ ${name} READY ]`;
  return "[ WAITING FOR LOGS ]";
}

function formatPhaseLabel(kind: ProgressOperationKind, status: ProgressOperationStatus) {
  if (kind === "plan") return status === "finalizing" ? "Finalizing Plan" : "Plan";
  if (kind === "ingest") return status === "finalizing" ? "Finalizing Ingest" : "Ingest";
  if (kind === "apply") return status === "finalizing" ? "Finalizing Apply" : "Apply";
  if (kind === "canonical") return status === "finalizing" ? "Finalizing Canonical" : "Canonical";
  if (kind === "tag") return status === "finalizing" ? "Finalizing Tags" : "Tag";
  if (status === "completed") return "Complete";
  if (status === "error") return "Failed";
  return "Idle";
}

function formatMetricValue(value: number | null, suffix = "") {
  return value === null ? "--" : `${value.toFixed(1)}${suffix}`;
}

function formatCountLabel(kind: ProgressOperationKind) {
  return kind === "ingest" || kind === "plan" ? "Files" : "Processed";
}

function formatThroughput(kind: ProgressOperationKind, throughputFps: number | null) {
  if (throughputFps === null) return "--";
  const unit = kind === "ingest" || kind === "plan" ? "files/sec" : "items/sec";
  return `${throughputFps.toFixed(1)} ${unit}`;
}

function formatStageLabel(stage: string | null) {
  if (!stage) return null;
  return stage
    .split(/[_-]/)
    .map((segment) => segment.charAt(0).toUpperCase() + segment.slice(1))
    .join(" ");
}

interface LiveProgressPanelProps {
  className?: string;
  operationKind?: ProgressOperationKind;
  operationStatus?: ProgressOperationStatus;
}

export function LiveProgressPanel({
  className,
  operationKind,
  operationStatus,
}: LiveProgressPanelProps) {
  // Optional support panels in this UI default collapsed so the main workflow stays visually primary.
  const [open, setOpen] = useState(false);
  const { parsed, lines, error: fetchError } = useLiveLogs(100);
  const logViewportRef = useRef<HTMLDivElement | null>(null);
  const shouldAutoScrollRef = useRef(true);
  const displayState = resolveOperationDisplayState({
    operationKind,
    operationStatus,
    parsedPhase: parsed.phase,
    parsedStatus: parsed.status,
    progressPercent: parsed.progressPercent,
  });

  useEffect(() => {
    const viewport = logViewportRef.current;
    if (!viewport || !shouldAutoScrollRef.current) return;
    viewport.scrollTop = viewport.scrollHeight;
  }, [lines]);

  const progressValue = Math.max(
    0,
    Math.min(
      100,
      displayState.status === "completed" && parsed.progressPercent === null
        ? 100
        : parsed.progressPercent ?? 0,
    ),
  );
  const badgeSeverity =
    displayState.status === "running" || displayState.status === "finalizing"
      ? "info"
      : displayState.status === "completed"
        ? "success"
        : displayState.status === "error"
          ? "destructive"
      : fetchError
        ? "caution"
        : "neutral";

  return (
    <Collapsible open={open} onOpenChange={setOpen}>
      <Card className={cn("rounded-2xl border-border/70 bg-card/95 shadow-sm", className)}>
        <CardHeader className="space-y-3 pb-3">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <CardTitle className="font-mono text-sm tracking-[0.24em] text-foreground">
              {formatHeaderLabel(displayState.kind, displayState.status)}
            </CardTitle>
            <div className="flex items-center gap-2">
              <StatusBadge
                label={formatPhaseLabel(displayState.kind, displayState.status)}
                severity={badgeSeverity}
                dot={displayState.status === "running" || displayState.status === "finalizing"}
              />
              <CollapsibleTrigger asChild>
                <Button type="button" variant="ghost" size="sm">
                  {open ? (
                    <>
                      <ChevronUp className="mr-2 h-4 w-4" />
                      Hide live progress
                    </>
                  ) : (
                    <>
                      <ChevronDown className="mr-2 h-4 w-4" />
                      Show live progress
                    </>
                  )}
                </Button>
              </CollapsibleTrigger>
            </div>
          </div>
        </CardHeader>
        <CollapsibleContent>
          <CardContent className="space-y-4 border-t pt-4">
            <Progress value={progressValue} className="h-2.5 bg-muted/70" />
            {displayState.status === "finalizing" ? (
              <p className="text-xs text-muted-foreground">
                The latest progress checkpoint has been reached. The request is still finishing backend work.
              </p>
            ) : null}
            {parsed.stage && (displayState.status === "running" || displayState.status === "finalizing" || lines.length > 0) ? (
              <p className="text-xs text-muted-foreground">
                Current stage: <span className="font-medium text-foreground">{formatStageLabel(parsed.stage)}</span>
              </p>
            ) : null}
            <div className="grid gap-3 md:grid-cols-3">
              <div className="rounded-xl border bg-muted/20 p-3">
                <p className="text-[11px] font-semibold uppercase tracking-[0.2em] text-muted-foreground">
                  Progress
                </p>
                <p className="mt-2 text-lg font-semibold">{formatMetricValue(parsed.progressPercent, "%")}</p>
              </div>
              <div className="rounded-xl border bg-muted/20 p-3">
                <p className="text-[11px] font-semibold uppercase tracking-[0.2em] text-muted-foreground">
                  {formatCountLabel(displayState.kind)}
                </p>
                <p className="mt-2 text-lg font-semibold">
                  {parsed.processedCount ?? "--"} / {parsed.totalCount ?? "--"}
                </p>
              </div>
              <div className="rounded-xl border bg-muted/20 p-3">
                <p className="text-[11px] font-semibold uppercase tracking-[0.2em] text-muted-foreground">
                  Speed
                </p>
                <p className="mt-2 text-lg font-semibold">{formatThroughput(displayState.kind, parsed.throughputFps)}</p>
              </div>
            </div>

            {fetchError ? (
              <p className="text-xs text-muted-foreground">
                Live log polling is temporarily unavailable: {fetchError}
              </p>
            ) : null}

            <div className="space-y-2">
              <p className="text-[11px] font-semibold uppercase tracking-[0.2em] text-muted-foreground">
                Recent Logs
              </p>
              <div
                ref={logViewportRef}
                className="max-h-72 overflow-y-auto rounded-xl border bg-muted/15 p-3 font-mono text-xs"
                onScroll={(event) => {
                  const element = event.currentTarget;
                  const distanceFromBottom = element.scrollHeight - element.scrollTop - element.clientHeight;
                  shouldAutoScrollRef.current = distanceFromBottom < 24;
                }}
              >
                {lines.length === 0 ? (
                  <p className="text-muted-foreground">Waiting for pipeline log lines...</p>
                ) : (
                  <div className="space-y-1.5">
                    {lines.map((line, index) => {
                      const tone = getLogLineTone(line);
                      return (
                        <div
                          key={`${index}-${line}`}
                          className={cn(
                            "rounded-md px-2 py-1.5 text-muted-foreground",
                            tone === "warning" && "bg-caution/10 text-caution",
                            tone === "error" && "bg-destructive/10 text-destructive",
                          )}
                        >
                          {line}
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>
            </div>
          </CardContent>
        </CollapsibleContent>
      </Card>
    </Collapsible>
  );
}
