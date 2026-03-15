import { useMemo, type ReactNode } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";
import { ErrorAlert } from "@/components/ErrorAlert";
import { EmptyState } from "@/components/EmptyState";
import { StatusBadge } from "@/components/StatusBadge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { getCanonicalDetail } from "@/lib/api/endpoints";
import { queryKeys } from "@/lib/api/queryKeys";
import type { CanonicalFile, CanonicalFileDetail, PaginatedResponse } from "@/types";
import { ArrowLeft, FileImage, FileVideo, FolderOpen, Hash, ImageIcon } from "lucide-react";

function getErrorMessage(err: unknown): string | null {
  if (!err) return null;
  if (err instanceof Error) return err.message;
  return String(err);
}

function findCachedCanonicalFile(
  fileId: string,
  queryClient: ReturnType<typeof useQueryClient>,
): CanonicalFile | null {
  const cachedPages = queryClient.getQueriesData<PaginatedResponse<CanonicalFile>>({
    queryKey: queryKeys.canonicalRoot,
  });

  for (const [, page] of cachedPages) {
    const match = page?.items.find((item) => item.id === fileId);
    if (match) return match;
  }

  return null;
}

export default function MediaDetailPage() {
  const { fileId = "" } = useParams();
  const queryClient = useQueryClient();
  const cachedFile = useMemo(() => findCachedCanonicalFile(fileId, queryClient), [fileId, queryClient]);

  const detailQuery = useQuery({
    queryKey: queryKeys.canonicalDetail(fileId),
    queryFn: async () => (await getCanonicalDetail(fileId)).data,
    enabled: !!fileId,
    staleTime: 30_000,
  });

  const detail = (detailQuery.data as CanonicalFileDetail | undefined) ?? null;
  const mergedFile = detail
    ? {
        id: detail.id,
        filename: detail.filename,
        file_type: detail.file_type,
        media_url: detail.media_url,
        matched_tags: cachedFile?.matched_tags ?? [],
        top_confidence_score: cachedFile?.top_confidence_score ?? null,
        sort_tag_name: cachedFile?.sort_tag_name ?? null,
      }
    : cachedFile;
  const error = getErrorMessage(detailQuery.error);
  const isVideo = mergedFile?.file_type === "video";

  if (!fileId) {
    return (
      <div className="mx-auto flex max-w-5xl flex-col gap-6 p-6">
        <ErrorAlert message="No media file id was provided." />
      </div>
    );
  }

  return (
    <div className="mx-auto flex max-w-6xl flex-col gap-6 p-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="space-y-3">
          <Button asChild type="button" variant="outline" size="sm">
            <Link to="/gallery">
              <ArrowLeft className="mr-2 h-4 w-4" />
              Back to gallery
            </Link>
          </Button>
          <div className="space-y-2">
            <div className="inline-flex items-center gap-2 rounded-full border border-border/80 bg-background/80 px-3 py-1 text-xs font-semibold uppercase tracking-[0.24em] text-muted-foreground">
              {isVideo ? <FileVideo className="h-3.5 w-3.5" /> : <FileImage className="h-3.5 w-3.5" />}
              Media detail
            </div>
            <h1 className="text-3xl font-semibold tracking-tight text-foreground">
              {mergedFile?.filename ?? "Media detail"}
            </h1>
            <p className="max-w-2xl text-sm leading-6 text-muted-foreground">
              Full-page inspection for a canonical media item using the current API-only runtime model.
            </p>
          </div>
        </div>
        {mergedFile ? (
          <div className="flex flex-wrap gap-2">
            <StatusBadge label={isVideo ? "Video" : "Image"} severity="info" />
            {mergedFile.sort_tag_name ? <StatusBadge label={mergedFile.sort_tag_name} severity="success" /> : null}
          </div>
        ) : null}
      </div>

      {error ? <ErrorAlert message={error} /> : null}

      {detailQuery.isLoading ? (
        <div className="grid gap-6 lg:grid-cols-[minmax(0,1.5fr)_24rem]">
          <Card className="min-h-[28rem] animate-pulse border-dashed" />
          <Card className="min-h-[28rem] animate-pulse border-dashed" />
        </div>
      ) : !detail || !mergedFile ? (
        <EmptyState
          icon={<ImageIcon className="h-10 w-10" />}
          title="Media item not found"
          description="This file id does not resolve to an active canonical media item."
          className="rounded-2xl border border-dashed bg-card/50"
        />
      ) : (
        <div className="grid gap-6 lg:grid-cols-[minmax(0,1.5fr)_24rem]">
          <Card className="overflow-hidden rounded-[28px] border-border/70 bg-[linear-gradient(180deg,hsl(var(--card))_0%,hsl(var(--secondary)/0.35)_100%)] shadow-sm">
            <CardContent className="p-4 sm:p-6">
              <div className="flex min-h-[26rem] items-center justify-center rounded-[24px] border border-border/70 bg-black/90 p-3">
                {detail.media_url ? (
                  isVideo ? (
                    <video src={detail.media_url} controls className="max-h-[72vh] w-full rounded-2xl object-contain" />
                  ) : (
                    <img src={detail.media_url} alt={detail.filename} className="max-h-[72vh] w-full rounded-2xl object-contain" />
                  )
                ) : (
                  <div className="flex h-[24rem] w-full items-center justify-center rounded-2xl border border-dashed border-border/70 bg-muted/40">
                    {isVideo ? <FileVideo className="h-16 w-16 text-muted-foreground" /> : <FileImage className="h-16 w-16 text-muted-foreground" />}
                  </div>
                )}
              </div>
            </CardContent>
          </Card>

          <div className="flex flex-col gap-4">
            <Card className="rounded-[28px] border-border/70 shadow-sm">
              <CardHeader>
                <CardTitle>File metadata</CardTitle>
                <CardDescription>
                  Canonical media details resolved against the supported operator-console APIs.
                </CardDescription>
              </CardHeader>
              <CardContent className="grid gap-3">
                <DetailRow icon={<Hash className="h-4 w-4" />} label="Media ID" value={detail.id} mono />
                <DetailRow icon={<FolderOpen className="h-4 w-4" />} label="Absolute path" value={detail.absolute_path} mono />
                <DetailRow label="File type" value={detail.file_type} />
                <DetailRow label="Primary tag" value={mergedFile.sort_tag_name ?? mergedFile.matched_tags[0] ?? "None"} />
                <DetailRow
                  label="Confidence"
                  value={
                    mergedFile.top_confidence_score == null
                      ? "Unknown"
                      : `${Math.round(mergedFile.top_confidence_score * 100)}%`
                  }
                />
              </CardContent>
            </Card>

            <Card className="rounded-[28px] border-border/70 shadow-sm">
              <CardHeader>
                <CardTitle>Matched tags</CardTitle>
                <CardDescription>
                  Tags come from cached canonical gallery data when this item was reached from the gallery flow.
                </CardDescription>
              </CardHeader>
              <CardContent>
                {mergedFile.matched_tags.length ? (
                  <div className="flex flex-wrap gap-2">
                    {mergedFile.matched_tags.map((tag) => (
                      <StatusBadge
                        key={tag}
                        label={tag}
                        severity={tag === mergedFile.sort_tag_name ? "success" : "neutral"}
                      />
                    ))}
                  </div>
                ) : (
                  <p className="text-sm text-muted-foreground">No tag metadata is currently cached for this item.</p>
                )}
              </CardContent>
            </Card>
          </div>
        </div>
      )}
    </div>
  );
}

function DetailRow({
  label,
  value,
  icon,
  mono = false,
}: {
  label: string;
  value: string;
  icon?: ReactNode;
  mono?: boolean;
}) {
  return (
    <div className="rounded-2xl border border-border/70 bg-muted/25 p-4">
      <div className="flex items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.2em] text-muted-foreground">
        {icon}
        <span>{label}</span>
      </div>
      <p className={`mt-2 text-sm text-foreground ${mono ? "break-all font-mono text-xs" : ""}`}>{value}</p>
    </div>
  );
}
