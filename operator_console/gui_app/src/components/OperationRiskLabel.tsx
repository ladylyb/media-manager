import { Shield, ShieldAlert, Eye } from "lucide-react";
import { cn } from "@/lib/utils";

interface OperationRiskLabelProps {
  mutating: boolean;
  label?: string;
  className?: string;
}

export function OperationRiskLabel({ mutating, label, className }: OperationRiskLabelProps) {
  return (
    <span className={cn(
      "inline-flex items-center gap-1.5 rounded-md px-2 py-1 text-xs font-semibold uppercase tracking-wider border",
      mutating
        ? "bg-destructive/10 text-destructive border-destructive/30"
        : "bg-info/10 text-info border-info/30",
      className
    )}>
      {mutating ? <ShieldAlert className="h-3.5 w-3.5" /> : <Eye className="h-3.5 w-3.5" />}
      {label || (mutating ? "Mutating" : "Read-Only")}
    </span>
  );
}
