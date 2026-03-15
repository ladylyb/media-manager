import { Check, Lock, OctagonAlert, type LucideIcon } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { cn } from "@/lib/utils";
import type { ReactNode } from "react";

export type WizardProgressStatus = "completed" | "current" | "pending" | "failed" | "blocked";

export interface WizardProgressItem {
  id: string;
  title: string;
  kind: "execution" | "checkpoint";
  status: WizardProgressStatus;
  icon: LucideIcon;
}

interface WizardProgressHeaderProps {
  currentIndex: number;
  totalSteps: number;
  currentTitle: string;
  currentKind: "execution" | "checkpoint";
  previousTitle?: string | null;
  nextTitle?: string | null;
  items: WizardProgressItem[];
  secondaryAction?: ReactNode;
}

function StepMarker({
  status,
  stepNumber,
  title,
}: {
  status: WizardProgressStatus;
  stepNumber: number;
  title: string;
}) {
  if (status === "completed") {
    return (
      <div
        title={`Step ${stepNumber}: ${title} (completed)`}
        className="flex h-7 w-7 items-center justify-center rounded-full bg-success text-success-foreground shadow-sm"
      >
        <Check className="h-4 w-4" />
      </div>
    );
  }

  if (status === "current") {
    return (
      <div
        title={`Step ${stepNumber}: ${title} (current)`}
        className="flex h-9 min-w-9 items-center justify-center rounded-full bg-primary px-2 text-sm font-semibold text-primary-foreground shadow-sm"
      >
        {stepNumber}
      </div>
    );
  }

  if (status === "failed") {
    return (
      <div
        title={`Step ${stepNumber}: ${title} (failed)`}
        className="flex h-7 w-7 items-center justify-center rounded-full bg-destructive text-destructive-foreground shadow-sm"
      >
        <OctagonAlert className="h-4 w-4" />
      </div>
    );
  }

  if (status === "blocked") {
    return (
      <div
        title={`Step ${stepNumber}: ${title} (blocked)`}
        className="flex h-6 w-6 items-center justify-center rounded-full bg-muted text-muted-foreground"
      >
        <Lock className="h-3.5 w-3.5" />
      </div>
    );
  }

  return <div title={`Step ${stepNumber}: ${title} (upcoming)`} className="h-3.5 w-3.5 rounded-full bg-muted-foreground/45" />;
}

function StepConnector({ active }: { active: boolean }) {
  return <div className={cn("h-0.5 flex-1 rounded-full", active ? "bg-primary/45" : "bg-border")} />;
}

export function WizardProgressHeader({
  currentIndex,
  totalSteps,
  currentTitle,
  currentKind,
  previousTitle,
  nextTitle,
  items,
  secondaryAction,
}: WizardProgressHeaderProps) {
  return (
    <Card className="rounded-2xl border-border/80 bg-card/80 shadow-sm">
      <CardContent className="space-y-3 p-4">
        <div className="flex items-center justify-between gap-4">
          <div className="min-w-0 flex-1 space-y-2">
            <p className="text-xs font-semibold uppercase tracking-[0.3em] text-muted-foreground">Progress</p>
            <div className="flex items-center gap-2">
              {items.map((item, index) => (
                <div key={item.id} className="flex min-w-0 flex-1 items-center gap-2">
                  <StepMarker status={item.status} stepNumber={index + 1} title={item.title} />
                  {index < items.length - 1 && <StepConnector active={item.status === "completed" || item.status === "current"} />}
                </div>
              ))}
            </div>
          </div>
          {secondaryAction}
        </div>

        <div className="space-y-1">
          <p className="text-sm text-muted-foreground">
            Step {currentIndex + 1} of {totalSteps}
          </p>
          <h2 className="text-xl font-semibold tracking-tight">{currentTitle}</h2>
          <p className="text-sm text-muted-foreground">
            {currentKind === "execution" ? "Execution step" : "Review checkpoint"}
          </p>
        </div>

        <div className="flex flex-wrap gap-2 text-sm">
          <div className="rounded-full bg-muted px-3 py-1.5 text-muted-foreground">
            <span className="font-semibold text-foreground/80">Previous:</span>{" "}
            <span>{previousTitle ?? "Start of guided run"}</span>
          </div>
          <div className="rounded-full bg-muted px-3 py-1.5 text-muted-foreground">
            <span className="font-semibold text-foreground/80">Next:</span>{" "}
            <span>{nextTitle ?? "Guided run complete"}</span>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
