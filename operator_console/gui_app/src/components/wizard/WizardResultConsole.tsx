import { JsonViewer } from "@/components/JsonViewer";
import { StatusBadge } from "@/components/StatusBadge";

interface WizardMetric {
  label: string;
  value: string | number;
}

interface WizardResultConsoleProps {
  title?: string;
  status: "success" | "failed";
  metrics?: WizardMetric[];
  payload: unknown;
}

export function WizardResultConsole({
  title = "Step Result",
  status,
  metrics = [],
  payload,
}: WizardResultConsoleProps) {
  return (
    <div className="space-y-3 rounded-xl border bg-card p-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <p className="text-sm font-semibold">{title}</p>
          <p className="text-xs text-muted-foreground">
            Stored results remain visible when revisiting a completed step.
          </p>
        </div>
        <StatusBadge
          label={status === "success" ? "Success" : "Failed"}
          severity={status === "success" ? "success" : "destructive"}
          dot
        />
      </div>

      {metrics.length > 0 && (
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

      <JsonViewer data={payload} title="Response Payload" />
    </div>
  );
}
