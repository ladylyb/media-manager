import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ChevronDown, Copy } from "lucide-react";

import { ErrorAlert } from "@/components/ErrorAlert";
import { EmptyState } from "@/components/EmptyState";
import { StatusBadge } from "@/components/StatusBadge";
import { DuplicateFocusCard } from "@/components/duplicates/DuplicateFocusCard";
import { DuplicateMediaPreview } from "@/components/duplicates/DuplicateMediaPreview";
import { DuplicateReviewActionBar } from "@/components/duplicates/DuplicateReviewActionBar";
import { DuplicateReviewProgress } from "@/components/duplicates/DuplicateReviewProgress";
import { TopSurfaceHeader } from "@/components/layout/TopSurfaceHeader";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Skeleton } from "@/components/ui/skeleton";
import { getDuplicates, setDuplicateReview } from "@/lib/api/endpoints";
import { queryKeys } from "@/lib/api/queryKeys";
import { queryOptions } from "@/lib/api/queryOptions";
import { cn } from "@/lib/utils";
import type { DuplicateFile, DuplicateGroup } from "@/types";

type ReviewMark = "looks_right" | "needs_review" | "not_sure";
type ReviewFilter = "all" | "unreviewed" | ReviewMark;

const reviewOptions: Array<{ value: ReviewFilter; label: string }> = [
  { value: "all", label: "All" },
  { value: "unreviewed", label: "Still to review" },
  { value: "looks_right", label: "Looks right" },
  { value: "needs_review", label: "Needs review" },
  { value: "not_sure", label: "Not sure" },
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

function getReviewPresentation(mark?: ReviewMark, isStale = false) {
  if (isStale) {
    return { label: "Stale review", severity: "caution" as const };
  }
  switch (mark) {
    case "looks_right":
      return { label: "Looks right", severity: "success" as const };
    case "needs_review":
      return { label: "Needs review", severity: "destructive" as const };
    case "not_sure":
      return { label: "Not sure", severity: "caution" as const };
    default:
      return { label: "Still to review", severity: "caution" as const };
  }
}

function currentReviewMark(group: DuplicateGroup): ReviewMark | undefined {
  if (group.is_stale) return undefined;
  return group.review_status ?? undefined;
}

function reviewMarksByGroup(groups: DuplicateGroup[]): Record<string, ReviewMark> {
  return groups.reduce<Record<string, ReviewMark>>((acc, group) => {
    const mark = currentReviewMark(group);
    if (mark) acc[group.group_id] = mark;
    return acc;
  }, {});
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
  const queryClient = useQueryClient();

  const duplicatesQuery = useQuery({
    queryKey: queryKeys.duplicates,
    queryFn: async () => (await getDuplicates()).data,
    staleTime: queryOptions.duplicates.staleTime,
  });

  const reviewMutation = useMutation({
    mutationFn: (payload: {
      content_id: string;
      review_status: ReviewMark;
      reviewed_canonical_instance_id: string;
    }) => setDuplicateReview(payload),
    onMutate: async (payload) => {
      await queryClient.cancelQueries({ queryKey: queryKeys.duplicates });
      const previous = queryClient.getQueryData<DuplicateGroup[]>(queryKeys.duplicates);
      queryClient.setQueryData<DuplicateGroup[]>(queryKeys.duplicates, (current = []) =>
        current.map((group) =>
          group.group_id === payload.content_id
            ? {
                ...group,
                review_status: payload.review_status,
                reviewed_at: new Date().toISOString(),
                reviewed_canonical_instance_id: payload.reviewed_canonical_instance_id,
                is_stale: false,
                stale_reason: null,
              }
            : group,
        ),
      );
      return { previous };
    },
    onError: (_error, _payload, context) => {
      if (context?.previous) {
        queryClient.setQueryData(queryKeys.duplicates, context.previous);
      }
    },
    onSettled: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.duplicates });
    },
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
        const mark = currentReviewMark(group);
        if (reviewFilter === "unreviewed") return !mark;
        return mark === reviewFilter;
      }),
    [reviewFilter, sortedGroups],
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
  const reviewedCount = sortedGroups.filter((group) => currentReviewMark(group)).length;
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
  const selectedReview = selected ? getReviewPresentation(currentReviewMark(selected), Boolean(selected.is_stale)) : null;

  function moveSelection(direction: -1 | 1) {
    if (!filteredGroups.length || selectedIndex < 0) return;
    const nextIndex = selectedIndex + direction;
    if (nextIndex < 0 || nextIndex >= filteredGroups.length) return;
    setSelectedId(filteredGroups[nextIndex].group_id);
  }

  function applyReviewMark(mark: ReviewMark) {
    if (!selected || !selectedCanonical) return;

    const nextMarks = {
      ...reviewMarksByGroup(sortedGroups),
      [selected.group_id]: mark,
    };
    const nextSelectedId = findNextGroupIdAfterReview({
      currentId: selected.group_id,
      groups: sortedGroups,
      nextMarks,
    });

    reviewMutation.mutate({
      content_id: selected.group_id,
      review_status: mark,
      reviewed_canonical_instance_id: selectedCanonical.file_instance_id,
    });

    if (nextSelectedId && nextSelectedId !== selected.group_id) {
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
          applyReviewMark("looks_right");
          break;
        case "2":
          event.preventDefault();
          applyReviewMark("needs_review");
          break;
        case "3":
          event.preventDefault();
          applyReviewMark("not_sure");
          break;
        default:
          break;
      }
    }

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [selected, selectedIndex, filteredGroups, sortedGroups]);

  return (
    <div className="mx-auto flex max-w-7xl flex-col gap-5 p-6">
      <TopSurfaceHeader
        badge="Duplicate Review"
        title="Review duplicate groups."
        description="Focus on the images first, then mark the group and continue."
        icon={Copy}
      />

      {duplicatesQuery.error && (
        <ErrorAlert message={getErrorMessage(duplicatesQuery.error) || "Failed to load duplicate groups"} />
      )}
      {reviewMutation.error && (
        <ErrorAlert message={getErrorMessage(reviewMutation.error) || "Failed to save duplicate review"} />
      )}

      {duplicatesQuery.isLoading ? (
        <div className="space-y-4">
          <Skeleton className="h-28 rounded-[24px]" />
          <Skeleton className="h-[42rem] rounded-[28px]" />
        </div>
      ) : !groups.length ? (
        <EmptyState
          icon={<Copy className="h-10 w-10" />}
          title="No duplicate groups to review"
          description="Once the library finds matching files, they will appear here for side-by-side review."
        />
      ) : (
        <>
          <Card className="rounded-[24px] border-border/70 bg-card/95 shadow-sm">
            <CardContent className="space-y-4 p-4">
              <div className="flex flex-wrap items-start justify-between gap-4">
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    {selectedReview ? <StatusBadge label={selectedReview.label} severity={selectedReview.severity} /> : null}
                    {selected ? (
                      <>
                        <StatusBadge label={`${selected.duplicates.length} files in group`} severity="neutral" />
                        <StatusBadge
                          label={
                            selectedDuplicates.length === 1
                              ? "1 matching copy"
                              : `${selectedDuplicates.length} matching copies`
                          }
                          severity="info"
                        />
                      </>
                    ) : null}
                  </div>
                  <p className="mt-3 truncate text-xl font-semibold tracking-tight text-foreground">
                    {selected ? basename(selected.canonical_path) : "Select a duplicate group"}
                  </p>
                </div>
                <div className="flex items-center gap-2">
                  <Button type="button" variant="outline" onClick={() => moveSelection(-1)} disabled={selectedIndex <= 0}>
                    Prev
                  </Button>
                  <Button
                    type="button"
                    variant="outline"
                    onClick={() => moveSelection(1)}
                    disabled={selectedIndex < 0 || selectedIndex >= filteredGroups.length - 1}
                  >
                    Next
                  </Button>
                </div>
              </div>

              <DuplicateReviewProgress
                currentIndex={selectedOverallIndex < 0 ? 0 : selectedOverallIndex}
                total={sortedGroups.length}
                reviewedCount={reviewedCount}
              />

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
            </CardContent>
          </Card>

          <Card className="rounded-[30px] border-border/70 bg-card/95 shadow-sm">
            <CardContent className="space-y-6 p-4 sm:p-5">
              {selected && selectedCanonical ? (
                <>
                  <DuplicateReviewActionBar
                    activeMark={currentReviewMark(selected)}
                    hasPrev={selectedIndex > 0}
                    hasNext={selectedIndex >= 0 && selectedIndex < filteredGroups.length - 1}
                    onMark={applyReviewMark}
                    onNext={() => moveSelection(1)}
                    onPrev={() => moveSelection(-1)}
                    sticky={false}
                    showShortcutHint={false}
                  />

                  <div className="grid gap-4 xl:grid-cols-[minmax(0,1.5fr)_minmax(0,1fr)]">
                    <DuplicateFocusCard
                      badge="Main"
                      description="Use this as the anchor for the review."
                      emphasis="success"
                      file={selectedCanonical}
                      previewClassName="h-[24rem] sm:h-[32rem] lg:h-[40rem]"
                      previewFit="contain"
                    />

                    {selectedDuplicate ? (
                      <DuplicateFocusCard
                        badge="Selected copy"
                        description="Compare this copy against the main version."
                        emphasis="info"
                        file={selectedDuplicate}
                        previewClassName="h-[24rem] sm:h-[32rem] lg:h-[40rem]"
                        previewFit="contain"
                      />
                    ) : (
                      <Card className="rounded-[24px] border-border/70 bg-background/85 shadow-sm">
                        <CardContent className="flex h-full min-h-[14rem] items-center justify-center p-6 text-center">
                          <div className="space-y-2">
                            <StatusBadge label="No extra copies" severity="neutral" />
                            <p className="text-sm text-muted-foreground">Nothing else to compare in this group.</p>
                          </div>
                        </CardContent>
                      </Card>
                    )}
                  </div>

                  {selectedDuplicates.length ? (
                    <section className="space-y-3">
                      <div className="flex items-center justify-between gap-3">
                        <h2 className="text-sm font-semibold uppercase tracking-[0.18em] text-muted-foreground">
                          {selectedDuplicates.length} duplicate{selectedDuplicates.length === 1 ? "" : "s"}
                        </h2>
                      </div>
                      <ScrollArea className="w-full whitespace-nowrap">
                        <div className="flex gap-3 pb-2">
                          {selectedDuplicates.map((file, index) => {
                            const active = selectedDuplicate?.file_instance_id === file.file_instance_id;
                            return (
                              <button
                                key={file.file_instance_id || file.path}
                                type="button"
                                onClick={() => setSelectedDuplicateId(file.file_instance_id)}
                                className={cn(
                                  "w-36 shrink-0 rounded-[18px] border p-2.5 text-left transition-all",
                                  active
                                    ? "border-primary bg-primary/5 shadow-sm ring-1 ring-primary/20"
                                    : "border-border/70 bg-background/80 hover:border-primary/20 hover:bg-muted/30",
                                )}
                              >
                                <div className="mb-2 flex items-center justify-between gap-2">
                                  <span className="text-[11px] font-medium text-muted-foreground">{index + 1}</span>
                                  {active ? <StatusBadge label="Selected" severity="info" /> : null}
                                </div>
                                <DuplicateMediaPreview
                                  src={file.thumbnail_url}
                                  alt={basename(file.path)}
                                  isImage={file.is_image}
                                  mediaType={file.media_type}
                                  className="h-24 rounded-[16px]"
                                  fit="contain"
                                />
                                <p className="mt-2 truncate text-xs font-medium text-foreground">
                                  {basename(file.path)}
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
                            Exact paths and reference IDs for the moments when visual review is not enough.
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
                </>
              ) : (
                <EmptyState
                  title="Select a group to compare"
                  description="Choose a duplicate group from the active filter to compare the main version against a matching file."
                />
              )}
            </CardContent>
          </Card>

          {selected ? (
            <DuplicateReviewActionBar
              activeMark={currentReviewMark(selected)}
              hasPrev={selectedIndex > 0}
              hasNext={selectedIndex >= 0 && selectedIndex < filteredGroups.length - 1}
              onMark={applyReviewMark}
              onNext={() => moveSelection(1)}
              onPrev={() => moveSelection(-1)}
            />
          ) : null}
        </>
      )}
    </div>
  );
}
