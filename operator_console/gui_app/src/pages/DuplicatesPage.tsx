import { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { ChevronDown, Copy } from "lucide-react";

import { ErrorAlert } from "@/components/ErrorAlert";
import { EmptyState } from "@/components/EmptyState";
import { StatusBadge } from "@/components/StatusBadge";
import { DuplicateFocusCard } from "@/components/duplicates/DuplicateFocusCard";
import { DuplicateKeyboardShortcutsHint } from "@/components/duplicates/DuplicateKeyboardShortcutsHint";
import { DuplicateMediaPreview } from "@/components/duplicates/DuplicateMediaPreview";
import { DuplicateQueueItem } from "@/components/duplicates/DuplicateQueueItem";
import { DuplicateReviewActionBar } from "@/components/duplicates/DuplicateReviewActionBar";
import { DuplicateReviewProgress } from "@/components/duplicates/DuplicateReviewProgress";
import { TopSurfaceHeader } from "@/components/layout/TopSurfaceHeader";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Skeleton } from "@/components/ui/skeleton";
import { getDuplicates } from "@/lib/api/endpoints";
import { queryKeys } from "@/lib/api/queryKeys";
import { queryOptions } from "@/lib/api/queryOptions";
import { cn } from "@/lib/utils";
import type { DuplicateFile, DuplicateGroup } from "@/types";

type ReviewMark = "looks-right" | "needs-review" | "unsure";
type ReviewFilter = "all" | "unreviewed" | ReviewMark;

const reviewOptions: Array<{ value: ReviewFilter; label: string }> = [
  { value: "all", label: "All" },
  { value: "unreviewed", label: "Still to review" },
  { value: "looks-right", label: "Looks right" },
  { value: "needs-review", label: "Needs review" },
  { value: "unsure", label: "Not sure" },
];

function getErrorMessage(err: unknown): string | null {
  if (!err) return null;
  if (err instanceof Error) return err.message;
  return String(err);
}

function basename(path: string): string {
  const segments = path.split(/[\\/]/).filter(Boolean);
  return segments.at(-1) ?? path;
}

function getReviewPresentation(mark?: ReviewMark) {
  switch (mark) {
    case "looks-right":
      return { label: "Looks right", severity: "success" as const };
    case "needs-review":
      return { label: "Needs review", severity: "destructive" as const };
    case "unsure":
      return { label: "Not sure", severity: "caution" as const };
    default:
      return { label: "Still to review", severity: "caution" as const };
  }
}

function isEditableTarget(target: EventTarget | null) {
  if (!(target instanceof HTMLElement)) return false;
  return (
    target instanceof HTMLInputElement ||
    target instanceof HTMLTextAreaElement ||
    target instanceof HTMLSelectElement ||
    target.isContentEditable
  );
}

function findNextGroupIdAfterReview({
  currentId,
  groups,
  nextMarks,
}: {
  currentId: string;
  groups: DuplicateGroup[];
  nextMarks: Record<string, ReviewMark>;
}) {
  const currentIndex = groups.findIndex((group) => group.group_id === currentId);
  if (currentIndex === -1) return null;

  for (let index = currentIndex + 1; index < groups.length; index += 1) {
    const candidate = groups[index];
    if (!nextMarks[candidate.group_id]) return candidate.group_id;
  }
  for (let index = 0; index < currentIndex; index += 1) {
    const candidate = groups[index];
    if (!nextMarks[candidate.group_id]) return candidate.group_id;
  }
  for (let index = currentIndex + 1; index < groups.length; index += 1) {
    return groups[index].group_id;
  }
  for (let index = 0; index < currentIndex; index += 1) {
    return groups[index].group_id;
  }
  return currentId;
}

