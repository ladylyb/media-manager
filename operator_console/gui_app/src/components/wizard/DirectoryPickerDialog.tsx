import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { ChevronLeft, ChevronRight, FolderOpen, FolderTree, Loader2 } from "lucide-react";
import { ErrorAlert } from "@/components/ErrorAlert";
import { StatusBadge } from "@/components/StatusBadge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { getDirectoryPickerListing } from "@/lib/api/endpoints";
import { queryKeys } from "@/lib/api/queryKeys";
import { queryOptions } from "@/lib/api/queryOptions";
import type { DirectoryPickerCapability, DirectoryPickerRoot } from "@/types";
import { cn } from "@/lib/utils";

interface DirectoryPickerDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  capability: DirectoryPickerCapability | null;
  initialPath: string;
  onSelect: (path: string) => void;
}

function parseError(err: unknown): string {
  if (err instanceof Error) return err.message;
  return String(err);
}

function selectedRootForPath(roots: DirectoryPickerRoot[], path: string): DirectoryPickerRoot | null {
  return roots.find((root) => path === root.path || path.startsWith(`${root.path}/`)) ?? null;
}

function relativeSegments(rootPath: string, currentPath: string): string[] {
  if (!currentPath) return [];
  if (currentPath === rootPath) return [];
  if (!currentPath.startsWith(rootPath)) return [currentPath];

  return currentPath
    .slice(rootPath.length)
    .replace(/^\/+/, "")
    .split("/")
    .filter(Boolean);
}

export function DirectoryPickerDialog({
  open,
  onOpenChange,
  capability,
  initialPath,
  onSelect,
}: DirectoryPickerDialogProps) {
  const [currentPath, setCurrentPath] = useState("");

  useEffect(() => {
    if (!open || !capability?.roots.length) return;
    const fallback = capability.roots[0].path;
    const matchesKnownRoot = capability.roots.some((root) => initialPath.startsWith(root.path));
    setCurrentPath(matchesKnownRoot && initialPath ? initialPath : fallback);
  }, [open, capability, initialPath]);

  const listingQuery = useQuery({
    queryKey: queryKeys.directoryPickerListing(currentPath),
    queryFn: async () => (await getDirectoryPickerListing(currentPath)).data,
    staleTime: queryOptions.directoryPicker.staleTime,
    enabled: open && Boolean(currentPath),
  });

  const directories = listingQuery.data?.directories ?? [];
  const parentPath = listingQuery.data?.parent_path ?? null;
  const roots = capability?.roots ?? [];
  const selectedRoot = selectedRootForPath(roots, currentPath);
  const currentSegments = selectedRoot ? relativeSegments(selectedRoot.path, currentPath) : [];

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-3xl">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <FolderTree className="h-5 w-5" />
            Browse Server Directories
          </DialogTitle>
          <DialogDescription>
            First choose a configured server root, then browse into a folder inside that root. Use
            “Use This Path” to insert the currently selected folder into the wizard.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          <div className="space-y-3">
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.2em] text-muted-foreground">
                Configured Roots
              </p>
              <p className="mt-1 text-sm text-muted-foreground">
                These are the server-side starting locations you are allowed to browse.
              </p>
            </div>

            <div className="flex flex-wrap gap-2">
              {roots.map((root) => {
                const selected = currentPath === root.path || currentPath.startsWith(`${root.path}/`);
                return (
                  <button
                    key={root.path}
                    type="button"
                    onClick={() => setCurrentPath(root.path)}
                    className={cn(
                      "rounded-full border px-3 py-2 text-left text-sm transition-colors",
                      selected
                        ? "border-primary/30 bg-primary/10 text-primary"
                        : "border-border bg-background text-foreground hover:bg-muted/40",
                    )}
                  >
                    <div className="flex items-center gap-2">
                      <span className="font-medium">{root.label}</span>
                      {selected ? <StatusBadge label="Selected root" severity="info" className="text-[10px]" /> : null}
                    </div>
                  </button>
                );
              })}
            </div>
          </div>

          <div className="grid gap-3 lg:grid-cols-2">
            <div className="rounded-xl border bg-muted/20 p-3">
              <p className="text-xs font-semibold uppercase tracking-[0.2em] text-muted-foreground">
                Selected Root
              </p>
              <p className="mt-2 text-sm font-medium">{selectedRoot?.label ?? "--"}</p>
              <p className="mt-1 break-all font-mono text-xs text-muted-foreground">
                {selectedRoot?.path ?? "--"}
              </p>
            </div>

            <div className="rounded-xl border bg-muted/20 p-3">
              <p className="text-xs font-semibold uppercase tracking-[0.2em] text-muted-foreground">
                Current Folder
              </p>
              <div className="mt-2 flex flex-wrap items-center gap-1.5 text-sm">
                <span className="font-medium">{selectedRoot?.label ?? "Root"}</span>
                {currentSegments.length > 0
                  ? currentSegments.map((segment, index) => (
                      <div key={`${segment}-${index}`} className="flex items-center gap-1.5">
                        <ChevronRight className="h-3.5 w-3.5 text-muted-foreground" />
                        <span>{segment}</span>
                      </div>
                    ))
                  : (
                      <span className="text-muted-foreground">/</span>
                    )}
              </div>
              <p className="mt-2 break-all font-mono text-xs text-muted-foreground">{currentPath || "--"}</p>
            </div>
          </div>

          {listingQuery.error && <ErrorAlert message={parseError(listingQuery.error)} />}

          <div className="rounded-xl border bg-card">
            <div className="flex items-center justify-between border-b px-4 py-3">
              <div>
                <p className="text-sm font-semibold">Folders Inside This Location</p>
                <p className="text-xs text-muted-foreground">
                  Open a folder to move deeper into the selected root. You can only browse configured
                  roots and their descendants.
                </p>
              </div>
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => parentPath && setCurrentPath(parentPath)}
                disabled={!parentPath || listingQuery.isLoading}
              >
                <ChevronLeft className="mr-2 h-4 w-4" />
                Up
              </Button>
            </div>

            <div className="max-h-80 space-y-2 overflow-auto p-4">
              {listingQuery.isLoading ? (
                <div className="flex items-center gap-2 text-sm text-muted-foreground">
                  <Loader2 className="h-4 w-4 animate-spin" />
                  Loading directories...
                </div>
              ) : directories.length > 0 ? (
                directories.map((directory) => (
                  <button
                    key={directory.path}
                    type="button"
                    onClick={() => setCurrentPath(directory.path)}
                    className="flex w-full items-center justify-between rounded-lg border px-3 py-2 text-left transition-colors hover:bg-muted/40"
                  >
                    <div>
                      <p className="text-sm font-medium">{directory.name}</p>
                      <p className="mt-1 text-xs text-foreground/70">Open this folder</p>
                      <p className="mt-1 break-all font-mono text-xs text-muted-foreground">
                        {directory.path}
                      </p>
                    </div>
                    <FolderOpen className="h-4 w-4 text-muted-foreground" />
                  </button>
                ))
              ) : (
                <p className="text-sm text-muted-foreground">No subdirectories found for this location.</p>
              )}
            </div>
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button
            onClick={() => {
              onSelect(currentPath);
              onOpenChange(false);
            }}
            disabled={!currentPath}
          >
            Use This Path
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
