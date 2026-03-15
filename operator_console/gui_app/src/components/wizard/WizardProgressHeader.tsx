import { CheckCircle2, CircleDot, Lock, OctagonAlert, type LucideIcon } from "lucide-react";
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

function StatusIcon({ status }: { status: WizardProgressStatus }) {
  if (status === "completed") return <CheckCircle2 className="h-4 w-4 text-success" />;
  if (status === "current") return <CircleDot className="h-4 w-4 text-primary" />;
  if (status === "failed") return <OctagonAlert className="h-4 w-4 text-destructive" />;
  if (status === "blocked") return <Lock className="h-4 w-4 text-muted-foreground" />;
  return <span className="h-2.5 w-2.5 rounded-full bg-muted-foreground/60" />;
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
      <CardContent className="space-y-4 p-5">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="space-y-2">
            <p className="text-xs font-semibold uppercase tracking-[0.3em] text-muted-foreground">Pipeline Progress</p>
            <div>
              <p className="text-sm text-muted-foreground">
                Step {currentIndex + 1} of {totalSteps}
              </p>
              <h2 className="text-lg font-semibold tracking-tight">{currentTitle}</h2>
              <p className="text-sm text-muted-foreground">
                {currentKind === "execution" ? "Execution step" : "Review checkpoint"}
              </p>
            </div>
          </div>

          <div className="flex flex-wrap items-start justify-end gap-3">
            {secondaryAction}
            <div className="grid gap-3 sm:grid-cols-2">
              <div className="rounded-xl border bg-muted/15 p-3">
                <p className="text-[11px] font-semibold uppercase tracking-[0.2em] text-muted-foreground">Previous</p>
                <p className="mt-2 text-sm font-medium text-foreground/90">{previousTitle ?? "Start of guided run"}</p>
              </div>
              <div className="rounded-xl border bg-muted/15 p-3">
                <p className="text-[11px] font-semibold uppercase tracking-[0.2em] text-muted-foreground">Next</p>
                <p className="mt-2 text-sm font-medium text-foreground/90">{nextTitle ?? "Guided run complete"}</p>
              </div>
            </div>
          </div>
        </div>

        <div className="overflow-x-auto">
          <div className="flex min-w-max gap-2">
            {items.map((item, index) => (
              <div
                key={item.id}
                className={cn(
                  "flex min-w-[12rem] items-center gap-3 rounded-xl border px-3 py-3 transition-colors",
                  item.status === "current" && "border-primary/40 bg-primary/5",
                  item.status === "completed" && "border-success/30 bg-success/5",
                  item.status === "failed" && "border-destructive/30 bg-destructive/5",
                  item.status === "blocked" && "opacity-70",
                )}
              >
                <div className="flex items-center gap-2">
                  <StatusIcon status={item.status} />
                  <item.icon className="h-4 w-4 text-muted-foreground" />
                </div>
                <div className="min-w-0">
                  <p className="text-[11px] font-semibold uppercase tracking-[0.2em] text-muted-foreground">{index + 1}</p>
                  <p className="truncate text-sm font-medium">{item.title}</p>
                </div>
              </div>
            ))}
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
