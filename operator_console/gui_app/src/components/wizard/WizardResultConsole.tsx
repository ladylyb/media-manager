import { useState } from "react";
import { ChevronDown, ChevronUp } from "lucide-react";
import { JsonViewer } from "@/components/JsonViewer";
import { StatusBadge } from "@/components/StatusBadge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";

interface WizardMetric {
  label: string;
  value: string | number;
}

interface WizardReferenceItem {
  label: string;
  value: string;
  helperText?: string;
  copyable?: boolean;
}

interface WizardResultConsoleProps {
  title?: string;
  status: "success" | "failed";
  metrics?: WizardMetric[];
  references?: WizardReferenceItem[];
  summaryLines?: string[];
  summaryTone?: "default" | "caution";
  nextStepHint?: string;
  nextStepTone?: "default" | "caution";
  payload: unknown;
  technicalDetailsMode?: "inline" | "modal";
}

export function WizardResultConsole({
  title = "Step Result",
  status,
  metrics = [],
  references = [],
  summaryLines = [],
  summaryTone = "default",
  nextStepHint,
  nextStepTone = "default",
  payload,
  technicalDetailsMode = "inline",
}: WizardResultConsoleProps) {
  const [technicalOpen, setTechnicalOpen] = useState(false);
  const [copiedReference, setCopiedReference] = useState<string | null>(null);
  const [open, setOpen] = useState(true);

  const copyReference = async (label: string, value: string) => {
    try {
      await navigator.clipboard.writeText(value);
      setCopiedReference(label);
      window.setTimeout(() => {
        setCopiedReference((current) => (current === label ? null : current));
      }, 2000);
    } catch {
      setCopiedReference(null);
    }
  };

  const summaryClass =
    summaryTone === "caution"
      ? "rounded-xl border border-caution/30 bg-caution/[0.08] p-4"
      : "rounded-xl border border-primary/15 bg-primary/[0.04] p-4";
  const summaryLabelClass =
    summaryTone === "caution"
      ? "text-[11px] font-semibold uppercase tracking-[0.2em] text-caution"
      : "text-[11px] font-semibold uppercase tracking-[0.2em] text-primary/80";
  const nextStepClass =
    nextStepTone === "caution"
      ? "rounded-xl border border-caution/30 bg-caution/[0.08] p-4"
      : "rounded-xl border border-success/20 bg-success/[0.05] p-4";
  const nextStepLabelClass =
    nextStepTone === "caution"
      ? "text-[11px] font-semibold uppercase tracking-[0.2em] text-caution"
      : "text-[11px] font-semibold uppercase tracking-[0.2em] text-success";

  return (
    <div className="space-y-3 rounded-xl border bg-card p-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="min-w-0 flex-1">
          <p className="text-sm font-semibold">{title}</p>
          <p className="text-xs text-muted-foreground">
            Stored results remain visible when revisiting a completed step.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <StatusBadge
            label={status === "success" ? "Success" : "Failed"}
            severity={status === "success" ? "success" : "destructive"}
            dot
          />
          <Button type="button" variant="outline" size="sm" onClick={() => setOpen((current) => !current)}>
            {open ? (
              <>
                <ChevronUp className="mr-2 h-4 w-4" />
                Hide result
              </>
            ) : (
              <>
                <ChevronDown className="mr-2 h-4 w-4" />
                Show result
              </>
            )}
          </Button>
        </div>
      </div>

      {open && summaryLines.length > 0 && (
        <div className={summaryClass}>
          <p className={summaryLabelClass}>
            What This Means
          </p>
          <div className="mt-3 space-y-2">
            {summaryLines.map((line, index) => (
              <p key={`${index}-${line}`} className="text-sm leading-6 text-foreground/90">
                {line}
              </p>
            ))}
          </div>
        </div>
      )}

      {open && references.length > 0 && (
        <div className="rounded-xl border border-border/70 bg-muted/15 p-4">
          <p className="text-[11px] font-semibold uppercase tracking-[0.2em] text-muted-foreground">
            Saved Plan
          </p>
          <div className="mt-3 space-y-3">
            {references.map((reference) => (
              <div
                key={`${reference.label}-${reference.value}`}
                className="flex flex-wrap items-start justify-between gap-3 rounded-lg border bg-background p-3"
              >
                <div className="min-w-0 flex-1">
                  <p className="text-[11px] font-semibold uppercase tracking-[0.2em] text-muted-foreground">
                    {reference.label}
                  </p>
                  <p className="mt-2 break-all font-mono text-sm text-foreground/90">{reference.value}</p>
                  {reference.helperText && (
                    <p className="mt-2 text-sm text-muted-foreground">{reference.helperText}</p>
                  )}
                </div>
                {reference.copyable && (
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={() => void copyReference(reference.label, reference.value)}
                  >
                    {copiedReference === reference.label ? "Copied" : "Copy"}
                  </Button>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {open && metrics.length > 0 && (
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          {metrics.map((metric) => (
            <div key={metric.label} className="rounded-lg border bg-muted/20 p-3">
              <p className="text-[11px] font-semibold uppercase tracking-[0.2em] text-muted-foreground">
                {metric.label}
              </p>
              <p className="mt-2 text-lg font-semibold">{metric.value}</p>
            </div>
          ))}
        </div>
      )}

      {open && nextStepHint && (
        <div className={nextStepClass}>
          <p className={nextStepLabelClass}>
            Recommended Next Step
          </p>
          <p className="mt-2 text-sm leading-6 text-foreground/90">{nextStepHint}</p>
        </div>
      )}

      {open && technicalDetailsMode === "inline" ? (
        <JsonViewer data={payload} title="Response Payload" />
      ) : open ? (
        <>
          <div className="flex justify-start">
            <Button type="button" variant="outline" size="sm" onClick={() => setTechnicalOpen(true)}>
              View technical response
            </Button>
          </div>
          <Dialog open={technicalOpen} onOpenChange={setTechnicalOpen}>
            <DialogContent className="max-w-3xl">
              <DialogHeader>
                <DialogTitle>{title} Technical Response</DialogTitle>
                <DialogDescription>
                  Raw API details remain available for debugging, but they are optional for the guided workflow.
                </DialogDescription>
              </DialogHeader>
              <JsonViewer data={payload} title="Response Payload" collapsible={false} maxHeight="60vh" />
            </DialogContent>
          </Dialog>
        </>
      ) : null}
    </div>
  );
}
