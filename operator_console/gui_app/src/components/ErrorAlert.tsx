import { AlertTriangle, XCircle, Info } from "lucide-react";
import { cn } from "@/lib/utils";

interface ErrorAlertProps {
  title?: string;
  message: string;
  severity?: "error" | "warning" | "info";
  className?: string;
  onDismiss?: () => void;
}

const styles = {
  error: "bg-destructive/10 border-destructive/30 text-destructive",
  warning: "bg-caution/10 border-caution/30 text-caution",
  info: "bg-info/10 border-info/30 text-info",
};

const icons = {
  error: XCircle,
  warning: AlertTriangle,
  info: Info,
};

export function ErrorAlert({ title, message, severity = "error", className, onDismiss }: ErrorAlertProps) {
  const Icon = icons[severity];
  return (
    <div className={cn("flex items-start gap-3 rounded-lg border p-4", styles[severity], className)}>
      <Icon className="h-5 w-5 mt-0.5 shrink-0" />
      <div className="flex-1 min-w-0">
        {title && <p className="font-semibold text-sm">{title}</p>}
        <p className="text-sm">{message}</p>
      </div>
      {onDismiss && (
        <button onClick={onDismiss} className="text-current opacity-60 hover:opacity-100">
          <XCircle className="h-4 w-4" />
        </button>
      )}
    </div>
  );
}
