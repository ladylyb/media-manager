import { useEffect, useState } from "react";
import { Activity, RefreshCw } from "lucide-react";

import { getStatus } from "@/lib/api/endpoints";
import type { SystemStatus } from "@/types";
import { cn } from "@/lib/utils";

const STATUS_POLL_INTERVAL_MS = 120_000;

export function StatusStrip() {
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
      // Status refresh is informative only; keep the shell usable on failure.
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    let isMounted = true;

    const safeRefresh = async () => {
      if (!isMounted || document.visibilityState !== "visible") {
        return;
      }
      await refresh();
    };

    void safeRefresh();

    const interval = window.setInterval(() => {
      void safeRefresh();
    }, STATUS_POLL_INTERVAL_MS);

    const onVisibilityChange = () => {
      if (document.visibilityState === "visible") {
        void refresh();
      }
    };

    document.addEventListener("visibilitychange", onVisibilityChange);

    return () => {
      isMounted = false;
      window.clearInterval(interval);
      document.removeEventListener("visibilitychange", onVisibilityChange);
    };
  }, []);

  return (
    <div className="gradient-status-bar flex h-9 shrink-0 items-center justify-between border-b px-4 text-xs font-mono text-status-bar-foreground">
      <div className="flex items-center gap-4">
        <span className="flex items-center gap-1.5">
          <Activity className="h-3 w-3" />
          <span>Media Manager Console</span>
        </span>
        {status ? (
          <>
            <span className="text-muted-foreground">|</span>
            <span>Workflow v{status.workflow_version}</span>
            <span className="text-muted-foreground">|</span>
            <span>Schema v{status.schema_version}</span>
            {status.active_phase ? (
              <>
                <span className="text-muted-foreground">|</span>
                <span>Phase {status.active_phase}</span>
              </>
            ) : null}
          </>
        ) : null}
      </div>
      <div className="flex items-center gap-3">
        <span className="text-muted-foreground">Last: {lastRefresh.toLocaleTimeString()}</span>
        <button
          type="button"
          onClick={refresh}
          disabled={loading}
          className="transition-colors hover:text-foreground"
        >
          <RefreshCw className={cn("h-3 w-3", loading && "animate-spin")} />
        </button>
      </div>
    </div>
  );
}
