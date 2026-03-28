import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, Copy, ExternalLink, ShieldAlert } from "lucide-react";
import { Link, useSearchParams } from "react-router-dom";

import { ErrorAlert } from "@/components/ErrorAlert";
import { EmptyState } from "@/components/EmptyState";
import { StatusBadge } from "@/components/StatusBadge";
import { DuplicateFocusCard } from "@/components/duplicates/DuplicateFocusCard";
import { DuplicateMediaPreview } from "@/components/duplicates/DuplicateMediaPreview";
import { DuplicateQueueItem } from "@/components/duplicates/DuplicateQueueItem";
import { DuplicateReviewActionBar } from "@/components/duplicates/DuplicateReviewActionBar";
import { TopSurfaceHeader } from "@/components/layout/TopSurfaceHeader";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  executeDuplicateReclaim,
  getDuplicateReclaimItems,
  getDuplicates,
  getIntegrityIssues,
  getPolicy,
  restoreDuplicateReclaim,
  setDuplicateReclaim,
  setDuplicateReview,
} from "@/lib/api/endpoints";
import { queryKeys } from "@/lib/api/queryKeys";
import { queryOptions } from "@/lib/api/queryOptions";
import { cn } from "@/lib/utils";
import type { DuplicateFile, DuplicateGroup, DuplicateReclaimItem, IntegrityIssue, Policy } from "@/types";

type ReviewMark = "looks_right" | "needs_review" | "not_sure";
type ReviewFilter = "all" | "unreviewed" | ReviewMark;
type DuplicatesTab = "review" | "removal" | "playback-issues";

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