export default function DuplicatesPage() {
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [selectedDuplicateId, setSelectedDuplicateId] = useState<string | null>(null);
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
  const selectedIndex = selected ? filteredGroups.findIndex((group) => group.group_id === selected.group_id) : -1;
  const selectedOverallIndex = selected ? sortedGroups.findIndex((group) => group.group_id === selected.group_id) : -1;
  const reviewedCount = Object.keys(reviewMarks).length;
  const selectedCanonical = selected?.duplicates.find((file) => file.is_canonical) ?? null;
  const selectedDuplicates = useMemo(
    () => selected?.duplicates.filter((file) => !file.is_canonical) ?? [],
    [selected],
  );

  useEffect(() => {
    if (!selectedDuplicates.length) {
      setSelectedDuplicateId(null);
      return;
    }
    if (!selectedDuplicateId || !selectedDuplicates.some((file) => file.file_instance_id === selectedDuplicateId)) {
      setSelectedDuplicateId(selectedDuplicates[0].file_instance_id);
    }
  }, [selectedDuplicateId, selectedDuplicates]);

  const selectedDuplicate =
    selectedDuplicates.find((file) => file.file_instance_id === selectedDuplicateId) ?? selectedDuplicates[0] ?? null;
  const selectedReview = selected ? getReviewPresentation(reviewMarks[selected.group_id]) : null;

  function moveSelection(direction: -1 | 1) {
    if (!filteredGroups.length || selectedIndex < 0) return;
    const nextIndex = selectedIndex + direction;
    if (nextIndex < 0 || nextIndex >= filteredGroups.length) return;
    setSelectedId(filteredGroups[nextIndex].group_id);
  }

  function applyReviewMark(mark: ReviewMark) {
    if (!selected) return;

    const currentMark = reviewMarks[selected.group_id];
    let nextSelectedId: string | null = selected.group_id;

    setReviewMarks((current) => {
      if (current[selected.group_id] === mark) {
        const { [selected.group_id]: _removed, ...rest } = current;
        return rest;
      }

      const next = { ...current, [selected.group_id]: mark };
      nextSelectedId = findNextGroupIdAfterReview({
        currentId: selected.group_id,
        groups: sortedGroups,
        nextMarks: next,
      });
      return next;
    });

    if (currentMark !== mark && nextSelectedId && nextSelectedId !== selected.group_id) {
      setSelectedId(nextSelectedId);
    }
  }

  useEffect(() => {
    function handleKeyDown(event: KeyboardEvent) {
      if (isEditableTarget(event.target)) return;
      if (!selected) return;

      switch (event.key) {
        case "ArrowLeft":
          event.preventDefault();
          moveSelection(-1);
          break;
        case "ArrowRight":
          event.preventDefault();
          moveSelection(1);
          break;
        case "1":
          event.preventDefault();
          applyReviewMark("looks-right");
          break;
        case "2":
          event.preventDefault();
          applyReviewMark("needs-review");
          break;
        case "3":
          event.preventDefault();
          applyReviewMark("unsure");
          break;
        default:
          break;
      }
    }

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [selected, selectedIndex, filteredGroups, reviewMarks, sortedGroups]);

  return (
    <div className="mx-auto flex max-w-7xl flex-col gap-6 p-6">
      <TopSurfaceHeader
        badge="Duplicate Review"
        title="Review duplicate groups quickly without losing your place."
        description="This workspace is optimized for long queues: keep the queue visible, compare previews first, and leave full path details collapsed until you need them."
        icon={Copy}
      >
        <div className="grid gap-3 lg:grid-cols-[minmax(0,1fr)_20rem]">
          <div className="rounded-[28px] border border-border/70 bg-background/85 p-5 shadow-sm">
            <p className="text-sm font-semibold text-foreground">Throughput-first workflow</p>
            <p className="mt-2 text-sm leading-6 text-muted-foreground">
              Mark a group, auto-advance, and come back only when something needs a closer look. The queue keeps reviewed and flagged states visible so you can maintain momentum across hundreds of groups.
            </p>
          </div>
          <DuplicateKeyboardShortcutsHint />
        </div>
      </TopSurfaceHeader>

      {duplicatesQuery.error && (
        <ErrorAlert message={getErrorMessage(duplicatesQuery.error) || "Failed to load duplicate groups"} />
      )}

      {duplicatesQuery.isLoading ? (
        <div className="space-y-4">
          <Skeleton className="h-36 rounded-[28px]" />
          <div className="grid gap-4 xl:grid-cols-[20rem_minmax(0,1fr)]">
            <Skeleton className="h-[42rem] rounded-[28px]" />
            <Skeleton className="h-[42rem] rounded-[28px]" />
          </div>
        </div>
      ) : !groups.length ? (
        <EmptyState
          icon={<Copy className="h-10 w-10" />}
          title="No duplicate groups to review"
          description="Once the library finds matching files, they will appear here for side-by-side review."
        />
      ) : (
        <>
          <DuplicateReviewProgress
            currentIndex={selectedOverallIndex < 0 ? 0 : selectedOverallIndex}
            total={sortedGroups.length}
            reviewedCount={reviewedCount}
          />

          <div className="grid gap-4 xl:grid-cols-[20rem_minmax(0,1fr)]">
            <Card className="overflow-hidden rounded-[30px] border-border/70 bg-card/95 shadow-sm">
              <CardHeader className="space-y-4 pb-4">
                <div>
                  <CardDescription>Review Queue</CardDescription>
                  <CardTitle className="text-2xl">Keep your place</CardTitle>
                </div>
                <p className="text-sm leading-6 text-muted-foreground">
                  Use the queue to triage groups quickly. Review states stay visible, so you can move fast without re-reading every path.
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
              <CardContent className="px-3 pb-4 pt-0">
                <ScrollArea className="h-[42rem] pr-3">
                  <div className="space-y-3">
                    {filteredGroups.map((group) => {
                      const review = getReviewPresentation(reviewMarks[group.group_id]);
                      return (
                        <DuplicateQueueItem
                          key={group.group_id}
                          active={selected?.group_id === group.group_id}
                          group={group}
                          markLabel={review.label}
                          markSeverity={review.severity}
                          onSelect={() => setSelectedId(group.group_id)}
                        />
                      );
                    })}
                    {!filteredGroups.length ? (
                      <EmptyState
                        title="No groups match this filter"
                        description="Switch the filter to keep reviewing the remaining duplicate groups."
                      />
                    ) : null}
                  </div>
                </ScrollArea>
              </CardContent>
            </Card>

            <div className="space-y-4">
              <Card className="overflow-hidden rounded-[30px] border-border/70 bg-card/95 shadow-sm">
                <CardHeader className="space-y-4 pb-4">
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div>
                      <CardDescription>Focused Comparison</CardDescription>
                      <CardTitle className="text-2xl">
                        {selected ? basename(selected.canonical_path) : "Select a duplicate group"}
                      </CardTitle>
                    </div>
                    {selectedReview ? <StatusBadge label={selectedReview.label} severity={selectedReview.severity} /> : null}
                  </div>
                  {selected ? (
                    <div className="rounded-[24px] border border-border/70 bg-background/80 p-4">
                      <p className="text-sm font-semibold text-foreground">How to review efficiently</p>
                      <p className="mt-2 text-sm leading-6 text-muted-foreground">
                        Compare the main version with one matching file at a time, rely on previews first, and only open technical details if you need exact file paths or IDs.
                      </p>
                    </div>
                  ) : null}
                </CardHeader>
                <CardContent>
                  {selected && selectedCanonical ? (
                    <div className="space-y-6">
                      <div className="grid gap-4 xl:grid-cols-2">
                        <DuplicateFocusCard
                          badge="Main version"
                          description="This is the file currently treated as the primary copy for this group."
                          emphasis="success"
                          file={selectedCanonical}
                        />
                        {selectedDuplicate ? (
                          <DuplicateFocusCard
                            badge="Selected match"
                            description="Use this focused comparison to decide whether the group looks correct or needs another review pass."
                            emphasis="info"
                            file={selectedDuplicate}
                          />
                        ) : (
                          <Card className="rounded-[28px] border-border/70 bg-background/85 shadow-sm">
                            <CardContent className="flex h-full min-h-[20rem] flex-col items-center justify-center gap-3 p-6 text-center">
                              <StatusBadge label="No extra copies" severity="neutral" />
                              <p className="text-base font-semibold text-foreground">This group has no additional duplicates</p>
                              <p className="max-w-md text-sm text-muted-foreground">
                                There is nothing else to compare for this group, so you can review the main version and move on.
                              </p>
                            </CardContent>
                          </Card>
                        )}
                      </div>

                      {selectedDuplicates.length ? (
                        <section className="space-y-3">
                          <div className="flex items-center justify-between gap-3">
                            <div>
                              <h2 className="text-lg font-semibold tracking-tight text-foreground">Matching files</h2>
                              <p className="mt-1 text-sm text-muted-foreground">
                                Pick one matching file to focus on. The full paths are available below when you need them.
                              </p>
                            </div>
                            <StatusBadge
                              label={
                                selectedDuplicates.length === 1
                                  ? "1 extra copy"
                                  : `${selectedDuplicates.length} extra copies`
                              }
                              severity="info"
                            />
                          </div>
                          <ScrollArea className="w-full whitespace-nowrap">
                            <div className="flex gap-3 pb-2">
                              {selectedDuplicates.map((file) => {
                                const active = selectedDuplicate?.file_instance_id === file.file_instance_id;
                                return (
                                  <button
                                    key={file.file_instance_id || file.path}
                                    type="button"
                                    onClick={() => setSelectedDuplicateId(file.file_instance_id)}
                                    className={cn(
                                      "w-48 shrink-0 rounded-[24px] border p-3 text-left transition-all",
                                      active
                                        ? "border-primary/35 bg-primary/10 shadow-sm"
                                        : "border-border/70 bg-background/80 hover:border-primary/20 hover:bg-muted/40",
                                    )}
                                  >
                                    <DuplicateMediaPreview
                                      src={file.thumbnail_url}
                                      alt={basename(file.path)}
                                      isImage={file.is_image}
                                      mediaType={file.media_type}
                                      className="aspect-[4/3]"
                                    />
                                    <p className="mt-3 truncate text-sm font-semibold text-foreground">
                                      {basename(file.path)}
                                    </p>
                                    <p className="mt-1 line-clamp-2 text-xs text-muted-foreground">
                                      Compare this copy against the main version.
                                    </p>
                                  </button>
                                );
                              })}
                            </div>
                          </ScrollArea>
                        </section>
                      ) : null}

                      <Collapsible className="rounded-[24px] border border-border/70 bg-background/85">
                        <CollapsibleTrigger asChild>
                          <button
                            type="button"
                            className="flex w-full items-center justify-between gap-3 px-5 py-4 text-left"
                          >
                            <div>
                              <p className="text-sm font-semibold text-foreground">Technical details</p>
                              <p className="mt-1 text-sm text-muted-foreground">
                                Group ID, exact paths, and raw member data for deeper investigation.
                              </p>
                            </div>
                            <ChevronDown className="h-4 w-4 text-muted-foreground" />
                          </button>
                        </CollapsibleTrigger>
                        <CollapsibleContent className="space-y-4 border-t px-5 py-4">
                          <div className="grid gap-4 lg:grid-cols-2">
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
                          </div>
                          <div className="space-y-2">
                            <p className="text-xs font-semibold uppercase tracking-[0.22em] text-muted-foreground">
                              Group members
                            </p>
                            <div className="space-y-2">
                              {selected.duplicates.map((file: DuplicateFile) => (
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
                      description="Choose a duplicate group from the review queue to compare the main version against a matching file."
                    />
                  )}
                </CardContent>
              </Card>

              {selected ? (
                <DuplicateReviewActionBar
                  activeMark={reviewMarks[selected.group_id]}
                  hasPrev={selectedIndex > 0}
                  hasNext={selectedIndex >= 0 && selectedIndex < filteredGroups.length - 1}
                  onMark={applyReviewMark}
                  onNext={() => moveSelection(1)}
                  onPrev={() => moveSelection(-1)}
                />
              ) : null}
            </div>
          </div>
        </>
      )}
    </div>
  );
}
