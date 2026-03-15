import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { ErrorAlert } from "@/components/ErrorAlert";
import { EmptyState } from "@/components/EmptyState";
import { MetricCard } from "@/components/MetricCard";
import { StatusBadge } from "@/components/StatusBadge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { getDuplicates } from "@/lib/api/endpoints";
import { queryKeys } from "@/lib/api/queryKeys";
import { queryOptions } from "@/lib/api/queryOptions";
import type { DuplicateGroup } from "@/types";
import { Copy, Crown, FileIcon, FolderTree, Layers3, Sparkles } from "lucide-react";
import { Skeleton } from "@/components/ui/skeleton";

function getErrorMessage(err: unknown): string | null {
  if (!err) return null;
  if (err instanceof Error) return err.message;
  return String(err);
}

export default function DuplicatesPage() {
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const duplicatesQuery = useQuery({
    queryKey: queryKeys.duplicates,
    queryFn: async () => (await getDuplicates()).data,
    staleTime: queryOptions.duplicates.staleTime,
  });

  const groups = (duplicatesQuery.data as DuplicateGroup[] | undefined) ?? [];

  useEffect(() => {
    if (!selectedId && groups.length) {
      setSelectedId(groups[0].group_id);
    }
  }, [groups, selectedId]);

  const selected = groups.find(g => g.group_id === selectedId);
  const totalFiles = groups.reduce((sum, group) => sum + group.duplicates.length, 0);
  const duplicateFiles = groups.reduce(
    (sum, group) => sum + group.duplicates.filter(file => !file.is_canonical).length,
    0,
  );

  return (
    <div className="max-w-7xl space-y-4 p-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Duplicates</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Inspect duplicate groups, confirm canonical selections, and review the scope of deduplication work.
        </p>
      </div>
      {duplicatesQuery.error && (
        <ErrorAlert message={getErrorMessage(duplicatesQuery.error) || "Failed to load duplicate groups"} />
      )}

      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
        <MetricCard title="Groups" value={groups.length} subtitle="Detected duplicate clusters" icon={<Layers3 className="h-4 w-4" />} loading={duplicatesQuery.isLoading} />
        <MetricCard title="Files In Groups" value={totalFiles} subtitle="Canonical plus duplicate members" icon={<FolderTree className="h-4 w-4" />} loading={duplicatesQuery.isLoading} />
        <MetricCard title="Non-Canonical" value={duplicateFiles} subtitle="Duplicate candidates" icon={<Copy className="h-4 w-4" />} loading={duplicatesQuery.isLoading} />
        <MetricCard title="Selected Group" value={selected ? selected.duplicates.length : 0} subtitle={selected ? "Files in current selection" : "Select a group to inspect"} icon={<Sparkles className="h-4 w-4" />} loading={duplicatesQuery.isLoading} />
      </div>

      {duplicatesQuery.isLoading ? (
        <div className="flex h-[calc(100vh-200px)] gap-4">
          <div className="w-80 space-y-2">
            {Array.from({ length: 8 }).map((_, i) => (
              <Skeleton key={i} className="h-14 w-full rounded-lg" />
            ))}
          </div>
          <div className="flex-1">
            <Skeleton className="h-full rounded-lg" />
          </div>
        </div>
      ) : !groups.length ? (
        <EmptyState
          icon={<Copy className="h-10 w-10" />}
          title="No duplicate groups"
          description="Run an ingest + plan cycle to detect duplicates"
        />
      ) : (
        <div className="flex h-[calc(100vh-200px)] gap-4">
          <Card className="w-80 shrink-0 overflow-hidden">
            <CardHeader className="pb-3">
              <CardDescription>Duplicate Groups</CardDescription>
              <CardTitle className="text-xl">Detected clusters</CardTitle>
            </CardHeader>
            <CardContent className="space-y-2 overflow-auto scrollbar-thin p-3 pt-0">
              {groups.map(g => (
                <button
                  key={g.group_id}
                  onClick={() => setSelectedId(g.group_id)}
                  className={`w-full rounded-md border px-3 py-2.5 text-left transition-colors ${selectedId === g.group_id ? "border-primary/30 bg-primary/10" : "border-transparent hover:bg-muted"}`}
                >
                  <div className="flex items-start justify-between gap-2">
                    <p className="truncate text-xs font-mono">{g.hash.slice(0, 20)}…</p>
                    <StatusBadge label={`${g.duplicates.length} files`} severity="neutral" />
                  </div>
                  <p className="mt-2 truncate text-xs text-muted-foreground">{g.canonical_path}</p>
                </button>
              ))}
            </CardContent>
          </Card>

          <Card className="flex-1 overflow-auto scrollbar-thin">
            <CardHeader className="pb-3">
              <CardDescription>Group Details</CardDescription>
              <CardTitle className="text-xl">
                {selected ? `Group ${selected.group_id}` : "Select a duplicate group"}
              </CardTitle>
            </CardHeader>
            <CardContent>
              {selected ? (
                <div className="space-y-6">
                  <div className="grid gap-3 md:grid-cols-3">
                    <div className="rounded-lg border bg-muted/20 p-4 md:col-span-2">
                      <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">Hash</p>
                      <p className="mt-2 break-all font-mono text-xs">{selected.hash}</p>
                    </div>
                    <div className="rounded-lg border bg-muted/20 p-4">
                      <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">Duplicates</p>
                      <p className="mt-2 font-mono text-2xl font-bold">
                        {selected.duplicates.filter(d => !d.is_canonical).length}
                      </p>
                    </div>
                  </div>
                  <div>
                    <h4 className="mb-2 text-xs font-semibold uppercase tracking-wider text-muted-foreground">Canonical</h4>
                    <div className="flex items-center gap-3 rounded-md border-2 border-success/30 bg-success/5 p-4">
                      <Crown className="h-5 w-5 shrink-0 text-success" />
                      <div className="min-w-0">
                        <p className="truncate text-sm font-mono">{selected.canonical_path}</p>
                        <StatusBadge label="Canonical" severity="success" className="mt-2" />
                      </div>
                    </div>
                  </div>
                  <div>
                    <h4 className="mb-2 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                      Duplicates ({selected.duplicates.filter(d => !d.is_canonical).length})
                    </h4>
                    <div className="space-y-2">
                      {selected.duplicates
                        .filter(d => !d.is_canonical)
                        .map((d, i) => (
                          <div key={i} className="flex items-center gap-3 rounded-md border bg-muted/10 p-3">
                            <FileIcon className="h-4 w-4 shrink-0 text-muted-foreground" />
                            <div className="min-w-0">
                              <p className="truncate text-sm font-mono">{d.path}</p>
                              <p className="text-xs text-muted-foreground">
                                {(d.size_bytes / 1024).toFixed(1)} KB • {new Date(d.created_at).toLocaleDateString()}
                              </p>
                            </div>
                          </div>
                        ))}
                    </div>
                  </div>
                </div>
              ) : (
                <EmptyState
                  title="Select a group"
                  description="Click a duplicate group on the left to inspect its canonical file and remaining duplicates."
                />
              )}
            </CardContent>
          </Card>
        </div>
      )}
    </div>
  );
}