function formatBytes(value: number): string {
  if (value >= 1024 ** 3) return `${(value / (1024 ** 3)).toFixed(2)} GB`;
  if (value >= 1024 ** 2) return `${(value / (1024 ** 2)).toFixed(1)} MB`;
  return `${value} B`;
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

function getDuplicatesTab(value: string | null): DuplicatesTab {
  if (value === "removal" || value === "playback-issues") return value;
  return "review";
}

function isIssueBlocking(issue: IntegrityIssue): boolean {
  return issue.status === "BROKEN";
}

export default function DuplicatesPage() {
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [selectedDuplicateId, setSelectedDuplicateId] = useState<string | null>(null);
  const [reviewFilter, setReviewFilter] = useState<ReviewFilter>("unreviewed");
  const [searchParams, setSearchParams] = useSearchParams();
  const activeTab = getDuplicatesTab(searchParams.get("tab"));
  const queryClient = useQueryClient();

  const duplicatesQuery = useQuery({
    queryKey: queryKeys.duplicates,
    queryFn: async () => (await getDuplicates()).data,
    staleTime: queryOptions.duplicates.staleTime,
  });
  const policyQuery = useQuery({
    queryKey: queryKeys.policy,
    queryFn: async () => (await getPolicy()).data,
    staleTime: queryOptions.policy.staleTime,
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

  const reclaimMutation = useMutation({
    mutationFn: (payload: { content_id: string; reclaim_status: "UNREVIEWED" | "REVIEWED_SAFE_TO_RECLAIM" }) =>
      setDuplicateReclaim(payload),
    onMutate: async (payload) => {
      await queryClient.cancelQueries({ queryKey: queryKeys.duplicates });
      const previous = queryClient.getQueryData<DuplicateGroup[]>(queryKeys.duplicates);
      queryClient.setQueryData<DuplicateGroup[]>(queryKeys.duplicates, (current = []) =>
        current.map((group) =>
          group.group_id === payload.content_id
            ? {
                ...group,
                reclaim_status: payload.reclaim_status,
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

  const reclaimItemsQuery = useQuery({
    queryKey: queryKeys.duplicateReclaimItems(1, 50),
    queryFn: async () => (await getDuplicateReclaimItems({ page: 1, limit: 50 })).data,
  });

  const playbackIssuesQuery = useQuery({
    queryKey: queryKeys.integrityIssues({ page: 1, limit: 200 }),
    queryFn: async () => (await getIntegrityIssues({ page: 1, limit: 200 })).data,
    enabled: activeTab === "playback-issues",
  });

  const executeReclaimMutation = useMutation({
    mutationFn: (payload: { content_ids: string[]; retention_days: number }) => executeDuplicateReclaim(payload),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.duplicates });
      void queryClient.invalidateQueries({ queryKey: ["duplicates", "reclaim-items"] });
    },
  });

  const restoreReclaimMutation = useMutation({
    mutationFn: (fileInstanceId: string) => restoreDuplicateReclaim({ file_instance_ids: [fileInstanceId] }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.duplicates });
      void queryClient.invalidateQueries({ queryKey: ["duplicates", "reclaim-items"] });
    },
  });

  const groups = (duplicatesQuery.data as DuplicateGroup[] | undefined) ?? [];
  const policy = (policyQuery.data as Policy | undefined) ?? null;
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
  const reclaimReadyCount = sortedGroups.filter((group) => group.reclaim_status === "REVIEWED_SAFE_TO_RECLAIM").length;
  const totalReclaimableFiles = sortedGroups.reduce((sum, group) => sum + (group.reclaimable_file_count ?? 0), 0);
  const totalEstimatedBytes = sortedGroups.reduce((sum, group) => sum + (group.estimated_reclaim_bytes ?? 0), 0);
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
  const reclaimItems = ((reclaimItemsQuery.data?.items ?? []) as DuplicateReclaimItem[]) ?? [];
  const archivedItems = reclaimItems.filter((item) => item.item_status === "ARCHIVED");
  const readyGroups = sortedGroups.filter((group) => group.reclaim_status === "REVIEWED_SAFE_TO_RECLAIM");
  const removalReviewGroups = sortedGroups.filter(
    (group) =>
      (group.reclaimable_file_count ?? 0) > 0 &&
      group.reclaim_status !== "REVIEWED_SAFE_TO_RECLAIM" &&
      group.reclaim_status !== "ARCHIVED",
  );

  const integrityIssues = ((playbackIssuesQuery.data?.items ?? []) as IntegrityIssue[]) ?? [];
  const issuesByFileId = useMemo(
    () =>
      integrityIssues.reduce<Record<string, IntegrityIssue[]>>((acc, issue) => {
        if (!acc[issue.file_instance_id]) acc[issue.file_instance_id] = [];
        acc[issue.file_instance_id].push(issue);
        return acc;
      }, {}),
    [integrityIssues],
  );

  const duplicatePlaybackGroups = useMemo(
    () =>
      sortedGroups
        .map((group) => {
          const issues = group.duplicates.flatMap((file) => issuesByFileId[file.file_instance_id] ?? []);
          if (!issues.length) return null;
          const brokenCount = issues.filter((issue) => issue.status === "BROKEN").length;
          const suspectCount = issues.filter((issue) => issue.status === "SUSPECT").length;
          return {
            group,
            issues,
            brokenCount,
            suspectCount,
            affectedFiles: group.duplicates.filter((file) => (issuesByFileId[file.file_instance_id] ?? []).length > 0),
          };
        })
        .filter(Boolean) as Array<{
        group: DuplicateGroup;
        issues: IntegrityIssue[];
        brokenCount: number;
        suspectCount: number;
        affectedFiles: DuplicateFile[];
      }>,
    [issuesByFileId, sortedGroups],
  );
  const reviewProgressLabel =
    selectedOverallIndex >= 0 ? `${selectedOverallIndex + 1} of ${sortedGroups.length}` : `0 of ${sortedGroups.length}`;

  function setActiveTab(nextTab: DuplicatesTab) {
    const nextParams = new URLSearchParams(searchParams);
    nextParams.set("tab", nextTab);
    setSearchParams(nextParams);
  }

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
      if (activeTab !== "review") return;
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
  }, [activeTab, selected, selectedIndex, filteredGroups, sortedGroups]);

  return (
    <div
      className={cn(
        "mx-auto flex flex-col",
        activeTab === "review"
          ? "max-w-[96rem] gap-3 px-4 py-4 lg:px-5"
          : "max-w-7xl gap-5 p-6",
      )}
    >
      <TopSurfaceHeader
        badge="Duplicate Review"
        title="Work duplicate decisions in focused steps."
        description="Compare groups, review removal workflow, and inspect playback exceptions without mixing those jobs together."
        icon={Copy}
        density={activeTab === "review" ? "compact" : "default"}
        className={activeTab === "review" ? "rounded-[24px]" : undefined}
      />

      {duplicatesQuery.error && (
        <ErrorAlert message={getErrorMessage(duplicatesQuery.error) || "Failed to load duplicate groups"} />
      )}
      {reviewMutation.error && (
        <ErrorAlert message={getErrorMessage(reviewMutation.error) || "Failed to save duplicate review"} />
      )}
      {reclaimMutation.error && (
        <ErrorAlert message={getErrorMessage(reclaimMutation.error) || "Failed to save reclaim readiness"} />
      )}
      {executeReclaimMutation.error && (
        <ErrorAlert message={getErrorMessage(executeReclaimMutation.error) || "Failed to archive reclaimable duplicates"} />
      )}
      {restoreReclaimMutation.error && (
        <ErrorAlert message={getErrorMessage(restoreReclaimMutation.error) || "Failed to restore archived duplicate"} />
      )}
      {playbackIssuesQuery.error && activeTab === "playback-issues" ? (
        <ErrorAlert message={getErrorMessage(playbackIssuesQuery.error) || "Failed to load duplicate playback issues"} />
      ) : null}

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
        <Tabs value={activeTab} onValueChange={(value) => setActiveTab(value as DuplicatesTab)} className="space-y-4">
          <Card className={cn("rounded-[24px] border-border/70 bg-card/95 shadow-sm", activeTab === "review" && "shadow-none")}>
            <CardContent className={cn("space-y-4 p-4", activeTab === "review" && "space-y-3 p-3")}>
              <TabsList className="flex h-auto w-full flex-wrap justify-start gap-2 rounded-[18px] bg-muted/60 p-1">
                <TabsTrigger value="review">Review duplicates</TabsTrigger>
                <TabsTrigger value="removal">Removal review</TabsTrigger>
                <TabsTrigger value="playback-issues">Playback issues</TabsTrigger>
              </TabsList>

              <TabsContent value="review" className="mt-0">
                <div className="space-y-2">
                  <div className="flex flex-col gap-2 lg:flex-row lg:items-center lg:justify-between">
                    <div>
                      <h2 className="text-lg font-semibold tracking-tight text-foreground">Review duplicates</h2>
                      <p className="mt-1 text-sm text-muted-foreground">
                        Compare one group at a time, mark the human review state, and move on.
                      </p>
                    </div>
                    <div className="flex flex-wrap items-center gap-2">
                      <StatusBadge label={reviewProgressLabel} severity="info" />
                      <StatusBadge label={`${sortedGroups.length - reviewedCount} left`} severity="caution" />
                      <StatusBadge label={`${filteredGroups.length} in filter`} severity="neutral" />
                    </div>
                  </div>
                </div>
              </TabsContent>

              <TabsContent value="removal" className="mt-0">
                <div className="space-y-2">
                  <h2 className="text-xl font-semibold tracking-tight text-foreground">Removal review</h2>
                  <p className="text-sm text-muted-foreground">
                    Work the existing reclaim workflow from an explicit operational queue.
                  </p>
                </div>
              </TabsContent>

              <TabsContent value="playback-issues" className="mt-0">
                <div className="space-y-2">
                  <h2 className="text-xl font-semibold tracking-tight text-foreground">Playback issues</h2>
                  <p className="text-sm text-muted-foreground">
                    Inspect duplicate-related blockers and warnings, then continue review here or in Integrity Review.
                  </p>
                </div>
              </TabsContent>
            </CardContent>
          </Card>

          <TabsContent value="review" className="mt-0">
            <div className="grid gap-3 xl:grid-cols-[260px_minmax(0,1fr)]">
              <Card className="rounded-[22px] border-border/70 bg-card/95 shadow-sm">
                <CardContent className="space-y-3 p-3">
                  <div className="space-y-2">
                    <div>
                      <p className="text-sm font-semibold text-foreground">Group navigation</p>
                      <p className="text-sm text-muted-foreground">Use this queue to jump around. Back and Next drive the main review loop.</p>
                    </div>
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
                  </div>

                  <ScrollArea className="h-[40rem] pr-2">
                    <div className="space-y-3">
                      {filteredGroups.map((group, index) => {
                        const presentation = getReviewPresentation(currentReviewMark(group), Boolean(group.is_stale));
                        return (
                          <DuplicateQueueItem
                            key={group.group_id}
                            index={index}
                            active={selected?.group_id === group.group_id}
                            group={group}
                            markLabel={presentation.label}
                            markSeverity={presentation.severity}
                            onSelect={() => setSelectedId(group.group_id)}
                          />
                        );
                      })}
                    </div>
                  </ScrollArea>
                </CardContent>
              </Card>

              <Card className="rounded-[26px] border-border/70 bg-card/95 shadow-sm">
                <CardContent className="space-y-4 p-3 sm:p-4">
                  {selected && selectedCanonical ? (
                    <>
                      <div className="space-y-3">
                        <div className="flex flex-col gap-2 lg:flex-row lg:items-start lg:justify-between">
                          <div className="min-w-0 space-y-2">
                            <div className="flex flex-wrap items-center gap-2">
                              {selectedReview ? <StatusBadge label={selectedReview.label} severity={selectedReview.severity} /> : null}
                              <StatusBadge
                                label={
                                  selectedDuplicates.length === 1
                                    ? "1 matching copy"
                                    : `${selectedDuplicates.length} matching copies`
                                }
                                severity="info"
                              />
                              <StatusBadge label={`${selected.duplicates.length} files in group`} severity="neutral" />
                            </div>
                            <p
                              className="truncate text-xl font-semibold tracking-tight text-foreground"
                              title={basename(selected.canonical_path)}
                              data-testid="review-group-title"
                            >
                              {basename(selected.canonical_path)}
                            </p>
                            <p className="text-sm text-muted-foreground">
                              Compare the main version against the selected copy, then mark the group and continue.
                            </p>
                          </div>
                        </div>
                        <DuplicateReviewActionBar
                          activeMark={currentReviewMark(selected)}
                          hasPrev={selectedIndex > 0}
                          hasNext={selectedIndex >= 0 && selectedIndex < filteredGroups.length - 1}
                          onMark={applyReviewMark}
                          onNext={() => moveSelection(1)}
                          onPrev={() => moveSelection(-1)}
                          sticky={false}
                          compact
                          progressLabel={`${reviewProgressLabel} • ${reviewedCount} reviewed`}
                        />
                        {(selected.integrity_issue_count ?? 0) > 0 ? (
                          <div className="flex flex-col gap-2 rounded-[18px] border border-caution/30 bg-caution/10 px-3 py-2.5 lg:flex-row lg:items-center lg:justify-between">
                            <div className="min-w-0">
                              <div className="flex flex-wrap items-center gap-2">
                                <StatusBadge
                                  label={`${selected.integrity_issue_count} playback issue${selected.integrity_issue_count === 1 ? "" : "s"}`}
                                  severity="caution"
                                />
                                {(selected.integrity_broken_count ?? 0) > 0 ? (
                                  <StatusBadge label={`${selected.integrity_broken_count} broken`} severity="destructive" />
                                ) : null}
                                {(selected.integrity_suspect_count ?? 0) > 0 ? (
                                  <StatusBadge label={`${selected.integrity_suspect_count} suspect`} severity="caution" />
                                ) : null}
                              </div>
                              <p className="mt-1 text-sm text-muted-foreground">
                                Check Playback Issues if file health is affecting this decision.
                              </p>
                            </div>
                            <div className="flex gap-2">
                              <Button type="button" variant="outline" size="sm" onClick={() => setActiveTab("playback-issues")}>
                                Open playback issues
                              </Button>
                              <Button asChild type="button" variant="outline" size="sm">
                                <Link to="/integrity">
                                  Integrity review
                                  <ExternalLink className="h-4 w-4" />
                                </Link>
                              </Button>
                            </div>
                          </div>
                        ) : null}
                      </div>

                      <div className="grid gap-3 xl:grid-cols-[minmax(0,1.55fr)_minmax(0,1.1fr)]">
                        <DuplicateFocusCard
                          badge="Main version"
                          description="Anchor this comparison against the selected duplicate."
                          emphasis="success"
                          file={selectedCanonical}
                          previewClassName="h-[26rem] sm:h-[34rem] lg:h-[44rem]"
                          previewFit="contain"
                          previewTestId="primary-comparison-preview"
                          titleTestId="primary-comparison-title"
                        />

                        {selectedDuplicate ? (
                          <DuplicateFocusCard
                            badge="Currently comparing"
                            description={`Selected duplicate ${selectedDuplicates.findIndex((file) => file.file_instance_id === selectedDuplicate.file_instance_id) + 1} updates this pane immediately.`}
                            emphasis="info"
                            file={selectedDuplicate}
                            title={`Selected copy: ${basename(selectedDuplicate.path)}`}
                            previewClassName="h-[26rem] sm:h-[34rem] lg:h-[44rem]"
                            previewFit="contain"
                            previewTestId="secondary-comparison-preview"
                            titleTestId="secondary-comparison-title"
                          />
                        ) : (
                          <Card className="rounded-[22px] border-border/70 bg-background/85 shadow-sm">
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
                        <section className="space-y-2.5">
                          <div className="flex items-center justify-between gap-3">
                            <h3 className="text-xs font-semibold uppercase tracking-[0.18em] text-muted-foreground">
                              Select the duplicate to compare
                            </h3>
                            {selectedDuplicate ? (
                              <p
                                className="max-w-[28rem] truncate text-xs text-muted-foreground"
                                title={basename(selectedDuplicate.path)}
                                data-testid="active-duplicate-caption"
                              >
                                Active: {basename(selectedDuplicate.path)}
                              </p>
                            ) : null}
                          </div>
                          <ScrollArea className="w-full whitespace-nowrap">
                            <div className="flex gap-2 pb-2">
                              {selectedDuplicates.map((file, index) => {
                                const active = selectedDuplicate?.file_instance_id === file.file_instance_id;
                                return (
                                  <button
                                    key={file.file_instance_id || file.path}
                                    type="button"
                                    onClick={() => setSelectedDuplicateId(file.file_instance_id)}
                                    aria-pressed={active}
                                    aria-label={`Compare duplicate ${index + 1}: ${basename(file.path)}`}
                                    className={cn(
                                      "w-40 shrink-0 rounded-[18px] border p-2 text-left transition-all",
                                      active
                                        ? "border-primary bg-primary/8 shadow-sm ring-2 ring-primary/25"
                                        : "border-border/70 bg-background/80 hover:border-primary/20 hover:bg-muted/30",
                                    )}
                                  >
                                    <div className="mb-2 flex items-center justify-between gap-2">
                                      <span className="text-[11px] font-medium text-muted-foreground">{index + 1}</span>
                                      {active ? <StatusBadge label="Comparing" severity="info" /> : null}
                                    </div>
                                    <DuplicateMediaPreview
                                      src={file.preview_url ?? (file.is_image ? file.media_url ?? file.thumbnail_url : null)}
                                      alt={basename(file.path)}
                                      isImage={file.is_image}
                                      mediaType={file.media_type}
                                      className="h-24 rounded-[16px]"
                                      fit="contain"
                                    />
                                    <p
                                      className="mt-2 truncate text-xs font-medium text-foreground"
                                      title={basename(file.path)}
                                    >
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
                                Paths and reference IDs for moments when visual review is not enough.
                              </p>
                            </div>
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
                    </>
                  ) : (
                    <EmptyState
                      title="Select a group to compare"
                      description="Choose a duplicate group from the active filter to compare the main version against a matching file."
                    />
                  )}
                </CardContent>
              </Card>
            </div>
          </TabsContent>

          <TabsContent value="removal" className="mt-0">
            <div className="space-y-4">
              <div className="grid gap-3 md:grid-cols-3">
                <Card className="rounded-[22px] border-border/70 bg-card/95 shadow-sm">
                  <CardContent className="space-y-1 p-4">
                    <p className="text-xs uppercase tracking-[0.18em] text-muted-foreground">Ready groups</p>
                    <p className="text-2xl font-semibold text-foreground">{readyGroups.length}</p>
                    <p className="text-sm text-muted-foreground">{totalReclaimableFiles} files reclaimable across duplicate groups.</p>
                  </CardContent>
                </Card>
                <Card className="rounded-[22px] border-border/70 bg-card/95 shadow-sm">
                  <CardContent className="space-y-1 p-4">
                    <p className="text-xs uppercase tracking-[0.18em] text-muted-foreground">Estimated savings</p>
                    <p className="text-2xl font-semibold text-foreground">{formatBytes(totalEstimatedBytes)}</p>
                    <p className="text-sm text-muted-foreground">Operational estimate based on existing duplicate read models.</p>
                  </CardContent>
                </Card>
                <Card className="rounded-[22px] border-border/70 bg-card/95 shadow-sm">
                  <CardContent className="space-y-1 p-4">
                    <p className="text-xs uppercase tracking-[0.18em] text-muted-foreground">Archived items</p>
                    <p className="text-2xl font-semibold text-foreground">{archivedItems.length}</p>
                    <p className="text-sm text-muted-foreground">Restore candidates remain grouped separately below.</p>
                  </CardContent>
                </Card>
              </div>

              <Card className="rounded-[24px] border-border/70 bg-card/95 shadow-sm">
                <CardContent className="space-y-4 p-4">
                  <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
                    <div>
                      <p className="text-sm font-semibold text-foreground">Ready to archive</p>
                      <p className="text-sm text-muted-foreground">
                        Groups already marked safe in the current reclaim workflow.
                      </p>
                    </div>
                    <Button
                      type="button"
                      onClick={() =>
                        executeReclaimMutation.mutate({
                          content_ids: readyGroups.map((group) => group.group_id),
                          retention_days: policy?.duplicate_reclaim.default_retention_days ?? 14,
                        })
                      }
                      disabled={executeReclaimMutation.isPending || readyGroups.length === 0}
                    >
                      Archive reclaimable
                    </Button>
                  </div>

                  {!readyGroups.length ? (
                    <p className="text-sm text-muted-foreground">No groups are currently marked safe to reclaim.</p>
                  ) : (
                    <div className="space-y-3">
                      {readyGroups.map((group) => (
                        <div
                          key={group.group_id}
                          className="flex flex-col gap-3 rounded-[22px] border border-border/70 bg-background/70 p-4 lg:flex-row lg:items-center lg:justify-between"
                        >
                          <div className="min-w-0 space-y-2">
                            <div className="flex flex-wrap items-center gap-2">
                              <StatusBadge label="Ready to archive" severity="success" />
                              <StatusBadge
                                label={`${group.reclaimable_file_count ?? 0} reclaimable file${(group.reclaimable_file_count ?? 0) === 1 ? "" : "s"}`}
                                severity="neutral"
                              />
                              <StatusBadge label={formatBytes(group.estimated_reclaim_bytes ?? 0)} severity="info" />
                            </div>
                            <p className="truncate text-sm font-semibold text-foreground">{basename(group.canonical_path)}</p>
                            <p className="text-xs text-muted-foreground">
                              Review state: {getReviewPresentation(currentReviewMark(group), Boolean(group.is_stale)).label}
                            </p>
                          </div>
                          <div className="flex gap-2">
                            <Button
                              type="button"
                              variant="outline"
                              onClick={() =>
                                reclaimMutation.mutate({
                                  content_id: group.group_id,
                                  reclaim_status: "UNREVIEWED",
                                })
                              }
                              disabled={reclaimMutation.isPending}
                            >
                              Undo ready state
                            </Button>
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </CardContent>
              </Card>

              <Card className="rounded-[24px] border-border/70 bg-card/95 shadow-sm">
                <CardContent className="space-y-4 p-4">
                  <div>
                    <p className="text-sm font-semibold text-foreground">Needs removal review</p>
                    <p className="text-sm text-muted-foreground">
                      Groups that can enter the reclaim workflow but are not yet marked safe.
                    </p>
                  </div>

                  {!removalReviewGroups.length ? (
                    <p className="text-sm text-muted-foreground">No additional groups are waiting for reclaim review.</p>
                  ) : (
                    <div className="space-y-3">
                      {removalReviewGroups.map((group) => (
                        <div
                          key={group.group_id}
                          className="flex flex-col gap-3 rounded-[22px] border border-border/70 bg-background/70 p-4 lg:flex-row lg:items-center lg:justify-between"
                        >
                          <div className="min-w-0 space-y-2">
                            <div className="flex flex-wrap items-center gap-2">
                              <StatusBadge label="Needs reclaim decision" severity="caution" />
                              <StatusBadge
                                label={`${group.reclaimable_file_count ?? 0} reclaimable file${(group.reclaimable_file_count ?? 0) === 1 ? "" : "s"}`}
                                severity="neutral"
                              />
                              <StatusBadge label={formatBytes(group.estimated_reclaim_bytes ?? 0)} severity="info" />
                            </div>
                            <p className="truncate text-sm font-semibold text-foreground">{basename(group.canonical_path)}</p>
                            <p className="text-xs text-muted-foreground">
                              Review state: {getReviewPresentation(currentReviewMark(group), Boolean(group.is_stale)).label}
                            </p>
                          </div>
                          <div className="flex gap-2">
                            <Button
                              type="button"
                              onClick={() =>
                                reclaimMutation.mutate({
                                  content_id: group.group_id,
                                  reclaim_status: "REVIEWED_SAFE_TO_RECLAIM",
                                })
                              }
                              disabled={reclaimMutation.isPending}
                            >
                              Mark safe to reclaim
                            </Button>
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </CardContent>
              </Card>

              <Card className="rounded-[24px] border-border/70 bg-card/95 shadow-sm">
                <CardContent className="space-y-4 p-4">
                  <div>
                    <p className="text-sm font-semibold text-foreground">Archived items / restore candidates</p>
                    <p className="text-sm text-muted-foreground">
                      Files already archived in the existing duplicate reclaim workflow.
                    </p>
                  </div>

                  {!archivedItems.length ? (
                    <p className="text-sm text-muted-foreground">No duplicate files are archived yet.</p>
                  ) : (
                    <div className="space-y-3">
                      {archivedItems.map((item) => (
                        <div
                          key={item.file_instance_id}
                          className="flex flex-col gap-3 rounded-[22px] border border-border/70 bg-background/70 p-4 lg:flex-row lg:items-center lg:justify-between"
                        >
                          <div className="min-w-0 space-y-2">
                            <div className="flex flex-wrap items-center gap-2">
                              <StatusBadge label="Archived" severity="neutral" />
                              {item.expires_at ? (
                                <StatusBadge label={`Expires ${new Date(item.expires_at).toLocaleDateString()}`} severity="info" />
                              ) : null}
                            </div>
                            <p className="truncate text-sm font-semibold text-foreground">{basename(item.original_path)}</p>
                            <p className="truncate text-xs text-muted-foreground">{item.archive_path}</p>
                          </div>
                          <Button
                            type="button"
                            variant="outline"
                            onClick={() => restoreReclaimMutation.mutate(item.file_instance_id)}
                            disabled={restoreReclaimMutation.isPending}
                          >
                            Restore
                          </Button>
                        </div>
                      ))}
                    </div>
                  )}
                </CardContent>
              </Card>
            </div>
          </TabsContent>

          <TabsContent value="playback-issues" className="mt-0">
            <div className="space-y-4">
              <Card className="rounded-[24px] border-border/70 bg-card/95 shadow-sm">
                <CardContent className="space-y-3 p-4">
                  <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
                    <div>
                      <p className="text-sm font-semibold text-foreground">Duplicate-related playback exceptions</p>
                      <p className="text-sm text-muted-foreground">
                        This view stays limited to issues attached to files in duplicate groups.
                      </p>
                    </div>
                    <div className="flex gap-2">
                      <Button type="button" variant="outline" onClick={() => setActiveTab("review")}>
                        Back to review
                      </Button>
                      <Button asChild type="button" variant="outline">
                        <Link to="/integrity">
                          Open integrity review
                          <ExternalLink className="h-4 w-4" />
                        </Link>
                      </Button>
                    </div>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    <StatusBadge label={`${duplicatePlaybackGroups.length} affected group${duplicatePlaybackGroups.length === 1 ? "" : "s"}`} severity="neutral" />
                    <StatusBadge
                      label={`${duplicatePlaybackGroups.filter((entry) => entry.brokenCount > 0).length} blocker cue${duplicatePlaybackGroups.filter((entry) => entry.brokenCount > 0).length === 1 ? "" : "s"}`}
                      severity="destructive"
                    />
                    <StatusBadge
                      label={`${duplicatePlaybackGroups.filter((entry) => entry.brokenCount === 0 && entry.suspectCount > 0).length} warning cue${duplicatePlaybackGroups.filter((entry) => entry.brokenCount === 0 && entry.suspectCount > 0).length === 1 ? "" : "s"}`}
                      severity="caution"
                    />
                  </div>
                </CardContent>
              </Card>

              {playbackIssuesQuery.isLoading ? (
                <Skeleton className="h-80 rounded-[24px]" />
              ) : !duplicatePlaybackGroups.length ? (
                <EmptyState
                  icon={<ShieldAlert className="h-10 w-10" />}
                  title="No duplicate-related playback issues"
                  description="Integrity review can still show unrelated file-health findings, but none are attached to the current duplicate groups."
                />
              ) : (
                <div className="space-y-4">
                  {duplicatePlaybackGroups.map(({ group, issues, brokenCount, suspectCount, affectedFiles }) => {
                    const hasBlockingCue = issues.some(isIssueBlocking);
                    return (
                      <Card key={group.group_id} className="rounded-[24px] border-border/70 bg-card/95 shadow-sm">
                        <CardContent className="space-y-4 p-4">
                          <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
                            <div className="min-w-0 space-y-2">
                              <div className="flex flex-wrap gap-2">
                                <StatusBadge
                                  label={hasBlockingCue ? "Blocks removal in this view" : "Warning in this view"}
                                  severity={hasBlockingCue ? "destructive" : "caution"}
                                />
                                {brokenCount > 0 ? <StatusBadge label={`${brokenCount} broken`} severity="destructive" /> : null}
                                {suspectCount > 0 ? <StatusBadge label={`${suspectCount} suspect`} severity="caution" /> : null}
                              </div>
                              <p className="truncate text-lg font-semibold text-foreground">{basename(group.canonical_path)}</p>
                              <p className="text-sm text-muted-foreground">
                                {hasBlockingCue
                                  ? "Use this as a blocker cue while reviewing duplicates here. This does not change backend reclaim eligibility."
                                  : "Use this as a warning cue while reviewing duplicates here. Deeper diagnosis still belongs in Integrity Review."}
                              </p>
                            </div>
                            <div className="flex gap-2">
                              <Button
                                type="button"
                                variant="outline"
                                onClick={() => {
                                  setSelectedId(group.group_id);
                                  setActiveTab("review");
                                }}
                              >
                                Open in review
                              </Button>
                              <Button asChild type="button" variant="outline">
                                <Link to="/integrity">
                                  Integrity review
                                  <ExternalLink className="h-4 w-4" />
                                </Link>
                              </Button>
                            </div>
                          </div>

                          <div className="grid gap-3 lg:grid-cols-2">
                            <div className="rounded-[20px] border border-border/70 bg-background/70 p-4">
                              <p className="text-sm font-semibold text-foreground">Affected files</p>
                              <div className="mt-3 space-y-2">
                                {affectedFiles.map((file) => {
                                  const fileIssues = issuesByFileId[file.file_instance_id] ?? [];
                                  return (
                                    <div
                                      key={file.file_instance_id}
                                      className="flex flex-wrap items-center justify-between gap-2 rounded-2xl border border-border/70 bg-card/80 px-3 py-2"
                                    >
                                      <span className="min-w-0 truncate text-sm text-foreground">{basename(file.path)}</span>
                                      <div className="flex flex-wrap gap-2">
                                        {fileIssues.map((issue) => (
                                          <StatusBadge
                                            key={issue.check_id}
                                            label={issue.status === "BROKEN" ? "Broken" : "Suspect"}
                                            severity={issue.status === "BROKEN" ? "destructive" : "caution"}
                                          />
                                        ))}
                                      </div>
                                    </div>
                                  );
                                })}
                              </div>
                            </div>

                            <div className="rounded-[20px] border border-border/70 bg-background/70 p-4">
                              <p className="text-sm font-semibold text-foreground">Next step</p>
                              <div className="mt-3 rounded-2xl border border-border/70 bg-card/80 p-3">
                                <p className="text-sm text-foreground">
                                  {hasBlockingCue
                                    ? "Pause reclaim decisions for this group in the UI until the broken playback issue is understood."
                                    : "You can continue duplicate review here, but keep the warning in mind before acting in the reclaim workflow."}
                                </p>
                                <p className="mt-2 text-xs text-muted-foreground">
                                  This cue is scoped to this page only and does not redefine backend workflow policy.
                                </p>
                              </div>
                              <div className="mt-3 flex items-start gap-2 rounded-2xl border border-border/70 bg-card/80 p-3">
                                <AlertTriangle className="mt-0.5 h-4 w-4 text-caution" />
                                <p className="text-xs text-muted-foreground">
                                  Integrity Review remains the place for deeper diagnosis, file-level detail, and non-duplicate playback health work.
                                </p>
                              </div>
                            </div>
                          </div>
                        </CardContent>
                      </Card>
                    );
                  })}
                </div>
              )}
            </div>
          </TabsContent>
        </Tabs>
      )}
    </div>
  );
}
