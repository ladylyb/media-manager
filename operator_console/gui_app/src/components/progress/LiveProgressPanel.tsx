import { ChevronDown, ChevronUp } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";

import { StatusBadge } from "@/components/StatusBadge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { Progress } from "@/components/ui/progress";
import { fetchLogs } from "@/lib/api/endpoints/system";
import { cn } from "@/lib/utils";
import { getLogLineTone, mergeLogLines, parseProgressLogs } from "@/lib/logs/parseProgressLogs";

function formatHeaderLabel(phase: "ingest" | "plan" | null, status: "idle" | "running" | "error") {
  if (status === "running" && phase === "plan") return "[ PLAN RUNNING ]";
  if (status === "running" && phase === "ingest") return "[ INGEST RUNNING ]";
  return "[ WAITING FOR LOGS ]";
}

function formatPhaseLabel(phase: "ingest" | "plan" | null) {
  if (phase === "plan") return "Planning";
  if (phase === "ingest") return "Ingest";
  return "Idle";
}

export function LiveProgressPanel({ className }: { className?: string }) {
  const [lines, setLines] = useState<string[]>([]);
  const [fetchError, setFetchError] = useState<string | null>(null);
  // Optional support panels in this UI default collapsed so the main workflow stays visually primary.
  const [open, setOpen] = useState(false);
  const logViewportRef = useRef<HTMLDivElement | null>(null);
  const shouldAutoScrollRef = useRef(true);

  useEffect(() => {
    let cancelled = false;

    const loadLogs = async () => {
      try {
        // Poll the lightweight log buffer directly so the panel stays read-only and self-contained.
        const nextLines = await fetchLogs(100);
        if (cancelled) return;
        setLines((current) => mergeLogLines(current, nextLines, 100));
        setFetchError(null);
      } catch (error) {
        if (cancelled) return;
        setFetchError(error instanceof Error ? error.message : "Unable to load logs.");
      }
    };

    void loadLogs();
    const intervalId = window.setInterval(() => {
      void loadLogs();
    }, 1_000);

    return () => {
      cancelled = true;
      window.clearInterval(intervalId);
    };
  }, []);

  const parsed = useMemo(() => parseProgressLogs(lines), [lines]);

  useEffect(() => {
    const viewport = logViewportRef.current;
    if (!viewport || !shouldAutoScrollRef.current) return;
    viewport.scrollTop = viewport.scrollHeight;
  }, [lines]);

  const progressValue = Math.max(0, Math.min(100, parsed.progressPercent ?? 0));
  const badgeSeverity =
    parsed.status === "running"
      ? "info"
      : fetchError
        ? "caution"
        : "neutral";

  return (
    <Collapsible open={open} onOpenChange={setOpen}>
      <Card className={cn("rounded-2xl border-border/70 bg-card/95 shadow-sm", className)}>
        <CardHeader className="space-y-3 pb-3">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <CardTitle className="font-mono text-sm tracking-[0.24em] text-foreground">
              {formatHeaderLabel(parsed.phase, parsed.status)}
            </CardTitle>
            <div className="flex items-center gap-2">
              <StatusBadge
                label={formatPhaseLabel(parsed.phase)}
                severity={badgeSeverity}
                dot={parsed.status === "running"}
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
            <div className="grid gap-3 md:grid-cols-3">
              <div className="rounded-xl border bg-muted/20 p-3">
                <p className="text-[11px] font-semibold uppercase tracking-[0.2em] text-muted-foreground">
                  Progress
                </p>
                <p className="mt-2 text-lg font-semibold">{(parsed.progressPercent ?? 0).toFixed(1)}%</p>
              </div>
              <div className="rounded-xl border bg-muted/20 p-3">
                <p className="text-[11px] font-semibold uppercase tracking-[0.2em] text-muted-foreground">
                  Files
                </p>
                <p className="mt-2 text-lg font-semibold">
                  {parsed.processedCount ?? 0} / {parsed.totalCount ?? 0}
                </p>
              </div>
              <div className="rounded-xl border bg-muted/20 p-3">
                <p className="text-[11px] font-semibold uppercase tracking-[0.2em] text-muted-foreground">
                  Speed
                </p>
                <p className="mt-2 text-lg font-semibold">{(parsed.throughputFps ?? 0).toFixed(1)} files/sec</p>
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
