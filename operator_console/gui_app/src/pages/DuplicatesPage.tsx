import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, Copy, ExternalLink, LayoutGrid, List, PanelLeft, PanelLeftClose, ShieldAlert } from "lucide-react";
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
import { Checkbox } from "@/components/ui/checkbox";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
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
type ReclaimSyncStatus = "UNREVIEWED" | "REVIEWED_SAFE_TO_RECLAIM";
type FeedbackTone = "success" | "warning";
type RecycleBinViewMode = "gallery" | "list";

interface MutationSummary {
  applied_count?: number;
  skipped_count?: number;
  moves_count?: number;
}

interface RecycleBinFeedback {
  tone: FeedbackTone;
  message: string;
}

const reviewOptions: Array<{ value: ReviewFilter; label: string }> = [
  { value: "all", label: "All" },
  { value: "unreviewed", label: "Still to review" },
  { value: "looks_right", label: "Looks right" },
  { value: "needs_review", label: "Needs review" },
  { value: "not_sure", label: "Not sure" },
];

const binStateLabels = {
  ready: "Ready to move",
  inBin: "In the holding area",
  needsReview: "Needs review",
  safeToRemove: "Safe to remove",
  restore: "Restore",
  moveToBin: "Move eligible duplicates",
  daysRemaining: "Days remaining",
  approachingExpiry: "Approaching permanent deletion",
  needsChecking: "Needs checking",
  playbackIssue: "Playback issue",
  wontPlay: "Won't play",
} as const;

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

