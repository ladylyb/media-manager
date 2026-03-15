import { CheckCircle2, CircleDot, Lock, OctagonAlert, type LucideIcon } from "lucide-react";
import { StatusBadge } from "@/components/StatusBadge";
import { cn } from "@/lib/utils";

export type WizardSidebarStatus = "completed" | "current" | "pending" | "failed" | "blocked";

export interface WizardSidebarItem {
  id: string;
  title: string;
  kind: "execution" | "checkpoint";
  status: WizardSidebarStatus;
  icon: LucideIcon;
}

function StatusIcon({ status }: { status: WizardSidebarStatus }) {
  if (status === "completed") {
    return <CheckCircle2 className="h-4 w-4 text-success" />;
  }
  if (status === "current") {
    return <CircleDot className="h-4 w-4 text-primary" />;
  }
  if (status === "failed") {
    return <OctagonAlert className="h-4 w-4 text-destructive" />;
  }
  if (status === "blocked") {
    return <Lock className="h-4 w-4 text-muted-foreground" />;
  }
  return <span className="h-2.5 w-2.5 rounded-full bg-muted-foreground/60" />;
}

export function WizardSidebar({ items }: { items: WizardSidebarItem[] }) {
  return (
    <aside className="rounded-2xl border bg-card p-4 shadow-sm">
      <div className="space-y-1">
        <p className="text-xs font-semibold uppercase tracking-[0.3em] text-muted-foreground">
          Pipeline Steps
        </p>
        <h2 className="text-lg font-semibold">Checkpoint Wizard</h2>
      </div>

      <div className="mt-5 space-y-2">
        {items.map((item, index) => (
          <div
            key={item.id}
            className={cn(
              "rounded-xl border p-3 transition-colors",
              item.status === "current" && "border-primary/40 bg-primary/5",
              item.status === "completed" && "border-success/30 bg-success/5",
              item.status === "failed" && "border-destructive/30 bg-destructive/5",
              item.status === "blocked" && "opacity-70",
            )}
          >
            <div className="flex items-start gap-3">
              <div className="mt-0.5 flex items-center gap-2">
                <StatusIcon status={item.status} />
                <item.icon className="h-4 w-4 text-muted-foreground" />
              </div>
              <div className="min-w-0 flex-1">
                <div className="flex items-center justify-between gap-2">
                  <p className="text-sm font-medium">
                    {index + 1}. {item.title}
                  </p>
                </div>
                <div className="mt-2 flex flex-wrap gap-2">
                  <StatusBadge
                    label={item.kind === "execution" ? "Operation" : "Review Checkpoint"}
                    severity={item.kind === "execution" ? "info" : "neutral"}
                  />
                  <StatusBadge
                    label={item.status}
                    severity={
                      item.status === "completed"
                        ? "success"
                        : item.status === "current"
                          ? "info"
                          : item.status === "failed"
                            ? "destructive"
                            : item.status === "blocked"
                              ? "caution"
                              : "neutral"
                    }
                  />
                </div>
              </div>
            </div>
          </div>
        ))}
      </div>
    </aside>
  );
}
