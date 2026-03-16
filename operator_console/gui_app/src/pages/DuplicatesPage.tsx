import { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { ErrorAlert } from "@/components/ErrorAlert";
import { EmptyState } from "@/components/EmptyState";
import { TopSurfaceHeader } from "@/components/layout/TopSurfaceHeader";
import { MetricCard } from "@/components/MetricCard";
import { StatusBadge } from "@/components/StatusBadge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { getDuplicates } from "@/lib/api/endpoints";
import { queryKeys } from "@/lib/api/queryKeys";
import { queryOptions } from "@/lib/api/queryOptions";
import { cn } from "@/lib/utils";
import type { DuplicateGroup } from "@/types";
import {
  AlertCircle,
  CheckCircle2,
  ChevronDown,
  Copy,
  FileIcon,
  FolderTree,
  HelpCircle,
  ImageIcon,
  Layers3,
  Sparkles,
  Video,
} from "lucide-react";
import { Skeleton } from "@/components/ui/skeleton";

function getErrorMessage(err: unknown): string | null {
  if (!err) return null;
  if (err instanceof Error) return err.message;
  return String(err);
}

type ReviewMark = "looks-right" | "needs-review" | "unsure";
type ReviewFilter = "all" | "unreviewed" | ReviewMark;

const reviewOptions: Array<{ value: ReviewFilter; label: string }> = [
  { value: "all", label: "All groups" },
  { value: "unreviewed", label: "Still to review" },
  { value: "looks-right", label: "Looks right" },
  { value: "needs-review", label: "Needs review" },
  { value: "unsure", label: "Not sure" },
];

function basename(path: string): string {
  const segments = path.split(/[\\/]/).filter(Boolean);
  return segments.at(-1) ?? path;
}

function truncateMiddle(value: string, maxLength = 72): string {
  if (value.length <= maxLength) return value;
  const keep = Math.floor((maxLength - 3) / 2);
  return `${value.slice(0, keep)}...${value.slice(-keep)}`;
}

function getReviewBadge(mark?: ReviewMark) {
  switch (mark) {
    case "looks-right":
      return { label: "Looks right", severity: "success" as const, icon: CheckCircle2 };
    case "needs-review":
      return { label: "Needs review", severity: "destructive" as const, icon: AlertCircle };
    case "unsure":
      return { label: "Not sure", severity: "caution" as const, icon: HelpCircle };
    default:
      return null;
  }
}

function ReviewActionButton({
  label,
  icon: Icon,
  active,
  onClick,
}: {
  label: string;
  icon: typeof CheckCircle2;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <Button
      type="button"
      variant={active ? "default" : "outline"}
      size="sm"
      onClick={onClick}
      className="justify-start rounded-full px-4"
    >
      <Icon className="h-4 w-4" />
      {label}
    </Button>
  );
}

function DuplicatePreview({
  src,
  alt,
  isImage,
  mediaType,
  className,
}: {
  src?: string | null;
  alt: string;
  isImage: boolean;
  mediaType: string;
  className?: string;
}) {
  const [imageSrc, setImageSrc] = useState(src ?? null);

  useEffect(() => {
    setImageSrc(src ?? null);
  }, [src]);

  return (
    <div
      className={cn(
        "relative overflow-hidden rounded-[24px] border border-border/70 bg-[linear-gradient(135deg,hsl(var(--muted))_0%,hsl(var(--secondary)/0.4)_100%)]",
        className,
      )}
    >
      {imageSrc ? (
        <img
          src={imageSrc}
          alt={alt}
          className="h-full w-full object-cover"
          onError={() => setImageSrc(null)}
        />
      ) : (
        <div className="flex h-full min-h-40 items-center justify-center">
          {isImage ? (
            <ImageIcon className="h-10 w-10 text-muted-foreground" />
          ) : mediaType.toLowerCase() === "video" ? (
            <Video className="h-10 w-10 text-muted-foreground" />
          ) : (
            <FileIcon className="h-10 w-10 text-muted-foreground" />
          )}
        </div>
      )}
      <div className="absolute left-3 top-3">
        <StatusBadge
          label={isImage ? "Image" : mediaType.toLowerCase() === "video" ? "Video" : "File"}
          severity="neutral"
          className="border-white/30 bg-background/85 text-foreground"
        />
      </div>
    </div>
  );
}

function QueuePreviewStrip({ group }: { group: DuplicateGroup }) {
  const previewFiles = group.duplicates.filter((file) => file.thumbnail_url).slice(0, 3);

  if (!previewFiles.length) {
    return (
      <div className="flex h-12 w-20 items-center justify-center rounded-2xl border border-dashed border-border/80 bg-muted/30">
        <Copy className="h-4 w-4 text-muted-foreground" />
      </div>
    );
  }

  return (
    <div className="flex items-center">
      {previewFiles.map((file, index) => (
        <div
          key={file.file_instance_id || `${file.path}-${index}`}
          className={cn(
            "h-12 w-12 overflow-hidden rounded-2xl border border-background bg-muted shadow-sm",
            index > 0 && "-ml-3",
          )}
        >
          <img src={file.thumbnail_url ?? ""} alt={basename(file.path)} className="h-full w-full object-cover" />
        </div>
      ))}
    </div>
  );
}

function DuplicateFileCard({
  title,
  subtitle,
  badge,
  file,
  emphasis = "default",
}: {
  title: string;
  subtitle: string;
  badge: string;
  file: DuplicateGroup["duplicates"][number];
  emphasis?: "default" | "success";
}) {
  return (
    <Card
      className={cn(
        "overflow-hidden rounded-[28px] border-border/70 bg-background/90 shadow-sm",
        emphasis === "success" && "border-success/35 bg-success/5",
      )}
    >
      <CardContent className="space-y-4 p-4">
        <DuplicatePreview
          src={file.thumbnail_url}
          alt={basename(file.path)}
          isImage={file.is_image}
          mediaType={file.media_type}
          className="aspect-[4/3]"
        />
        <div className="space-y-2">
          <StatusBadge label={badge} severity={emphasis === "success" ? "success" : "info"} />
          <div>
            <p className="text-base font-semibold text-foreground">{title}</p>
            <p className="mt-1 text-sm text-muted-foreground">{subtitle}</p>
          </div>
          <p className="break-all text-sm text-muted-foreground">{file.path}</p>
        </div>
      </CardContent>
    </Card>
  );
}

export default function DuplicatesPage() {
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [reviewFilter, setReviewFilter] = useState<ReviewFilter>("unreviewed");
  const [reviewMarks, setReviewMarks] = useState<Record<string, ReviewMark>>({});

  const duplicatesQuery = useQuery({
    queryKey: queryKeys.duplicates,
    queryFn: async () => (await getDuplicates()).data,
    staleTime: queryOptions.duplicates.staleTime,
  });

  const groups = (duplicatesQuery.data as DuplicateGroup[] | undefined) ?? [];
  const sortedGroups = useMemo(
    () =>
      [...groups].sort((left, right) => {
        const leftImages = left.duplicates.filter((file) => file.is_image).length;
        const rightImages = right.duplicates.filter((file) => file.is_image).length;
        if (rightImages !== leftImages) return rightImages - leftImages;
        if (right.duplicates.length !== left.duplicates.length) {
          return right.duplicates.length - left.duplicates.length;
        }
        return left.canonical_path.localeCompare(right.canonical_path);
      }),
    [groups],
  );
  const filteredGroups = useMemo(
    () =>
      sortedGroups.filter((group) => {
        if (reviewFilter === "all") return true;
        const mark = reviewMarks[group.group_id];
        if (reviewFilter === "unreviewed") return !mark;
        return mark === reviewFilter;
      }),
    [reviewFilter, reviewMarks, sortedGroups],
  );

  useEffect(() => {
    if (!filteredGroups.length) {
      setSelectedId(null);
      return;
    }
    if (!selectedId || !filteredGroups.some((group) => group.group_id === selectedId)) {
      setSelectedId(filteredGroups[0].group_id);
    }
  }, [filteredGroups, selectedId]);

  const selected = filteredGroups.find((group) => group.group_id === selectedId) ?? null;
  const totalFiles = groups.reduce((sum, group) => sum + group.duplicates.length, 0);
  const duplicateFiles = groups.reduce(
    (sum, group) => sum + group.duplicates.filter((file) => !file.is_canonical).length,
    0,
  );
  const imageGroups = groups.filter((group) => group.duplicates.some((file) => file.is_image)).length;
  const markedNeedsReview = Object.values(reviewMarks).filter((mark) => mark === "needs-review").length;
  const selectedCanonical = selected?.duplicates.find((file) => file.is_canonical) ?? null;
  const selectedDuplicates = selected?.duplicates.filter((file) => !file.is_canonical) ?? [];
  const selectedReviewBadge = selected ? getReviewBadge(reviewMarks[selected.group_id]) : null;

  function setReviewMark(groupId: string, nextMark: ReviewMark) {
    setReviewMarks((current) => {
      if (current[groupId] === nextMark) {
        const { [groupId]: _removed, ...rest } = current;
        return rest;
      }
      return { ...current, [groupId]: nextMark };
    });
  }

  return (
    <div className="mx-auto flex max-w-7xl flex-col gap-6 p-6">
      <TopSurfaceHeader
        badge="Duplicate Review"
        title="Review possible duplicates clearly before deciding what needs attention."
        description="Use this page to compare matching files side by side. The system marks one file as the current main version, and you can quickly note whether each group looks correct or needs a closer review."
        icon={Copy}
      >
        <div className="grid gap-3 lg:grid-cols-[minmax(0,1fr)_18rem]">
          <div className="rounded-[28px] border border-border/70 bg-background/85 p-5 shadow-sm">
            <p className="text-sm font-semibold text-foreground">When to use this</p>
            <p className="mt-2 text-sm leading-6 text-muted-foreground">
              Start here when you want to answer simple questions: &ldquo;Are these really the same file?&rdquo;,
              &ldquo;Which copy is the main one?&rdquo;, and &ldquo;Which groups need another look?&rdquo;
            </p>
          </div>
          <div className="rounded-[28px] border border-border/70 bg-background/85 p-5 shadow-sm">
            <p className="text-sm font-semibold text-foreground">What “main version” means</p>
            <p className="mt-2 text-sm leading-6 text-muted-foreground">
              The app picks one file as the main version for the group. Everything else shown beside it is a
              possible duplicate of that file.
            </p>
          </div>
        </div>
      </TopSurfaceHeader>
      {duplicatesQuery.error && (
        <ErrorAlert message={getErrorMessage(duplicatesQuery.error) || "Failed to load duplicate groups"} />
      )}

      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
        <MetricCard title="Groups To Review" value={groups.length} subtitle="Possible duplicate sets" icon={<Layers3 className="h-4 w-4" />} loading={duplicatesQuery.isLoading} />
        <MetricCard title="Files To Compare" value={totalFiles} subtitle="Main files plus matching copies" icon={<FolderTree className="h-4 w-4" />} loading={duplicatesQuery.isLoading} />
        <MetricCard title="Extra Copies" value={duplicateFiles} subtitle="Files that are not the main version" icon={<Copy className="h-4 w-4" />} loading={duplicatesQuery.isLoading} />
        <MetricCard title="Need Another Look" value={markedNeedsReview} subtitle={`${imageGroups} groups include image previews`} icon={<Sparkles className="h-4 w-4" />} loading={duplicatesQuery.isLoading} />
      </div>

      {duplicatesQuery.isLoading ? (
        <div className="grid gap-4 xl:grid-cols-[22rem_minmax(0,1fr)]">
          <div className="space-y-2">
            {Array.from({ length: 8 }).map((_, i) => (
              <Skeleton key={i} className="h-14 w-full rounded-lg" />
            ))}
          </div>
          <div>
            <Skeleton className="h-[44rem] rounded-[28px]" />
          </div>
        </div>
      ) : !groups.length ? (
        <EmptyState
          icon={<Copy className="h-10 w-10" />}
          title="No duplicate groups to review"
          description="Once the library finds matching files, they will appear here for side-by-side review."
        />
      ) : (
        <div className="grid gap-4 xl:grid-cols-[22rem_minmax(0,1fr)]">
          <Card className="overflow-hidden rounded-[30px] border-border/70 bg-card/95 shadow-sm">
            <CardHeader className="space-y-4 pb-4">
              <div>
                <CardDescription>Review Queue</CardDescription>
                <CardTitle className="text-2xl">Possible duplicate groups</CardTitle>
              </div>
              <p className="text-sm leading-6 text-muted-foreground">
                Pick a group to compare the main version with the matching copies. Start with groups that still
                need review.
              </p>
              <div className="flex flex-wrap gap-2">
                {reviewOptions.map((option) => (
                  <Button
                    key={option.value}
                    type="button"
                    variant={reviewFilter === option.value ? "default" : "outline"}
                    size="sm"
                    className="rounded-full"
                    onClick={() => setReviewFilter(option.value)}
                  >
                    {option.label}
                  </Button>
                ))}
              </div>
            </CardHeader>
            <CardContent className="space-y-3 overflow-auto scrollbar-thin px-3 pb-4 pt-0">
              {filteredGroups.map((group) => {
                const reviewBadge = getReviewBadge(reviewMarks[group.group_id]);
                const groupDuplicates = group.duplicates.filter((file) => !file.is_canonical).length;
                return (
                  <button
                    key={group.group_id}
                    type="button"
                    onClick={() => setSelectedId(group.group_id)}
                    className={cn(
                      "w-full rounded-[24px] border p-3 text-left transition-all",
                      selectedId === group.group_id
                        ? "border-primary/35 bg-primary/10 shadow-sm"
                        : "border-border/70 bg-background/80 hover:border-primary/20 hover:bg-muted/40",
                    )}
                  >
                    <div className="flex items-start gap-3">
                      <QueuePreviewStrip group={group} />
                      <div className="min-w-0 flex-1 space-y-2">
                        <div className="flex flex-wrap items-center gap-2">
                          <p className="truncate text-sm font-semibold text-foreground">
                            {basename(group.canonical_path)}
                          </p>
                          <StatusBadge label={`${group.duplicates.length} files`} severity="neutral" />
                          {reviewBadge ? (
                            <StatusBadge label={reviewBadge.label} severity={reviewBadge.severity} />
                          ) : (
                            <StatusBadge label="Still to review" severity="caution" />
                          )}
                        </div>
                        <p className="text-sm text-muted-foreground">
                          {groupDuplicates === 1
                            ? "1 matching copy beside the main version"
                            : `${groupDuplicates} matching copies beside the main version`}
                        </p>
                        <p className="truncate text-xs text-muted-foreground">
                          {truncateMiddle(group.canonical_path)}
                        </p>
                      </div>
                    </div>
                  </button>
                );
              })}
              {!filteredGroups.length ? (
                <EmptyState
                  title="No groups match this filter"
                  description="Change the filter to keep reviewing the remaining duplicate groups."
                />
              ) : null}
            </CardContent>
          </Card>

          <Card className="overflow-hidden rounded-[30px] border-border/70 bg-card/95 shadow-sm">
            <CardHeader className="space-y-4 pb-4">
              <div>
                <CardDescription>Compare Files</CardDescription>
                <CardTitle className="text-2xl">
                  {selected ? basename(selected.canonical_path) : "Select a duplicate group"}
                </CardTitle>
              </div>
              {selected ? (
                <div className="grid gap-3 xl:grid-cols-[minmax(0,1fr)_18rem]">
                  <div className="rounded-[24px] border border-border/70 bg-background/80 p-4">
                    <p className="text-sm font-semibold text-foreground">What you are looking at</p>
                    <p className="mt-2 text-sm leading-6 text-muted-foreground">
                      The card marked <span className="font-medium text-foreground">Main version</span> is the
                      file the system currently keeps as the primary copy. Compare it with the matching files
                      below and note whether this grouping looks correct.
                    </p>
                  </div>
                  <div className="rounded-[24px] border border-border/70 bg-background/80 p-4">
                    <p className="text-sm font-semibold text-foreground">Quick note</p>
                    <div className="mt-3 flex flex-wrap gap-2">
                      <ReviewActionButton
                        label="Looks right"
                        icon={CheckCircle2}
                        active={reviewMarks[selected.group_id] === "looks-right"}
                        onClick={() => setReviewMark(selected.group_id, "looks-right")}
                      />
                      <ReviewActionButton
                        label="Needs review"
                        icon={AlertCircle}
                        active={reviewMarks[selected.group_id] === "needs-review"}
                        onClick={() => setReviewMark(selected.group_id, "needs-review")}
                      />
                      <ReviewActionButton
                        label="Not sure"
                        icon={HelpCircle}
                        active={reviewMarks[selected.group_id] === "unsure"}
                        onClick={() => setReviewMark(selected.group_id, "unsure")}
                      />
                    </div>
                  </div>
                </div>
              ) : null}
            </CardHeader>
            <CardContent>
              {selected && selectedCanonical ? (
                <div className="space-y-6">
                  <div className="grid gap-4 xl:grid-cols-[minmax(0,1.2fr)_minmax(0,1fr)]">
                    <DuplicateFileCard
                      title={basename(selectedCanonical.path)}
                      subtitle="This is the file currently treated as the main version for this group."
                      badge="Main version"
                      file={selectedCanonical}
                      emphasis="success"
                    />
                    <Card className="rounded-[28px] border-border/70 bg-background/85 shadow-sm">
                      <CardContent className="space-y-4 p-5">
                        <div>
                          <p className="text-sm font-semibold text-foreground">At a glance</p>
                          <p className="mt-2 text-sm leading-6 text-muted-foreground">
                            This group contains {selected.duplicates.length} files in total, including{" "}
                            {selectedDuplicates.length === 1
                              ? "1 matching copy"
                              : `${selectedDuplicates.length} matching copies`}
                            . Use the previews first. Open technical details only if you need the exact paths or
                            group ID.
                          </p>
                        </div>
                        <div className="flex flex-wrap gap-2">
                          <StatusBadge label={`${selected.duplicates.length} files in group`} severity="neutral" />
                          <StatusBadge
                            label={
                              selectedDuplicates.length === 1
                                ? "1 extra copy"
                                : `${selectedDuplicates.length} extra copies`
                            }
                            severity="info"
                          />
                          {selectedReviewBadge ? (
                            <StatusBadge
                              label={selectedReviewBadge.label}
                              severity={selectedReviewBadge.severity}
                            />
                          ) : (
                            <StatusBadge label="Still to review" severity="caution" />
                          )}
                        </div>
                        <div className="rounded-2xl border border-dashed border-border/70 bg-muted/25 p-4">
                          <p className="text-xs font-semibold uppercase tracking-[0.22em] text-muted-foreground">
                            Main version path
                          </p>
                          <p className="mt-2 break-all text-sm text-foreground">{selectedCanonical.path}</p>
                        </div>
                      </CardContent>
                    </Card>
                  </div>

                  <section className="space-y-4">
                    <div>
                      <h2 className="text-lg font-semibold tracking-tight text-foreground">Matching files</h2>
                      <p className="mt-1 text-sm text-muted-foreground">
                        Compare these files with the main version above. Focus on the previews first; the full
                        path is here when you need to identify a specific file.
                      </p>
                    </div>
                    {selectedDuplicates.length ? (
                      <div className="grid gap-4 lg:grid-cols-2">
                        {selectedDuplicates.map((file) => (
                          <DuplicateFileCard
                            key={file.file_instance_id || file.path}
                            title={basename(file.path)}
                            subtitle="Possible duplicate of the main version."
                            badge="Matching file"
                            file={file}
                          />
                        ))}
                      </div>
                    ) : (
                      <EmptyState
                        title="No extra copies in this group"
                        description="This group only contains the current main version."
                      />
                    )}
                  </section>

                  <Collapsible className="rounded-[24px] border border-border/70 bg-background/85">
                    <CollapsibleTrigger asChild>
                      <button
                        type="button"
                        className="flex w-full items-center justify-between gap-3 px-5 py-4 text-left"
                      >
                        <div>
                          <p className="text-sm font-semibold text-foreground">Technical details</p>
                          <p className="mt-1 text-sm text-muted-foreground">
                            Group ID, full paths, and low-level reference data for deeper investigation.
                          </p>
                        </div>
                        <ChevronDown className="h-4 w-4 text-muted-foreground" />
                      </button>
                    </CollapsibleTrigger>
                    <CollapsibleContent className="space-y-4 border-t px-5 py-4">
                      <div className="space-y-2">
                        <p className="text-xs font-semibold uppercase tracking-[0.22em] text-muted-foreground">
                          Group ID
                        </p>
                        <p className="break-all font-mono text-xs text-foreground">{selected.group_id}</p>
                      </div>
                      <div className="space-y-2">
                        <p className="text-xs font-semibold uppercase tracking-[0.22em] text-muted-foreground">
                          Main version path
                        </p>
                        <p className="break-all font-mono text-xs text-foreground">{selected.canonical_path}</p>
                      </div>
                      <div className="space-y-2">
                        <p className="text-xs font-semibold uppercase tracking-[0.22em] text-muted-foreground">
                          Group members
                        </p>
                        <div className="space-y-2">
                          {selected.duplicates.map((file) => (
                            <div
                              key={file.file_instance_id || file.path}
                              className="rounded-2xl border border-border/70 bg-muted/20 p-3"
                            >
                              <div className="flex flex-wrap items-center gap-2">
                                <StatusBadge
                                  label={file.is_canonical ? "Main version" : "Matching file"}
                                  severity={file.is_canonical ? "success" : "neutral"}
                                />
                                <StatusBadge label={file.file_instance_id || "No file ID"} severity="neutral" />
                              </div>
                              <p className="mt-2 break-all font-mono text-xs text-foreground">{file.path}</p>
                            </div>
                          ))}
                        </div>
                      </div>
                    </CollapsibleContent>
                  </Collapsible>
                </div>
              ) : (
                <EmptyState
                  title="Select a group to compare"
                  description="Choose a duplicate group from the review queue to see the main version and matching files side by side."
                />
              )}
            </CardContent>
          </Card>
        </div>
      )}
    </div>
  );
}
