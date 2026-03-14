import { useState, useEffect } from "react";
import { useSearchParams } from "react-router-dom";
import { ErrorAlert } from "@/components/ErrorAlert";
import { MediaGrid } from "@/components/media/MediaGrid";
import { MediaPreviewModal } from "@/components/media/MediaPreviewModal";
import { getCanonical, getCanonicalTags } from "@/lib/api/endpoints";
import { useApi } from "@/hooks/useApi";
import type { CanonicalFile, Tag } from "@/types/media";
import type { PaginatedResponse } from "@/types/api";
import { Search, ArrowUpDown, X } from "lucide-react";

export default function Gallery() {
  const [searchParams, setSearchParams] = useSearchParams();
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
    const next = selectedTags.filter((t) => t !== tag);
    updateParams({ tags: next.length ? next.join(",") : undefined, page: "1" });
  };

  const { data: allTags } = useApi<Tag[]>(["canonical-tags"], getCanonicalTags);

  const { data, isLoading, error } = useApi<PaginatedResponse<CanonicalFile>>(
    ["canonical", String(page)],
    () => getCanonical({ page, page_size: 30 })
  );

  useEffect(() => {
    if (tagInput.length > 0 && allTags) {
      const filtered = allTags
        .map((t) => t.name)
        .filter((n) => n.toLowerCase().includes(tagInput.toLowerCase()) && !selectedTags.includes(n))
        .slice(0, 8);
      setSuggestions(filtered);
    } else {
      setSuggestions([]);
    }
  }, [tagInput, allTags, selectedTags]);

  return (
    <div className="p-6 space-y-6 max-w-7xl">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Gallery</h1>
        <p className="text-sm text-muted-foreground mt-1">Browse, filter, and inspect canonical media</p>
      </div>

      {error && <ErrorAlert message={error.message} />}

      {/* Tag Filter + Sort Controls */}
      <div className="flex flex-wrap items-center gap-2">
        <div className="relative">
          <input
            value={tagInput}
            onChange={(e) => setTagInput(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter" && tagInput) addTag(tagInput); }}
            placeholder="Filter by tag…"
            className="rounded-md border border-input bg-background px-3 py-2 text-sm pl-8 w-64"
          />
          <Search className="absolute left-2.5 top-2.5 h-3.5 w-3.5 text-muted-foreground" />
          {suggestions.length > 0 && (
            <div className="absolute top-full mt-1 w-full rounded-md border bg-card shadow-lg z-10 max-h-48 overflow-auto">
              {suggestions.map((s) => (
                <button key={s} onClick={() => addTag(s)} className="w-full text-left px-3 py-2 text-sm hover:bg-muted">{s}</button>
              ))}
            </div>
          )}
        </div>
        {selectedTags.map((tag) => (
          <span key={tag} className="inline-flex items-center gap-1 rounded-md bg-primary/10 text-primary px-2 py-1 text-xs font-medium">
            {tag}
            <button onClick={() => removeTag(tag)}><X className="h-3 w-3" /></button>
          </span>
        ))}
        <div className="ml-auto flex items-center gap-2">
          <select
            value={sortBy}
            onChange={(e) => updateParams({ sort: e.target.value })}
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

      <MediaGrid
        files={data?.items ?? []}
        loading={isLoading}
        emptyDescription={selectedTags.length ? "Try adjusting your tag filters" : undefined}
        onSelect={setSelectedFile}
      />

      {data && data.total_pages > 1 && (
        <div className="flex items-center justify-center gap-2">
          <button onClick={() => updateParams({ page: String(Math.max(1, page - 1)) })} disabled={page === 1} className="px-3 py-1 text-sm rounded border disabled:opacity-50">Prev</button>
          <span className="text-xs text-muted-foreground">Page {page} of {data.total_pages}</span>
          <button onClick={() => updateParams({ page: String(Math.min(data.total_pages, page + 1)) })} disabled={page === data.total_pages} className="px-3 py-1 text-sm rounded border disabled:opacity-50">Next</button>
        </div>
      )}

      <MediaPreviewModal file={selectedFile} onClose={() => setSelectedFile(null)} />
    </div>
  );
}
