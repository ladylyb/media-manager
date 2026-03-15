import { useSearchParams } from "react-router-dom";
import { ErrorAlert } from "@/components/ErrorAlert";
import { StatusBadge } from "@/components/StatusBadge";
import { useApi } from "@/hooks/useApi";
import { getMediaByHash } from "@/lib/api/endpoints";
import type { MediaFileRecord } from "@/types/media";
import { FileIcon, ArrowLeft } from "lucide-react";
import { Link } from "react-router-dom";

export default function MediaDetail() {
  const [searchParams] = useSearchParams();
  const hash = searchParams.get("hash") || "";

  const { data, isLoading, error } = useApi<MediaFileRecord>(
    ["media-detail", hash],
    () => getMediaByHash(hash),
    { enabled: !!hash }
  );

  if (!hash) {
    return (
      <div className="p-6">
        <ErrorAlert message="No hash specified. Navigate here from the Gallery or Ledger." />
      </div>
    );
  }

  return (
    <div className="p-6 space-y-6 max-w-3xl">
      <div className="flex items-center gap-3">
        <Link to="/gallery" className="p-2 rounded-md hover:bg-muted transition-colors">
          <ArrowLeft className="h-4 w-4" />
        </Link>
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Media Detail</h1>
          <p className="text-sm text-muted-foreground mt-1">File record for hash {hash.slice(0, 16)}…</p>
        </div>
      </div>

      {error && <ErrorAlert message={error.message} />}

      {isLoading ? (
        <div className="rounded-lg border bg-card p-6 space-y-4 animate-pulse">
          <div className="h-6 w-48 bg-muted rounded" />
          <div className="h-4 w-full bg-muted rounded" />
          <div className="h-4 w-3/4 bg-muted rounded" />
        </div>
      ) : data ? (
        <div className="rounded-lg border bg-card p-6 space-y-4">
          <div className="flex items-center gap-3">
            <FileIcon className="h-8 w-8 text-muted-foreground" />
            <div>
              <h2 className="font-semibold">{data.path.split("/").pop()}</h2>
              <StatusBadge label={data.status} severity={data.status === "canonical" ? "success" : "neutral"} />
            </div>
          </div>

          <div className="grid grid-cols-2 gap-4 text-sm">
            <div>
              <p className="text-muted-foreground text-xs uppercase tracking-wider mb-1">Hash</p>
              <p className="font-mono text-xs break-all">{data.hash}</p>
            </div>
            <div>
              <p className="text-muted-foreground text-xs uppercase tracking-wider mb-1">Path</p>
              <p className="font-mono text-xs break-all">{data.path}</p>
            </div>
            <div>
              <p className="text-muted-foreground text-xs uppercase tracking-wider mb-1">First Seen</p>
              <p className="text-xs">{new Date(data.first_seen).toLocaleString()}</p>
            </div>
            <div>
              <p className="text-muted-foreground text-xs uppercase tracking-wider mb-1">Last Seen</p>
              <p className="text-xs">{new Date(data.last_seen).toLocaleString()}</p>
            </div>
            <div>
              <p className="text-muted-foreground text-xs uppercase tracking-wider mb-1">Size</p>
              <p className="text-xs">{(data.size_bytes / 1024).toFixed(1)} KB</p>
            </div>
            <div>
              <p className="text-muted-foreground text-xs uppercase tracking-wider mb-1">Status</p>
              <p className="text-xs">{data.status}</p>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
