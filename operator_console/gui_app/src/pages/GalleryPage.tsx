import { useEffect, useState, useCallback } from "react";
import { useSearchParams } from "react-router-dom";
import { ErrorAlert } from "@/components/ErrorAlert";
import { EmptyState } from "@/components/EmptyState";
import { StatusBadge } from "@/components/StatusBadge";
import { getCanonical } from "@/lib/api/endpoints";
import type { CanonicalFile, PaginatedResponse } from "@/types/api";
import { ImageIcon, Video, FileIcon } from "lucide-react";
import { Skeleton } from "@/components/ui/skeleton";
import { Dialog, DialogContent } from "@/components/ui/dialog";

export default function GalleryPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [data, setData] = useState<PaginatedResponse<CanonicalFile> | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedFile, setSelectedFile] = useState<CanonicalFile | null>(null);
  const page = Number(searchParams.get("page") || 1);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await getCanonical({ page, limit: 30 });
      setData(res.data);
    } catch (err: any) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [page]);

  useEffect(() => {
    load();
  }, [load]);

  const isVideo = (fileType: string) => fileType === "video";

  return (
    <div className="p-6 space-y-6 max-w-7xl">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Gallery</h1>
        <p className="text-sm text-muted-foreground mt-1">Canonical media browser</p>
      </div>

      {error && <ErrorAlert message={error} onDismiss={() => setError(null)} />}

      {loading ? (
        <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-3">
          {Array.from({ length: 18 }).map((_, i) => <Skeleton key={i} className="aspect-square rounded-lg" />)}
        </div>
      ) : !data?.items.length ? (
        <EmptyState icon={<ImageIcon className="h-10 w-10" />} title="No media files" description="Run an ingest to populate the gallery" />
      ) : (
        <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-3">
          {data.items.map((file) => (
            <button
              key={file.id}
              onClick={() => setSelectedFile(file)}
              className="rounded-lg border bg-card overflow-hidden hover:border-primary/30 transition-colors group text-left"
            >
              <div className="aspect-square bg-muted flex items-center justify-center overflow-hidden relative">
                {file.media_url ? (
                  <img src={file.media_url} alt={file.filename} className="w-full h-full object-cover group-hover:scale-105 transition-transform" />
                ) : isVideo(file.file_type) ? (
                  <Video className="h-8 w-8 text-muted-foreground" />
                ) : (
                  <ImageIcon className="h-8 w-8 text-muted-foreground" />
                )}
                {isVideo(file.file_type) && (
                  <span className="absolute top-2 right-2 bg-card/80 backdrop-blur rounded px-1.5 py-0.5 text-[10px] font-semibold">VIDEO</span>
                )}
              </div>
              <div className="p-2">
                <p className="text-xs font-mono truncate text-muted-foreground">{file.filename}</p>
              </div>
            </button>
          ))}
        </div>
      )}

      {data && data.total_pages > 1 && (
        <div className="flex items-center justify-center gap-2">
          <button onClick={() => setSearchParams({ page: String(Math.max(1, page - 1)) })} disabled={page === 1} className="px-3 py-1 text-sm rounded border disabled:opacity-50">Prev</button>
          <span className="text-xs text-muted-foreground">Page {page} of {data.total_pages}</span>
          <button onClick={() => setSearchParams({ page: String(Math.min(data.total_pages, page + 1)) })} disabled={page === data.total_pages} className="px-3 py-1 text-sm rounded border disabled:opacity-50">Next</button>
        </div>
      )}

      <Dialog open={!!selectedFile} onOpenChange={() => setSelectedFile(null)}>
        <DialogContent className="max-w-2xl max-h-[90vh] overflow-auto">
          {selectedFile && (
            <div className="space-y-4">
              <div className="aspect-video bg-muted rounded-lg flex items-center justify-center overflow-hidden">
                {selectedFile.media_url ? (
                  isVideo(selectedFile.file_type) ? (
                    <video src={selectedFile.media_url} controls className="w-full h-full object-contain" />
                  ) : (
                    <img src={selectedFile.media_url} alt={selectedFile.filename} className="w-full h-full object-contain" />
                  )
                ) : (
                  <FileIcon className="h-16 w-16 text-muted-foreground" />
                )}
              </div>
              <div className="space-y-3">
                <h3 className="font-semibold">{selectedFile.filename}</h3>
                <div className="grid grid-cols-2 gap-2 text-sm">
                  <div><span className="text-muted-foreground">Media URL:</span><p className="font-mono text-xs mt-0.5 break-all">{selectedFile.media_url}</p></div>
                  <div><span className="text-muted-foreground">ID:</span><p className="font-mono text-xs mt-0.5 break-all">{selectedFile.id}</p></div>
                  <div><span className="text-muted-foreground">Type:</span><p className="text-xs mt-0.5">{selectedFile.file_type}</p></div>
                </div>
                {selectedFile.matched_tags && selectedFile.matched_tags.length > 0 && (
                  <div>
                    <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-2">Tags</p>
                    <div className="flex flex-wrap gap-1.5">
                      {selectedFile.matched_tags.map((tag) => (
                        <StatusBadge
                          key={tag}
                          label={`${tag} (${((selectedFile.top_confidence_score ?? 0) * 100).toFixed(0)}%)`}
                          severity="info"
                        />
                      ))}
                    </div>
                  </div>
                )}
              </div>
            </div>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}
