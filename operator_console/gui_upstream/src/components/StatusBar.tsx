import { useEffect, useState } from "react";
import { getStatus } from "@/lib/api/endpoints";
import type { SystemStatus } from "@/types/api";
import { cn } from "@/lib/utils";
import { Activity, RefreshCw, Database } from "lucide-react";

export function StatusBar() {
  const [status, setStatus] = useState<SystemStatus | null>(null);
  const [lastRefresh, setLastRefresh] = useState<Date>(new Date());
  const [loading, setLoading] = useState(false);

  const refresh = async () => {
    setLoading(true);
    try {
      const envelope = await getStatus();
      setStatus(envelope.data);
      setLastRefresh(new Date());
    } catch {
      // silently fail - status bar is non-critical
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    refresh();
    const interval = setInterval(refresh, 30000);
    return () => clearInterval(interval);
  }, []);

  return (
    <div className="gradient-status-bar border-b flex items-center justify-between px-4 h-9 text-xs font-mono text-status-bar-foreground shrink-0">
      <div className="flex items-center gap-4">
        <span className="flex items-center gap-1.5">
          <Activity className="h-3 w-3" />
          <span>Media Manager Console</span>
        </span>
        {status && (
          <>
            <span className="text-muted-foreground">|</span>
            <span>Workflow v{status.workflow_version}</span>
            <span className="text-muted-foreground">|</span>
            <span>Schema v{status.schema_version}</span>
            <span className="text-muted-foreground">|</span>
            <span className="flex items-center gap-1">
              <Database className="h-3 w-3" />
              <span className={cn(status.database_connected ? "text-success" : "text-destructive")}>
                {status.database_connected ? "Connected" : "Disconnected"}
              </span>
            </span>
          </>
        )}
      </div>
      <div className="flex items-center gap-3">
        <span className="text-muted-foreground">Last: {lastRefresh.toLocaleTimeString()}</span>
        <button onClick={refresh} disabled={loading} className="hover:text-foreground transition-colors">
          <RefreshCw className={cn("h-3 w-3", loading && "animate-spin")} />
        </button>
      </div>
    </div>
  );
}
