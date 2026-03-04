import { useEffect, useState, useCallback } from "react";
import { useSearchParams } from "react-router-dom";
import { ErrorAlert } from "@/components/ErrorAlert";
import { EmptyState } from "@/components/EmptyState";
import { StatusBadge } from "@/components/StatusBadge";
import { JsonViewer } from "@/components/JsonViewer";
import { getCanonical, getCanonicalTags } from "@/lib/api/endpoints";
import type { CanonicalFile, Tag, PaginatedResponse } from "@/types/api";
import { ImageIcon, Video, X, FileIcon, Search, ArrowUpDown } from "lucide-react";
import { Skeleton } from "@/components/ui/skeleton";
import { Dialog, DialogContent } from "@/components/ui/dialog";

export default function GalleryPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [data, setData] = useState<PaginatedResponse<CanonicalFile> | null>(null);
  const [allTags, setAllTags] = useState<Tag[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedFile, setSelectedFile] = useState<CanonicalFile | null>(null);
  const [tagInput, setTagInput] = useState("");
  const [suggestions, setSuggestions] = useState<string[]>([]);

  const selectedTags = searchParams.get("tags")?.split(",").filter(Boolean) || [];
  const sortBy = searchParams.get("sort") || "created_at";
  const sortOrder = searchParams.get("order") || "desc";
  const page = Number(searchParams.get("page") || 1);

  const updateParams = (updates: Record<string, string | undefined>) => {
    const newParams = new URLSearchParams(searchParams);
    Object.entries(updates).forEach(([k, v]) => v ? newParams.set(k, v) : newParams.delete(k));
    setSearchParams(newParams);
  };

  const addTag = (tag: string) => {
    if (!selectedTags.includes(tag)) {
      updateParams({ tags: [...selectedTags, tag].join(","), page: "1" });
    }
    setTagInput("");
    setSuggestions([]);
  };

  const removeTag = (tag: string) => {
    const next = selectedTags.filter(t => t !== tag);
    updateParams({ tags: next.length ? next.join(",") : undefined, page: "1" });
  };

  useEffect(() => {
    getCanonicalTags().then(e => setAllTags(e.data)).catch(() => {});
  }, []);

  useEffect(() => {
    if (tagInput.length > 0) {
      const filtered = allTags.map(t => t.name).filter(n => n.toLowerCase().includes(tagInput.toLowerCase()) && !selectedTags.includes(n)).slice(0, 8);
      setSuggestions(filtered);
    } else {
      setSuggestions([]);
    }
  }, [tagInput, allTags, selectedTags]);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await getCanonical({ page, page_size: 30 });
      setData(res.data);
    } catch (err: any) { setError(err.message); }
    finally { setLoading(false); }
  }, [page]);

  useEffect(() => { load(); }, [load]);

  const isVideo = (mime: string) => mime?.startsWith("video/");

  return (
    <div className="p-6 space-y-6 max-w-7xl">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Gallery</h1>
        <p className="text-sm text-muted-foreground mt-1">Browse, filter, and inspect canonical media</p>
      </div>

      {error && <ErrorAlert message={error} onDismiss={() => setError(null)} />}

      {/* Tag Filter + Sort Controls */}
      <div className="flex flex-wrap items-center gap-2">
        <div className="relative">
          <input
            value={tagInput}
            onChange={e => setTagInput(e.target.value)}
            onKeyDown={e => { if (e.key === "Enter" && tagInput) addTag(tagInput); }}
            placeholder="Filter by tag…"
            className="rounded-md border border-input bg-background px-3 py-2 text-sm pl-8 w-64"
          />
          <Search className="absolute left-2.5 top-2.5 h-3.5 w-3.5 text-muted-foreground" />
          {suggestions.length > 0 && (
            <div className="absolute top-full mt-1 w-full rounded-md border bg-card shadow-lg z-10 max-h-48 overflow-auto">
              {suggestions.map(s => (
                <button key={s} onClick={() => addTag(s)} className="w-full text-left px-3 py-2 text-sm hover:bg-muted">{s}</button>
              ))}
            </div>
          )}
        </div>
        {selectedTags.map(tag => (
          <span key={tag} className="inline-flex items-center gap-1 rounded-md bg-primary/10 text-primary px-2 py-1 text-xs font-medium">
            {tag}
            <button onClick={() => removeTag(tag)}><X className="h-3 w-3" /></button>
          </span>
        ))}
        <div className="ml-auto flex items-center gap-2">
          <select
            value={sortBy}
            onChange={e => updateParams({ sort: e.target.value })}
            className="rounded-md border border-input bg-background px-2 py-1.5 text-xs"
          >
            <option value="created_at">Created</option>
            <option value="tag">Tag</option>
            <option value="confidence">Confidence</option>
          </select>
          <button onClick={() => updateParams({ order: sortOrder === "asc" ? "desc" : "asc" })} className="p-1.5 rounded border border-input hover:bg-muted">
            <ArrowUpDown className="h-3.5 w-3.5" />
          </button>
        </div>
      </div>

      {/* Grid */}
      {loading ? (
        <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-3">
          {Array.from({ length: 18 }).map((_, i) => (
            <div key={i} className="rounded-lg border bg-card overflow-hidden">
              <Skeleton className="aspect-square w-full" />
              <div className="p-2 space-y-1"><Skeleton className="h-3 w-20" /><Skeleton className="h-3 w-12" /></div>
            </div>
          ))}
        </div>
      ) : !data?.items.length ? (
        <EmptyState icon={<ImageIcon className="h-10 w-10" />} title="No media found" description={selectedTags.length ? "Try adjusting your tag filters" : "Run an ingest to populate the gallery"} />
      ) : (
        <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-3">
          {data.items.map(file => (
            <button
              key={file.hash}
              onClick={() => setSelectedFile(file)}
              className="rounded-lg border bg-card overflow-hidden hover:border-primary/30 transition-colors group text-left"
            >
              <div className="aspect-square bg-muted flex items-center justify-center overflow-hidden relative">
                {file.thumbnail_url ? (
                  <img src={file.thumbnail_url} alt={file.path} className="w-full h-full object-cover group-hover:scale-105 transition-transform" />
                ) : isVideo(file.mime_type) ? (
                  <Video className="h-8 w-8 text-muted-foreground" />
                ) : (
                  <ImageIcon className="h-8 w-8 text-muted-foreground" />
                )}
                {isVideo(file.mime_type) && (
                  <span className="absolute top-2 right-2 bg-card/80 backdrop-blur rounded px-1.5 py-0.5 text-[10px] font-semibold">VIDEO</span>
                )}
              </div>
              <div className="p-2">
                <p className="text-xs font-mono truncate text-muted-foreground">{file.path.split("/").pop()}</p>
                {file.tags?.[0] && (
                  <StatusBadge label={`${file.tags[0].name} ${(file.tags[0].confidence * 100).toFixed(0)}%`} severity="info" className="mt-1" />
                )}
              </div>
            </button>
          ))}
        </div>
      )}

      {data && data.total_pages > 1 && (
        <div className="flex items-center justify-center gap-2">
          <button onClick={() => updateParams({ page: String(Math.max(1, page - 1)) })} disabled={page === 1} className="px-3 py-1 text-sm rounded border disabled:opacity-50">Prev</button>
          <span className="text-xs text-muted-foreground">Page {page} of {data.total_pages}</span>
          <button onClick={() => updateParams({ page: String(Math.min(data.total_pages, page + 1)) })} disabled={page === data.total_pages} className="px-3 py-1 text-sm rounded border disabled:opacity-50">Next</button>
        </div>
      )}

      {/* Detail Modal */}
      <Dialog open={!!selectedFile} onOpenChange={() => setSelectedFile(null)}>
        <DialogContent className="max-w-2xl max-h-[90vh] overflow-auto">
          {selectedFile && (
            <div className="space-y-4">
              <div className="aspect-video bg-muted rounded-lg flex items-center justify-center overflow-hidden">
                {selectedFile.thumbnail_url ? (
                  isVideo(selectedFile.mime_type) ? (
                    <video src={selectedFile.thumbnail_url} controls className="w-full h-full object-contain" />
                  ) : (
                    <img src={selectedFile.thumbnail_url} alt={selectedFile.path} className="w-full h-full object-contain" />
                  )
                ) : (
                  <FileIcon className="h-16 w-16 text-muted-foreground" />
                )}
              </div>
              <div className="space-y-3">
                <h3 className="font-semibold">{selectedFile.path.split("/").pop()}</h3>
                <div className="grid grid-cols-2 gap-2 text-sm">
                  <div><span className="text-muted-foreground">Path:</span><p className="font-mono text-xs mt-0.5 break-all">{selectedFile.path}</p></div>
                  <div><span className="text-muted-foreground">Hash:</span><p className="font-mono text-xs mt-0.5 break-all">{selectedFile.hash}</p></div>
                  <div><span className="text-muted-foreground">Type:</span><p className="text-xs mt-0.5">{selectedFile.mime_type}</p></div>
                  <div><span className="text-muted-foreground">Size:</span><p className="text-xs mt-0.5">{(selectedFile.size_bytes / 1024).toFixed(1)} KB</p></div>
                  <div><span className="text-muted-foreground">Created:</span><p className="text-xs mt-0.5">{new Date(selectedFile.created_at).toLocaleString()}</p></div>
                </div>
                {selectedFile.tags && selectedFile.tags.length > 0 && (
                  <div>
                    <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-2">Tags</p>
                    <div className="flex flex-wrap gap-1.5">
                      {selectedFile.tags.map(tag => (
                        <StatusBadge key={tag.name} label={`${tag.name} (${(tag.confidence * 100).toFixed(0)}%)`} severity="info" />
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
