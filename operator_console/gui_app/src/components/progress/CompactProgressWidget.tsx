import { ChevronDown, ChevronUp } from "lucide-react";
import { StatusBadge } from "@/components/StatusBadge";
import { Button } from "@/components/ui/button";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { Progress } from "@/components/ui/progress";
import { fetchLogs } from "@/lib/api/endpoints/system";
import { mergeLogLines, parseProgressLogs } from "@/lib/logs/parseProgressLogs";
import { useEffect, useMemo, useState } from "react";

function compactLabel(phase: "ingest" | "plan" | null, status: "idle" | "running" | "error") {
  if (status === "running" && phase === "plan") return "Plan running";
  if (status === "running" && phase === "ingest") return "Ingest running";
  return "Waiting for logs";
}

export function CompactProgressWidget() {
  const [lines, setLines] = useState<string[]>([]);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    let cancelled = false;

    const loadLogs = async () => {
      try {
        const nextLines = await fetchLogs(100);
        if (cancelled) return;
        setLines((current) => mergeLogLines(current, nextLines, 100));
      } catch {
        if (cancelled) return;
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
  const progressValue = Math.max(0, Math.min(100, parsed.progressPercent ?? 0));

  return (
    <Collapsible open={open} onOpenChange={setOpen}>
      <div className="rounded-xl border border-sidebar-border bg-sidebar-accent/50 p-3">
        <div className="flex items-center justify-between gap-2">
          <div className="min-w-0">
            <p className="text-[10px] font-semibold uppercase tracking-[0.22em] text-sidebar-muted">
              Live Progress
            </p>
            <p className="mt-1 text-xs text-sidebar-foreground">
              {parsed.processedCount ?? 0} / {parsed.totalCount ?? 0} files
            </p>
          </div>
          <div className="flex flex-col items-end gap-2">
            <StatusBadge
              label={compactLabel(parsed.phase, parsed.status)}
              severity={parsed.status === "running" ? "info" : "neutral"}
              className="border-sidebar-border bg-sidebar/60 text-sidebar-foreground"
              dot={parsed.status === "running"}
            />
            <CollapsibleTrigger asChild>
              <Button
                type="button"
                variant="ghost"
                size="sm"
                className="h-auto px-0 py-0 text-[10px] text-sidebar-foreground hover:bg-transparent"
              >
                {open ? (
                  <>
                    <ChevronUp className="mr-1 h-3.5 w-3.5" />
                    Hide
                  </>
                ) : (
                  <>
                    <ChevronDown className="mr-1 h-3.5 w-3.5" />
                    Show
                  </>
                )}
              </Button>
            </CollapsibleTrigger>
          </div>
        </div>
        <CollapsibleContent>
          <div className="mt-3 space-y-2 border-t border-sidebar-border pt-3">
            <Progress value={progressValue} className="h-1.5 bg-sidebar/70" />
            <p className="text-xs text-sidebar-foreground">
              {parsed.processedCount ?? 0} / {parsed.totalCount ?? 0} files
            </p>
          </div>
        </CollapsibleContent>
      </div>
    </Collapsible>
  );
}
