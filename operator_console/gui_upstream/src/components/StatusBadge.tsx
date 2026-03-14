import { cn } from "@/lib/utils";

type Severity = "info" | "success" | "caution" | "destructive" | "neutral";

const severityStyles: Record<Severity, string> = {
  info: "bg-info/15 text-info border-info/30",
  success: "bg-success/15 text-success border-success/30",
  caution: "bg-caution/15 text-caution border-caution/30",
  destructive: "bg-destructive/15 text-destructive border-destructive/30",
  neutral: "bg-muted text-muted-foreground border-border",
};

interface StatusBadgeProps {
  label: string;
  severity?: Severity;
  className?: string;
  dot?: boolean;
}

export function StatusBadge({ label, severity = "neutral", className, dot = false }: StatusBadgeProps) {
  return (
    <span className={cn("inline-flex items-center gap-1.5 rounded-md border px-2 py-0.5 text-xs font-medium font-mono", severityStyles[severity], className)}>
      {dot && <span className={cn("h-1.5 w-1.5 rounded-full", severity === "success" ? "bg-success" : severity === "destructive" ? "bg-destructive" : severity === "caution" ? "bg-caution" : severity === "info" ? "bg-info" : "bg-muted-foreground")} />}
      {label}
    </span>
  );
}
