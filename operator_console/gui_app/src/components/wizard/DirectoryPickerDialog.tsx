import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { ChevronLeft, FolderTree, Loader2 } from "lucide-react";
import { ErrorAlert } from "@/components/ErrorAlert";
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
import type { DirectoryPickerCapability } from "@/types";

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

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-3xl">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <FolderTree className="h-5 w-5" />
            Browse Server Directories
          </DialogTitle>
          <DialogDescription>
            Choose a configured server-side directory and insert it into the wizard path field.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          <div className="flex flex-wrap gap-2">
            {capability?.roots.map((root) => (
              <Button
                key={root.path}
                type="button"
                variant={currentPath === root.path || currentPath.startsWith(`${root.path}/`) ? "default" : "outline"}
                size="sm"
                onClick={() => setCurrentPath(root.path)}
              >
                {root.label}
              </Button>
            ))}
          </div>

          <div className="rounded-xl border bg-muted/20 p-3">
            <p className="text-xs font-semibold uppercase tracking-[0.2em] text-muted-foreground">
              Current Path
            </p>
            <p className="mt-2 break-all font-mono text-sm">{currentPath || "--"}</p>
          </div>

          {listingQuery.error && <ErrorAlert message={parseError(listingQuery.error)} />}

          <div className="rounded-xl border bg-card">
            <div className="flex items-center justify-between border-b px-4 py-3">
              <div>
                <p className="text-sm font-semibold">Subdirectories</p>
                <p className="text-xs text-muted-foreground">
                  Only configured server roots and their descendants are browseable.
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
                      <p className="mt-1 break-all font-mono text-xs text-muted-foreground">
                        {directory.path}
                      </p>
                    </div>
                    <FolderTree className="h-4 w-4 text-muted-foreground" />
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