function formatDaysRemaining(value: string | null | undefined): string | null {
  if (!value) return null;
  const milliseconds = new Date(value).getTime() - Date.now();
  if (Number.isNaN(milliseconds)) return null;
  const days = Math.max(Math.ceil(milliseconds / (1000 * 60 * 60 * 24)), 0);
  return days === 1 ? "1 day remaining" : `${days} days remaining`;
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

function getPlaybackStatusLabel(issue: IntegrityIssue): string {
  return issue.status === "BROKEN" ? binStateLabels.wontPlay : binStateLabels.needsChecking;
}

function getMutationSummary(payload: unknown): MutationSummary {
  if (!payload || typeof payload !== "object") return {};
  const summary = (payload as { summary?: MutationSummary }).summary;
  return summary && typeof summary === "object" ? summary : {};
}

function isPendingRemovalStatus(status: DuplicateGroup["reclaim_status"] | undefined | null) {
  return status === "ARCHIVED" || status === "RESTORED" || status === "SCHEDULED_FOR_DELETE";
}

function getKeepCopy(group: DuplicateGroup): DuplicateFile | null {
  return group.duplicates.find((file) => file.is_canonical) ?? group.duplicates[0] ?? null;
}

function getExtraCopies(group: DuplicateGroup): DuplicateFile[] {
  return group.duplicates.filter((file) => !file.is_canonical);
}

function getGalleryActionSummary(groupCount: number, appliedCount: number) {
  const groupLabel = `${groupCount} group${groupCount === 1 ? "" : "s"}`;
  const fileLabel = `${appliedCount} duplicate file${appliedCount === 1 ? "" : "s"}`;
  return `${fileLabel} moved from ${groupLabel} into the configured holding area. The keep copy stayed in place.`;
}

function getGalleryNoOpSummary(scope: "selected" | "all" | "single") {
  if (scope === "selected") {
    return "No new files were moved from the selected groups. Eligible duplicates were already processed or were no longer available to move.";
  }
  if (scope === "single") {
    return "No new files were moved from this group. Its eligible duplicates were already processed or were no longer available to move.";
  }
  return "No new files were moved. Eligible duplicates were already processed or were no longer available to move.";
}

export default function DuplicatesPage() {
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [selectedDuplicateId, setSelectedDuplicateId] = useState<string | null>(null);
  const [reviewFilter, setReviewFilter] = useState<ReviewFilter>("unreviewed");
  const [isReviewQueueOpen, setIsReviewQueueOpen] = useState(false);
  const [recycleBinViewMode, setRecycleBinViewMode] = useState<RecycleBinViewMode>("gallery");
  const [selectedReadyGroupIds, setSelectedReadyGroupIds] = useState<string[]>([]);
  const [reclaimBridgeBlockedIds, setReclaimBridgeBlockedIds] = useState<string[]>([]);
  const [reclaimBridgeWarning, setReclaimBridgeWarning] = useState<string | null>(null);
  const [recycleBinFeedback, setRecycleBinFeedback] = useState<RecycleBinFeedback | null>(null);
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
  const reclaimItems = ((reclaimItemsQuery.data?.items ?? []) as DuplicateReclaimItem[]) ?? [];
  const archivedItems = reclaimItems.filter((item) => item.item_status === "ARCHIVED");
  const restoredItems = reclaimItems.filter((item) => item.item_status === "RESTORED");
  const groupsById = useMemo(
    () =>
      sortedGroups.reduce<Record<string, DuplicateGroup>>((acc, group) => {
        acc[group.group_id] = group;
        return acc;
      }, {}),
    [sortedGroups],
  );
  const readyGroups = sortedGroups.filter(
    (group) =>
      currentReviewMark(group) === "looks_right" &&
      (group.reclaimable_file_count ?? 0) > 0 &&
      !isPendingRemovalStatus(group.reclaim_status) &&
      !reclaimBridgeBlockedIds.includes(group.group_id),
  );
  const readyExtraCopyCount = readyGroups.reduce((sum, group) => sum + (group.reclaimable_file_count ?? 0), 0);
  const readyEstimatedBytes = readyGroups.reduce((sum, group) => sum + (group.estimated_reclaim_bytes ?? 0), 0);
  const readyGroupIds = new Set(readyGroups.map((group) => group.group_id));
  const selectedReadyGroups = readyGroups.filter((group) => selectedReadyGroupIds.includes(group.group_id));
  const removalReviewGroups = sortedGroups.filter(
    (group) =>
      (group.reclaimable_file_count ?? 0) > 0 &&
      !readyGroupIds.has(group.group_id) &&
      !isPendingRemovalStatus(group.reclaim_status),
  );
  const archiveRoot = policy?.duplicate_reclaim.archive_root?.trim() ?? "";
  const archiveRetentionDays = policy?.duplicate_reclaim.default_retention_days ?? null;
  const recycleConfigWarning =
    policyQuery.error || !archiveRoot || !archiveRetentionDays
      ? "Recycle Bin details are unavailable right now. The app cannot confirm the configured holding area or retention window for this page."
      : null;

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
  const reviewMetaLine = selected
    ? `${reviewProgressLabel} • ${selectedDuplicates.length === 1 ? "1 matching copy" : `${selectedDuplicates.length} matching copies`} • ${reviewedCount} reviewed`
    : `${reviewProgressLabel} • ${reviewedCount} reviewed`;

  const readyGroupIdList = readyGroups.map((group) => group.group_id).join("|");

  useEffect(() => {
    setSelectedReadyGroupIds((current) => current.filter((groupId) => readyGroupIds.has(groupId)));
  }, [readyGroupIdList]);

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

  function markBridgeBlocked(groupId: string, blocked: boolean) {
    setReclaimBridgeBlockedIds((current) => {
      const next = new Set(current);
      if (blocked) {
        next.add(groupId);
      } else {
        next.delete(groupId);
      }
      return [...next];
    });
  }

  async function syncReclaimBridge(group: DuplicateGroup, reclaim_status: ReclaimSyncStatus, failureMessage: string) {
    try {
      await reclaimMutation.mutateAsync({
        content_id: group.group_id,
        reclaim_status,
      });
      markBridgeBlocked(group.group_id, false);
      setReclaimBridgeWarning((current) => (current && current.includes(group.group_id) ? null : current));
      return true;
    } catch {
      markBridgeBlocked(group.group_id, true);
      setReclaimBridgeWarning(failureMessage);
      setRecycleBinFeedback({ tone: "warning", message: failureMessage });
      return false;
    }
  }

  async function runPreflightReclaimSync(groupsToSync: DuplicateGroup[]) {
    for (const group of groupsToSync) {
      const synced = await syncReclaimBridge(
        group,
        "REVIEWED_SAFE_TO_RECLAIM",
        `Saved “Looks right” for ${basename(group.canonical_path)}, but the app could not confirm move eligibility. Try again before moving duplicates.`,
      );
      if (!synced) return false;
    }
    return true;
  }

  function toggleReadyGroupSelection(groupId: string, checked?: boolean) {
    setSelectedReadyGroupIds((current) => {
      const next = new Set(current);
      const shouldSelect = typeof checked === "boolean" ? checked : !next.has(groupId);
      if (shouldSelect) {
        next.add(groupId);
      } else {
        next.delete(groupId);
      }
      return [...next];
    });
  }

  function clearReadyGroupSelection() {
    setSelectedReadyGroupIds([]);
  }

  async function handleMoveEligibleDuplicates(groupsToMove: DuplicateGroup[] = readyGroups, scope: "selected" | "all" | "single" = "all") {
    setRecycleBinFeedback(null);
    if (recycleConfigWarning) {
      setRecycleBinFeedback({ tone: "warning", message: recycleConfigWarning });
      return;
    }
    if (!groupsToMove.length) {
      setRecycleBinFeedback({
        tone: "warning",
        message:
          scope === "selected"
            ? "Select one or more eligible groups to move their extra copies into the configured holding area."
            : "No new files were moved. No eligible extra copies are left to move from the main library.",
      });
      return;
    }

    const targetGroupIds = new Set(groupsToMove.map((group) => group.group_id));
    const groupsNeedingSync = groupsToMove.filter((group) => group.reclaim_status !== "REVIEWED_SAFE_TO_RECLAIM");
    const synced = await runPreflightReclaimSync(groupsNeedingSync);
    if (!synced) return;

    try {
      const result = await executeReclaimMutation.mutateAsync({
        content_ids: groupsToMove.map((group) => group.group_id),
        retention_days: archiveRetentionDays ?? 14,
      });
      const summary = getMutationSummary(result.data);
      const applied = Number(summary.applied_count ?? 0);
      setRecycleBinFeedback(
        applied > 0
          ? {
              tone: "success",
              message: getGalleryActionSummary(groupsToMove.length, applied),
            }
          : {
              tone: "warning",
              message: getGalleryNoOpSummary(scope),
            },
      );
      if (applied > 0) {
        setSelectedReadyGroupIds((current) => current.filter((groupId) => !targetGroupIds.has(groupId)));
      }
    } catch {
      setRecycleBinFeedback({
        tone: "warning",
        message: "The move action did not complete. No result was confirmed on this page.",
      });
    }
  }

  async function handleRestore(item: DuplicateReclaimItem) {
    setRecycleBinFeedback(null);
    try {
      const result = await restoreReclaimMutation.mutateAsync(item.file_instance_id);
      const summary = getMutationSummary(result.data);
      const applied = Number(summary.applied_count ?? 0);
      setRecycleBinFeedback(
        applied > 0
          ? {
              tone: "success",
              message: `${applied} file${applied === 1 ? "" : "s"} restored from the configured holding area. Restored groups stay out of Ready to move until they are reviewed again.`,
            }
          : {
              tone: "warning",
              message: "No files were restored. These items are no longer available to restore from the holding area.",
            },
      );
    } catch {
      setRecycleBinFeedback({
        tone: "warning",
        message: "The restore action did not complete. No result was confirmed on this page.",
      });
    }
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
    setRecycleBinFeedback(null);

    if (isPendingRemovalStatus(selected.reclaim_status)) {
      markBridgeBlocked(selected.group_id, false);
    } else if (mark === "looks_right") {
      void syncReclaimBridge(
        selected,
        "REVIEWED_SAFE_TO_RECLAIM",
        `Saved “Looks right” for ${basename(selected.canonical_path)}, but the app could not add it to Ready to move. Try again from the Recycle Bin tab.`,
      );
    } else if (
      selected.reclaim_status === "REVIEWED_SAFE_TO_RECLAIM" ||
      reclaimBridgeBlockedIds.includes(selected.group_id)
    ) {
      void syncReclaimBridge(
        selected,
        "UNREVIEWED",
        `Saved the review change for ${basename(selected.canonical_path)}, but the app could not remove it from Ready to move.`,
      );
    } else {
      markBridgeBlocked(selected.group_id, false);
    }

    if (nextSelectedId && nextSelectedId !== selected.group_id) {
      setSelectedId(nextSelectedId);
    }
  }

  function renderGalleryReadyCard(group: DuplicateGroup) {
    const keepCopy = getKeepCopy(group);
    const extraCopies = getExtraCopies(group);
    if (!keepCopy) return null;
    const isSelected = selectedReadyGroupIds.includes(group.group_id);

    return (
      <Card
        key={group.group_id}
        data-testid={`recycle-bin-gallery-card-${group.group_id}`}
        className={cn(
          "rounded-[24px] border-border/70 bg-card/95 shadow-sm transition-all",
          isSelected && "border-primary/45 ring-2 ring-primary/15",
        )}
      >
        <CardContent className="space-y-4 p-4">
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0 space-y-1">
              <p className="truncate text-base font-semibold text-foreground">{basename(group.canonical_path)}</p>
              <p className="text-sm text-muted-foreground">
                {extraCopies.length === 1 ? "1 extra copy" : `${extraCopies.length} extra copies`} • {formatBytes(group.estimated_reclaim_bytes ?? 0)}
              </p>
            </div>
            <div className="flex items-center gap-2">
              <Checkbox
                checked={isSelected}
                aria-label={`Select group ${basename(group.canonical_path)}`}
                onCheckedChange={(checked) => toggleReadyGroupSelection(group.group_id, Boolean(checked))}
                onClick={(event) => event.stopPropagation()}
              />
              <span className="text-xs text-muted-foreground">{isSelected ? "Selected" : "Select"}</span>
            </div>
          </div>

          <div
            role="button"
            tabIndex={0}
            className="space-y-4 outline-none"
            onClick={() => toggleReadyGroupSelection(group.group_id)}
            onKeyDown={(event) => {
              if (event.key === " " || event.key === "Enter") {
                event.preventDefault();
                toggleReadyGroupSelection(group.group_id);
              }
            }}
          >
            <div className="grid gap-3 xl:grid-cols-[minmax(0,1.2fr)_minmax(0,0.8fr)]">
              <div className="space-y-2">
                <p className="text-xs uppercase tracking-[0.18em] text-muted-foreground">Keep copy</p>
                <DuplicateMediaPreview
                  src={keepCopy.preview_url ?? (keepCopy.is_image ? keepCopy.media_url ?? keepCopy.thumbnail_url : null)}
                  alt={basename(keepCopy.path)}
                  isImage={keepCopy.is_image}
                  mediaType={keepCopy.media_type}
                  className="aspect-[4/3] sm:aspect-[16/10]"
                  fit="cover"
                />
              </div>
              <div className="space-y-2">
                <p className="text-xs uppercase tracking-[0.18em] text-muted-foreground">Extra copies</p>
                <div className="grid grid-cols-2 gap-2">
                  {extraCopies.slice(0, 4).map((file) => (
                    <DuplicateMediaPreview
                      key={file.file_instance_id}
                      src={file.preview_url ?? (file.is_image ? file.media_url ?? file.thumbnail_url : null)}
                      alt={basename(file.path)}
                      isImage={file.is_image}
                      mediaType={file.media_type}
                      className="aspect-square"
                      fit="cover"
                    />
                  ))}
                </div>
                {extraCopies.length > 4 ? (
                  <p className="text-xs text-muted-foreground">+{extraCopies.length - 4} more extra copies</p>
                ) : null}
              </div>
            </div>
          </div>

          <div className="flex items-center justify-between gap-3 border-t border-border/70 pt-3">
            <p className="text-xs text-muted-foreground">Only the extra copies in this group move into the configured holding area.</p>
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => void handleMoveEligibleDuplicates([group], "single")}
              disabled={executeReclaimMutation.isPending || Boolean(recycleConfigWarning)}
            >
              Move this group
            </Button>
          </div>
        </CardContent>
      </Card>
    );
  }

  function renderGalleryReviewCard(group: DuplicateGroup) {
    const keepCopy = getKeepCopy(group);
    if (!keepCopy) return null;
    const extraCopies = getExtraCopies(group);
    const reviewLabel = getReviewPresentation(currentReviewMark(group), Boolean(group.is_stale)).label;

    return (
      <Card key={group.group_id} className="rounded-[24px] border-border/70 bg-card/95 shadow-sm">
        <CardContent className="space-y-4 p-4">
          <div className="grid gap-3 md:grid-cols-[minmax(0,1fr)_220px]">
            <div className="space-y-2">
              <p className="truncate text-base font-semibold text-foreground">{basename(group.canonical_path)}</p>
              <p className="text-sm text-muted-foreground">
                {reviewLabel}
                {reclaimBridgeBlockedIds.includes(group.group_id) ? " • Eligibility sync needs attention" : ""}
              </p>
              <p className="text-xs text-muted-foreground">
                {extraCopies.length === 1 ? "1 extra copy" : `${extraCopies.length} extra copies`} • {formatBytes(group.estimated_reclaim_bytes ?? 0)}
              </p>
            </div>
            <DuplicateMediaPreview
              src={keepCopy.preview_url ?? (keepCopy.is_image ? keepCopy.media_url ?? keepCopy.thumbnail_url : null)}
              alt={basename(keepCopy.path)}
              isImage={keepCopy.is_image}
              mediaType={keepCopy.media_type}
              className="aspect-[4/3]"
              fit="cover"
            />
          </div>
          {extraCopies.length ? (
            <div className="space-y-2">
              <p className="text-xs uppercase tracking-[0.18em] text-muted-foreground">Extra copies</p>
              <div className="grid grid-cols-3 gap-2">
                {extraCopies.slice(0, 3).map((file) => (
                  <DuplicateMediaPreview
                    key={file.file_instance_id}
                    src={file.preview_url ?? (file.is_image ? file.media_url ?? file.thumbnail_url : null)}
                    alt={basename(file.path)}
                    isImage={file.is_image}
                    mediaType={file.media_type}
                    className="aspect-square"
                    fit="cover"
                  />
                ))}
              </div>
            </div>
          ) : null}
        </CardContent>
      </Card>
    );
  }

  function renderGalleryHoldingCard(item: DuplicateReclaimItem) {
    const group = groupsById[item.content_id];
    const keepCopy = group ? getKeepCopy(group) : null;
    const movedCopy =
      group?.duplicates.find((file) => file.file_instance_id === item.file_instance_id) ??
      group?.duplicates.find((file) => !file.is_canonical) ??
      null;

    return (
      <Card key={item.file_instance_id} className="rounded-[24px] border-border/70 bg-card/95 shadow-sm">
        <CardContent className="space-y-4 p-4">
          <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
            <div className="min-w-0 space-y-1">
              <p className="truncate text-base font-semibold text-foreground">{basename(item.original_path)}</p>
              <p className="text-sm text-muted-foreground">
                Restore is available here. Later retention recycle/purge still happens elsewhere.
              </p>
              {item.expires_at ? <p className="text-xs text-muted-foreground">{formatDaysRemaining(item.expires_at) ?? binStateLabels.daysRemaining}</p> : null}
            </div>
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => void handleRestore(item)}
              disabled={restoreReclaimMutation.isPending}
            >
              Restore
            </Button>
          </div>
          <div className="grid gap-3 md:grid-cols-2">
            <div className="space-y-2">
              <p className="text-xs uppercase tracking-[0.18em] text-muted-foreground">Keep copy</p>
              {keepCopy ? (
                <DuplicateMediaPreview
                  src={keepCopy.preview_url ?? (keepCopy.is_image ? keepCopy.media_url ?? keepCopy.thumbnail_url : null)}
                  alt={basename(keepCopy.path)}
                  isImage={keepCopy.is_image}
                  mediaType={keepCopy.media_type}
                  className="aspect-[4/3]"
                  fit="cover"
                />
              ) : (
                <div className="rounded-[24px] border border-border/70 bg-background/70 p-4 text-sm text-muted-foreground">
                  Keep copy preview is not available for this item.
                </div>
              )}
            </div>
            <div className="space-y-2">
              <p className="text-xs uppercase tracking-[0.18em] text-muted-foreground">Extra copy in holding</p>
              {movedCopy ? (
                <DuplicateMediaPreview
                  src={movedCopy.preview_url ?? (movedCopy.is_image ? movedCopy.media_url ?? movedCopy.thumbnail_url : null)}
                  alt={basename(movedCopy.path)}
                  isImage={movedCopy.is_image}
                  mediaType={movedCopy.media_type}
                  className="aspect-[4/3]"
                  fit="cover"
                />
              ) : (
                <div className="rounded-[24px] border border-border/70 bg-background/70 p-4 text-sm text-muted-foreground">
                  Preview is not available for this held extra copy.
                </div>
              )}
            </div>
          </div>
          <p className="truncate text-xs text-muted-foreground">{item.archive_path}</p>
        </CardContent>
      </Card>
    );
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
          ? "max-w-[120rem] gap-3 px-2 py-3 sm:px-2.5 lg:px-3"
          : "max-w-[120rem] gap-4 px-3 py-4 sm:px-4 lg:px-5",
      )}
    >
      <TopSurfaceHeader
        badge="Duplicate Review"
        title="Work duplicate decisions in focused steps."
        description="Compare duplicates, move eligible extra copies into the configured holding area, and check playback problems without mixing those jobs together."
        icon={Copy}
        density={activeTab === "review" ? "compact" : "default"}
        className={activeTab === "review" ? "rounded-[24px]" : undefined}
        contentClassName={activeTab === "review" ? "px-4 py-3 sm:px-4 lg:px-5 lg:py-4" : undefined}
      />

      {duplicatesQuery.error && (
        <ErrorAlert message={getErrorMessage(duplicatesQuery.error) || "Failed to load duplicate groups"} />
      )}
      {reviewMutation.error && (
        <ErrorAlert message={getErrorMessage(reviewMutation.error) || "Failed to save duplicate review"} />
      )}
      {reclaimMutation.error && (
        <ErrorAlert message={getErrorMessage(reclaimMutation.error) || "Failed to update move eligibility"} />
      )}
      {executeReclaimMutation.error && (
        <ErrorAlert message={getErrorMessage(executeReclaimMutation.error) || "Failed to move duplicates to the Recycle Bin"} />
      )}
      {restoreReclaimMutation.error && (
        <ErrorAlert message={getErrorMessage(restoreReclaimMutation.error) || "Failed to restore duplicate from the Recycle Bin"} />
      )}
      {playbackIssuesQuery.error && activeTab === "playback-issues" ? (
        <ErrorAlert message={getErrorMessage(playbackIssuesQuery.error) || "Failed to load playback issues for duplicates"} />
      ) : null}
      {reclaimBridgeWarning && activeTab === "removal" ? <ErrorAlert message={reclaimBridgeWarning} /> : null}

      {duplicatesQuery.isLoading ? (
        <div className="space-y-4">
          <Skeleton className="h-28 rounded-[24px]" />
          <Skeleton className="h-[42rem] rounded-[28px]" />
        </div>
      ) : !groups.length ? (
        <EmptyState
          icon={<Copy className="h-10 w-10" />}
          title="No duplicate groups to review"
          description="When duplicate files are found, they will appear here for side-by-side review."
        />
      ) : (
        <Tabs value={activeTab} onValueChange={(value) => setActiveTab(value as DuplicatesTab)} className="space-y-4">
          <Card className={cn("rounded-[24px] border-border/70 bg-card/95 shadow-sm", activeTab === "review" && "shadow-none")}>
            <CardContent className={cn("space-y-4 p-4", activeTab === "review" && "space-y-3 p-2.5 sm:p-3")}>
              <TabsList className="flex h-auto w-full flex-wrap justify-start gap-2 rounded-[18px] bg-muted/60 p-1">
                <TabsTrigger value="review">Review duplicates</TabsTrigger>
                <TabsTrigger value="removal">Recycle Bin</TabsTrigger>
                <TabsTrigger value="playback-issues">Playback issues</TabsTrigger>
              </TabsList>

              <TabsContent value="review" className="mt-0">
                <div className="space-y-2">
                  <div className="flex flex-col gap-2 lg:flex-row lg:items-center lg:justify-between">
                    <div>
                      <h2 className="text-lg font-semibold tracking-tight text-foreground">Review duplicates</h2>
                      <p className="mt-1 text-sm text-muted-foreground">
                        Compare one group at a time, decide whether the extra copies look safe to remove, and move on.
                      </p>
                    </div>
                    <p className="text-sm text-muted-foreground">{reviewProgressLabel} in sequence</p>
                  </div>
                </div>
              </TabsContent>

              <TabsContent value="removal" className="mt-0">
                <div className="space-y-2">
                  <h2 className="text-xl font-semibold tracking-tight text-foreground">Recycle Bin</h2>
                  <p className="text-sm text-muted-foreground">
                    Move eligible extra copies into the configured duplicate holding area, restore them if needed, and keep later retention steps separate.
                  </p>
                </div>
              </TabsContent>

              <TabsContent value="playback-issues" className="mt-0">
                <div className="space-y-2">
                  <h2 className="text-xl font-semibold tracking-tight text-foreground">Playback issues</h2>
                  <p className="text-sm text-muted-foreground">
                    Check duplicate-related playback problems here, then continue reviewing duplicates or open Integrity Review for more detail.
                  </p>
                </div>
              </TabsContent>
            </CardContent>
          </Card>

          <TabsContent value="review" className="mt-0">
            <div className="space-y-3">
              <div className="flex items-center justify-between gap-3">
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={() => setIsReviewQueueOpen((current) => !current)}
                  aria-expanded={isReviewQueueOpen}
                  aria-controls="review-group-navigation"
                >
                  {isReviewQueueOpen ? <PanelLeftClose className="h-4 w-4" /> : <PanelLeft className="h-4 w-4" />}
                  {isReviewQueueOpen ? "Hide group navigation" : "Show group navigation"}
                </Button>
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

              <div className={cn("grid gap-3", isReviewQueueOpen ? "xl:grid-cols-[240px_minmax(0,1fr)]" : "grid-cols-1")}>
                {isReviewQueueOpen ? (
                  <Card
                    id="review-group-navigation"
                    className="rounded-[20px] border-border/70 bg-card/95 shadow-sm"
                    data-testid="review-group-navigation"
                  >
                    <CardContent className="space-y-3 p-3">
                      <div className="space-y-1">
                        <p className="text-sm font-semibold text-foreground">Group navigation</p>
                        <p className="text-sm text-muted-foreground">Jump to a different duplicate group without interrupting the main review loop.</p>
                      </div>

                      <ScrollArea className="h-[40rem] pr-2">
                        <div className="space-y-2">
                          {filteredGroups.map((group, index) => {
                            const presentation = getReviewPresentation(currentReviewMark(group), Boolean(group.is_stale));
                            return (
                              <DuplicateQueueItem
                                key={group.group_id}
                                index={index}
                                active={selected?.group_id === group.group_id}
                                group={group}
                                markLabel={presentation.label}
                                onSelect={() => setSelectedId(group.group_id)}
                              />
                            );
                          })}
                        </div>
                      </ScrollArea>
                    </CardContent>
                  </Card>
                ) : (
                  <div data-testid="review-group-navigation-hidden" className="hidden" />
                )}

                <Card className="rounded-[26px] border-border/70 bg-card/95 shadow-sm">
                  <CardContent className="space-y-4 p-2.5 sm:p-3">
                    {selected && selectedCanonical ? (
                      <>
                        <div className="space-y-3">
                          <div className="flex flex-col gap-2 lg:flex-row lg:items-start lg:justify-between">
                            <div className="min-w-0 space-y-1.5">
                              <p
                                className="truncate text-xl font-semibold tracking-tight text-foreground"
                                title={basename(selected.canonical_path)}
                                data-testid="review-group-title"
                              >
                                {basename(selected.canonical_path)}
                              </p>
                              <p className="text-sm text-muted-foreground">{reviewMetaLine.replace("matching copies", "extra copies").replace("matching copy", "extra copy")}</p>
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
                            progressLabel={reviewProgressLabel}
                          />
                          {(selected.integrity_issue_count ?? 0) > 0 ? (
                            <div className="flex flex-col gap-2 rounded-[18px] border border-caution/30 bg-caution/10 px-3 py-2.5 lg:flex-row lg:items-center lg:justify-between">
                              <div className="min-w-0">
                                <p className="text-sm text-muted-foreground">
                                  {selected.integrity_issue_count} {binStateLabels.playbackIssue.toLowerCase()}{selected.integrity_issue_count === 1 ? "" : "s"} may affect this decision. Open Playback issues if something needs checking.
                                </p>
                              </div>
                              <div className="flex gap-2">
                                <Button type="button" variant="outline" size="sm" onClick={() => setActiveTab("playback-issues")}>
                                  Open Playback issues
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

                        <div className="grid gap-2.5 xl:grid-cols-[minmax(0,1.65fr)_minmax(0,1.05fr)]">
                          <DuplicateFocusCard
                            badge="Keep copy"
                            description="Use this copy as the point of comparison for the current review."
                            emphasis="success"
                            file={selectedCanonical}
                            previewClassName="h-[26rem] sm:h-[34rem] lg:h-[44rem]"
                            previewFit="contain"
                            previewTestId="primary-comparison-preview"
                            titleTestId="primary-comparison-title"
                          />

                          {selectedDuplicate ? (
                            <DuplicateFocusCard
                              badge="Extra copy"
                              description={`Selected extra copy ${selectedDuplicates.findIndex((file) => file.file_instance_id === selectedDuplicate.file_instance_id) + 1} updates this pane immediately.`}
                              emphasis="info"
                              file={selectedDuplicate}
                              title={`Extra copy: ${basename(selectedDuplicate.path)}`}
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
                                  <p className="text-sm text-muted-foreground">There are no other copies to compare in this group.</p>
                                </div>
                              </CardContent>
                            </Card>
                          )}
                        </div>

                        {selectedDuplicates.length ? (
                          <section className="space-y-2.5">
                            <div className="flex items-center justify-between gap-3">
                              <h3 className="text-xs font-semibold uppercase tracking-[0.18em] text-muted-foreground">
                                Select the extra copy to compare
                              </h3>
                              {selectedDuplicate ? (
                                <p
                                  className="max-w-[28rem] truncate text-xs text-muted-foreground"
                                  title={basename(selectedDuplicate.path)}
                                  data-testid="active-duplicate-caption"
                                >
                                  Comparing: {basename(selectedDuplicate.path)}
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
                                Paths and reference IDs for moments when side-by-side review is not enough.
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
                                Keep copy path
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
                                      label={file.is_canonical ? "Keep copy" : "Extra copy"}
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
                      description="Choose a duplicate group from the current filter to compare the keep copy against an extra copy."
                    />
                  )}
                </CardContent>
              </Card>
            </div>
            </div>
          </TabsContent>

          <TabsContent value="removal" className="mt-0">
            <div className="space-y-4">
              <div className="grid gap-3 md:grid-cols-3">
                <Card className="rounded-[22px] border-border/70 bg-card/95 shadow-sm">
                  <CardContent className="space-y-1 p-4">
                    <p className="text-xs uppercase tracking-[0.18em] text-muted-foreground">Ready to move</p>
                    <p className="text-2xl font-semibold text-foreground">{readyGroups.length}</p>
                    <p className="text-sm text-muted-foreground">
                      {readyExtraCopyCount} extra copies are in groups currently marked Looks right.
                    </p>
                  </CardContent>
                </Card>
                <Card className="rounded-[22px] border-border/70 bg-card/95 shadow-sm">
                  <CardContent className="space-y-1 p-4">
                    <p className="text-xs uppercase tracking-[0.18em] text-muted-foreground">Space you could free up</p>
                    <p className="text-2xl font-semibold text-foreground">{formatBytes(readyEstimatedBytes)}</p>
                    <p className="text-sm text-muted-foreground">Estimated space if the ready extra copies move out of the main library.</p>
                  </CardContent>
                </Card>
                <Card className="rounded-[22px] border-border/70 bg-card/95 shadow-sm">
                  <CardContent className="space-y-1 p-4">
                    <p className="text-xs uppercase tracking-[0.18em] text-muted-foreground">In the holding area</p>
                    <p className="text-2xl font-semibold text-foreground">{archivedItems.length}</p>
                    <p className="text-sm text-muted-foreground">These files can be restored from the holding area before later retention steps happen elsewhere.</p>
                  </CardContent>
                </Card>
              </div>

              <Card className="rounded-[24px] border-border/70 bg-card/95 shadow-sm">
                <CardContent className="flex flex-col gap-3 p-4 lg:flex-row lg:items-center lg:justify-between">
                  <div>
                    <p className="text-sm font-semibold text-foreground">View</p>
                    <p className="text-sm text-muted-foreground">
                      Gallery keeps the media visible. List keeps the same compact operational scan.
                    </p>
                  </div>
                  <ToggleGroup
                    type="single"
                    value={recycleBinViewMode}
                    onValueChange={(value) => {
                      if (value === "gallery" || value === "list") setRecycleBinViewMode(value);
                    }}
                    variant="outline"
                    size="sm"
                    className="justify-start"
                    data-testid="recycle-bin-view-toggle"
                  >
                    <ToggleGroupItem value="gallery" aria-label="Gallery view" data-testid="recycle-bin-view-gallery">
                      <LayoutGrid className="h-4 w-4" />
                      Gallery
                    </ToggleGroupItem>
                    <ToggleGroupItem value="list" aria-label="List view" data-testid="recycle-bin-view-list">
                      <List className="h-4 w-4" />
                      List
                    </ToggleGroupItem>
                  </ToggleGroup>
                </CardContent>
              </Card>

              <Card className="rounded-[24px] border-border/70 bg-card/95 shadow-sm">
                <CardContent className="space-y-4 p-4">
                  {recycleBinFeedback ? (
                    <div
                      className={cn(
                        "rounded-[18px] border px-4 py-3 text-sm",
                        recycleBinFeedback.tone === "success"
                          ? "border-success/30 bg-success/10 text-foreground"
                          : "border-caution/30 bg-caution/10 text-foreground",
                      )}
                    >
                      {recycleBinFeedback.message}
                    </div>
                  ) : null}
                  <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
                    <div>
                      <p className="text-sm font-semibold text-foreground">Ready to move</p>
                      <p className="text-sm text-muted-foreground">
                        Only groups marked “Looks right” can be moved from this page. The keep copy stays in place.
                      </p>
                    </div>
                    <div className="flex flex-wrap gap-2">
                      <Button
                        type="button"
                        variant="outline"
                        onClick={() => void handleMoveEligibleDuplicates(readyGroups, "all")}
                        disabled={executeReclaimMutation.isPending || readyGroups.length === 0 || Boolean(recycleConfigWarning)}
                      >
                        Move all eligible groups
                      </Button>
                    </div>
                  </div>
                  <div className="rounded-[18px] border border-border/70 bg-background/70 px-4 py-3 text-sm text-muted-foreground">
                    <p>Only extra copies move from this page. They go into the configured duplicate holding area, and restore is supported from that stage.</p>
                    {recycleConfigWarning ? (
                      <p className="mt-2 text-caution">{recycleConfigWarning}</p>
                    ) : (
                      <p className="mt-2">
                        Holding area: <span className="font-mono text-foreground">{archiveRoot}</span>. Current holding window: {archiveRetentionDays} day{archiveRetentionDays === 1 ? "" : "s"}. Later recycle/purge remains a separate manual workflow.
                      </p>
                    )}
                  </div>
                  {!readyGroups.length ? (
                    <p className="text-sm text-muted-foreground">No eligible extra copies are left to move from the main library.</p>
                  ) : null}

                  {selectedReadyGroups.length ? (
                    <div
                      data-testid="recycle-bin-bulk-action-bar"
                      className="flex flex-col gap-3 rounded-[20px] border border-primary/20 bg-primary/5 px-4 py-3 lg:flex-row lg:items-center lg:justify-between"
                    >
                      <div className="space-y-1">
                        <p className="text-sm font-semibold text-foreground">
                          {selectedReadyGroups.length} selected group{selectedReadyGroups.length === 1 ? "" : "s"}
                        </p>
                        <p className="text-sm text-muted-foreground">
                          Move only the extra copies from the selected groups into the configured holding area. Keep copies stay in place.
                        </p>
                      </div>
                      <div className="flex flex-wrap gap-2">
                        <Button
                          type="button"
                          onClick={() => void handleMoveEligibleDuplicates(selectedReadyGroups, "selected")}
                          disabled={executeReclaimMutation.isPending || Boolean(recycleConfigWarning)}
                        >
                          Move selected groups
                        </Button>
                        <Button type="button" variant="outline" onClick={clearReadyGroupSelection}>
                          Clear selection
                        </Button>
                      </div>
                    </div>
                  ) : null}

                  {readyGroups.length ? (
                    recycleBinViewMode === "gallery" ? (
                      <div
                        data-testid="recycle-bin-ready-gallery"
                        className="grid gap-4 xl:grid-cols-2"
                      >
                        {readyGroups.map((group) => renderGalleryReadyCard(group))}
                      </div>
                    ) : (
                      <div data-testid="recycle-bin-ready-list" className="space-y-3">
                        {readyGroups.map((group) => {
                          const isSelected = selectedReadyGroupIds.includes(group.group_id);
                          return (
                            <div
                              key={group.group_id}
                              className={cn(
                                "flex flex-col gap-3 rounded-[22px] border border-border/70 bg-background/70 p-4 lg:flex-row lg:items-center lg:justify-between",
                                isSelected && "border-primary/45 ring-2 ring-primary/15",
                              )}
                            >
                              <div className="flex min-w-0 items-start gap-3">
                                <Checkbox
                                  checked={isSelected}
                                  aria-label={`Select group ${basename(group.canonical_path)}`}
                                  onCheckedChange={(checked) => toggleReadyGroupSelection(group.group_id, Boolean(checked))}
                                />
                                <div className="min-w-0 space-y-2">
                                  <div className="flex flex-wrap items-center gap-2">
                                    <StatusBadge label={binStateLabels.ready} severity="success" />
                                    <StatusBadge
                                      label={`${group.reclaimable_file_count ?? 0} extra cop${(group.reclaimable_file_count ?? 0) === 1 ? "y" : "ies"}`}
                                      severity="neutral"
                                    />
                                    <StatusBadge label={formatBytes(group.estimated_reclaim_bytes ?? 0)} severity="info" />
                                  </div>
                                  <p className="truncate text-sm font-semibold text-foreground">{basename(group.canonical_path)}</p>
                                  <p className="text-xs text-muted-foreground">Review state: Looks right</p>
                                </div>
                              </div>
                              <Button
                                type="button"
                                variant="outline"
                                size="sm"
                                onClick={() => void handleMoveEligibleDuplicates([group], "single")}
                                disabled={executeReclaimMutation.isPending || Boolean(recycleConfigWarning)}
                              >
                                Move this group
                              </Button>
                            </div>
                          );
                        })}
                      </div>
                    )
                  ) : null}
                </CardContent>
              </Card>

              <Card className="rounded-[24px] border-border/70 bg-card/95 shadow-sm">
                <CardContent className="space-y-4 p-4">
                  <div>
                    <p className="text-sm font-semibold text-foreground">Needs review before moving to bin</p>
                    <p className="text-sm text-muted-foreground">
                      Groups must be reviewed again before they can re-enter Ready to move. Restored groups stay out until the operator marks Looks right again.
                    </p>
                  </div>

                  {!removalReviewGroups.length ? (
                    <p className="text-sm text-muted-foreground">No additional duplicate groups are waiting for review.</p>
                  ) : recycleBinViewMode === "gallery" ? (
                    <div data-testid="recycle-bin-review-gallery" className="grid gap-4 xl:grid-cols-2">
                      {removalReviewGroups.map((group) => renderGalleryReviewCard(group))}
                    </div>
                  ) : (
                    <div className="space-y-3">
                      {removalReviewGroups.map((group) => (
                        <div
                          key={group.group_id}
                          className="flex flex-col gap-3 rounded-[22px] border border-border/70 bg-background/70 p-4 lg:flex-row lg:items-center lg:justify-between"
                        >
                          <div className="min-w-0 space-y-2">
                            <div className="flex flex-wrap items-center gap-2">
                              <StatusBadge label={binStateLabels.needsReview} severity="caution" />
                              <StatusBadge
                                label={`${group.reclaimable_file_count ?? 0} extra cop${(group.reclaimable_file_count ?? 0) === 1 ? "y" : "ies"}`}
                                severity="neutral"
                              />
                              <StatusBadge label={formatBytes(group.estimated_reclaim_bytes ?? 0)} severity="info" />
                            </div>
                            <p className="truncate text-sm font-semibold text-foreground">{basename(group.canonical_path)}</p>
                            <p className="text-xs text-muted-foreground">
                              Review state: {getReviewPresentation(currentReviewMark(group), Boolean(group.is_stale)).label}
                              {reclaimBridgeBlockedIds.includes(group.group_id)
                                ? " • Eligibility sync needs attention before this group can move."
                                : ""}
                            </p>
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
                    <p className="text-sm font-semibold text-foreground">In the holding area</p>
                    <p className="text-sm text-muted-foreground">
                      These extra copies have already moved into the configured holding area. Restore is available here. Later retention recycle/purge happens elsewhere.
                    </p>
                  </div>

                  {!archivedItems.length ? (
                    <p className="text-sm text-muted-foreground">No duplicate files are in the holding area right now.</p>
                  ) : recycleBinViewMode === "gallery" ? (
                    <div data-testid="recycle-bin-holding-gallery" className="grid gap-4 xl:grid-cols-2">
                      {archivedItems.map((item) => renderGalleryHoldingCard(item))}
                    </div>
                  ) : (
                    <div className="space-y-3">
                      {archivedItems.map((item) => (
                        <div
                          key={item.file_instance_id}
                          className="flex flex-col gap-3 rounded-[22px] border border-border/70 bg-background/70 p-4 lg:flex-row lg:items-center lg:justify-between"
                        >
                          <div className="min-w-0 space-y-2">
                            <div className="flex flex-wrap items-center gap-2">
                              <StatusBadge label={binStateLabels.inBin} severity="neutral" />
                              {item.expires_at ? <StatusBadge label={formatDaysRemaining(item.expires_at) ?? binStateLabels.daysRemaining} severity="info" /> : null}
                            </div>
                            <p className="truncate text-sm font-semibold text-foreground">{basename(item.original_path)}</p>
                            <p className="truncate text-xs text-muted-foreground">{item.archive_path}</p>
                          </div>
                          <Button
                            type="button"
                            variant="outline"
                            onClick={() => void handleRestore(item)}
                            disabled={restoreReclaimMutation.isPending}
                          >
                            Restore
                          </Button>
                        </div>
                      ))}
                    </div>
                  )}
                  {restoredItems.length ? (
                    <div className="rounded-[18px] border border-border/70 bg-background/70 px-4 py-3 text-sm text-muted-foreground">
                      {restoredItems.length} restored file{restoredItems.length === 1 ? "" : "s"} already left the holding area. Those groups stay out of Ready to move until they are reviewed again.
                    </div>
                  ) : null}
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
                      <p className="text-sm font-semibold text-foreground">Playback issues in duplicate groups</p>
                      <p className="text-sm text-muted-foreground">
                        This view only shows duplicate groups where a file has a playback issue or needs checking.
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
                    <StatusBadge label={`${duplicatePlaybackGroups.length} group${duplicatePlaybackGroups.length === 1 ? "" : "s"} with playback issues`} severity="neutral" />
                    <StatusBadge
                      label={`${duplicatePlaybackGroups.filter((entry) => entry.brokenCount > 0).length} item${duplicatePlaybackGroups.filter((entry) => entry.brokenCount > 0).length === 1 ? "" : "s"} won't play`}
                      severity="destructive"
                    />
                    <StatusBadge
                      label={`${duplicatePlaybackGroups.filter((entry) => entry.brokenCount === 0 && entry.suspectCount > 0).length} item${duplicatePlaybackGroups.filter((entry) => entry.brokenCount === 0 && entry.suspectCount > 0).length === 1 ? "" : "s"} need checking`}
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
                  title="No playback issues in duplicate groups"
                  description="Integrity Review can still show unrelated file-health findings, but none are attached to the current duplicate groups."
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
                                  label={hasBlockingCue ? "Playback issue" : "Needs checking"}
                                  severity={hasBlockingCue ? "destructive" : "caution"}
                                />
                                {brokenCount > 0 ? <StatusBadge label={`${brokenCount} ${binStateLabels.wontPlay.toLowerCase()}`} severity="destructive" /> : null}
                                {suspectCount > 0 ? (
                                  <StatusBadge
                                    label={`${suspectCount} item${suspectCount === 1 ? "" : "s"} ${binStateLabels.needsChecking.toLowerCase()}`}
                                    severity="caution"
                                  />
                                ) : null}
                              </div>
                              <p className="truncate text-lg font-semibold text-foreground">{basename(group.canonical_path)}</p>
                              <p className="text-sm text-muted-foreground">
                                {hasBlockingCue
                                  ? "A copy in this group may not play. You can keep reviewing here, but this does not change the current removal rules."
                                  : "A copy in this group needs checking. Deeper diagnosis still belongs in Integrity Review."}
                              </p>
                            </div>
                            <div className="flex gap-2">
                              <Button
                                type="button"
                                variant="outline"
                                onClick={() => {
                                  setReviewFilter("all");
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
                                            label={getPlaybackStatusLabel(issue)}
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
                                    ? "Review this playback issue before moving extra copies to the Recycle Bin."
                                    : "You can continue reviewing duplicates here, but keep this item in mind before moving anything to the Recycle Bin."}
                                </p>
                                <p className="mt-2 text-xs text-muted-foreground">
                                  This note only helps explain what you are seeing here. It does not change the current product behavior.
                                </p>
                              </div>
                              <div className="mt-3 flex items-start gap-2 rounded-2xl border border-border/70 bg-card/80 p-3">
                                <AlertTriangle className="mt-0.5 h-4 w-4 text-caution" />
                                <p className="text-xs text-muted-foreground">
                                  Integrity Review remains the place for deeper diagnosis, file-level detail, and playback health work outside duplicate review.
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
