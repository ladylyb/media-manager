import { useEffect, useState } from "react";
import { ErrorAlert } from "@/components/ErrorAlert";
import { EmptyState } from "@/components/EmptyState";
import { StatusBadge } from "@/components/StatusBadge";
import { getDuplicates } from "@/lib/api/endpoints";
import type { DuplicateGroup } from "@/types/api";
import { Copy, Crown, FileIcon, Loader2 } from "lucide-react";
import { Skeleton } from "@/components/ui/skeleton";

export default function DuplicatesPage() {
  const [groups, setGroups] = useState<DuplicateGroup[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);

  useEffect(() => {
    getDuplicates()
      .then(e => { setGroups(e.data); if (e.data.length) setSelectedId(e.data[0].group_id); })
      .catch(e => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  const selected = groups.find(g => g.group_id === selectedId);

  return (
    <div className="p-6 space-y-4 max-w-7xl">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Duplicates</h1>
        <p className="text-sm text-muted-foreground mt-1">Inspect duplicate groups and canonical selections</p>
      </div>
      {error && <ErrorAlert message={error} onDismiss={() => setError(null)} />}

      {loading ? (
        <div className="flex gap-4 h-[calc(100vh-200px)]">
          <div className="w-80 space-y-2">{Array.from({ length: 8 }).map((_, i) => <Skeleton key={i} className="h-14 w-full rounded-lg" />)}</div>
          <div className="flex-1"><Skeleton className="h-full rounded-lg" /></div>
        </div>
      ) : !groups.length ? (
        <EmptyState icon={<Copy className="h-10 w-10" />} title="No duplicate groups" description="Run an ingest + plan cycle to detect duplicates" />
      ) : (
        <div className="flex gap-4 h-[calc(100vh-200px)]">
          {/* Group List */}
          <div className="w-80 shrink-0 overflow-auto scrollbar-thin space-y-1 border rounded-lg bg-card p-2">
            {groups.map(g => (
              <button
                key={g.group_id}
                onClick={() => setSelectedId(g.group_id)}
                className={`w-full text-left rounded-md px-3 py-2.5 transition-colors ${selectedId === g.group_id ? "bg-primary/10 border border-primary/30" : "hover:bg-muted border border-transparent"}`}
              >
                <p className="text-xs font-mono truncate">{g.hash.slice(0, 20)}…</p>
                <div className="flex items-center gap-2 mt-1">
                  <StatusBadge label={`${g.duplicates.length} files`} severity="neutral" />
                </div>
              </button>
            ))}
          </div>

          {/* Details */}
          <div className="flex-1 border rounded-lg bg-card p-5 overflow-auto scrollbar-thin">
            {selected ? (
              <div className="space-y-4">
                <div>
                  <h3 className="font-semibold text-sm">Group {selected.group_id}</h3>
                  <p className="text-xs font-mono text-muted-foreground mt-1">Hash: {selected.hash}</p>
                </div>
                <div>
                  <h4 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-2">Canonical</h4>
                  <div className="rounded-md border-2 border-success/30 bg-success/5 p-3 flex items-center gap-3">
                    <Crown className="h-5 w-5 text-success shrink-0" />
                    <div>
                      <p className="text-sm font-mono">{selected.canonical_path}</p>
                      <StatusBadge label="Canonical" severity="success" className="mt-1" />
                    </div>
                  </div>
                </div>
                <div>
                  <h4 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-2">Duplicates ({selected.duplicates.filter(d => !d.is_canonical).length})</h4>
                  <div className="space-y-2">
                    {selected.duplicates.filter(d => !d.is_canonical).map((d, i) => (
                      <div key={i} className="rounded-md border p-3 flex items-center gap-3">
                        <FileIcon className="h-4 w-4 text-muted-foreground shrink-0" />
                        <div className="min-w-0">
                          <p className="text-sm font-mono truncate">{d.path}</p>
                          <p className="text-xs text-muted-foreground">{(d.size_bytes / 1024).toFixed(1)} KB • {new Date(d.created_at).toLocaleDateString()}</p>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            ) : (
              <EmptyState title="Select a group" description="Click a duplicate group on the left to view details" />
            )}
          </div>
        </div>
      )}
    </div>
  );
}
