import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, ChevronLeft, ChevronRight, Copy, ExternalLink, LayoutGrid, List, PanelLeft, PanelLeftClose, ShieldAlert } from "lucide-react";
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
  getDuplicateBinPolicy,
  getDuplicateBinItems,
  getDuplicates,
  getIntegrityIssues,
  moveDuplicatesToBin,
  restoreDuplicatesFromBin,
  setDuplicateReclaim,
  setDuplicateReview,
} from "@/lib/api/endpoints";
import { queryKeys } from "@/lib/api/queryKeys";
import { queryOptions } from "@/lib/api/queryOptions";
import { cn } from "@/lib/utils";
import type {
  DuplicateFile,
  DuplicateGroup,
  DuplicateRecommendation,
  DuplicateReclaimItem,
  IntegrityIssue,
  PaginatedResponse,
} from "@/types";

type ReviewMark = "looks_right" | "needs_review" | "not_sure";
type ReviewFilter = "all" | "unreviewed" | "restored" | ReviewMark;
type DuplicatesTab = "review" | "ready-for-bin" | "recycle-bin" | "playback-issues";
type ReclaimSyncStatus = "UNREVIEWED" | "REVIEWED_SAFE_TO_RECLAIM";
type FeedbackTone = "success" | "warning";
type DuplicateWorkspaceViewMode = "focus" | "gallery" | "list";

type DuplicateBinItem = DuplicateReclaimItem;

interface RecycleBinDisplayItem extends DuplicateBinItem {
  recycle_bin_state: "restorable" | "expired";
  restore_allowed: boolean;
}

interface MutationSummary {
  applied_count?: number;
  skipped_count?: number;
  moves_count?: number;
}

interface DuplicateBinOperationDiagnostics {
  requested_group_count?: number;
  planned_action_count?: number;
  applied_count?: number;
  skipped_count?: number;
  result_type?: "zero_planned" | "planned_skipped" | "applied";
  group_results?: Array<{
    content_id: string;
    reason?: string | null;
  }>;
  reclaim_root?: string;
}

interface RecycleBinFeedback {
  tone: FeedbackTone;
  message: string;
}

interface DuplicateBinPolicy {
  current_move_root: string;
  current_retention_days: number;
  target_recycle_bin_root: string;
  implementation: string;
}

const reviewOptions: Array<{ value: ReviewFilter; label: string }> = [
  { value: "all", label: "All" },
  { value: "unreviewed", label: "Still to review" },
  { value: "restored", label: "Restored" },
  { value: "looks_right", label: "Looks right" },
  { value: "needs_review", label: "Needs review" },
  { value: "not_sure", label: "Not sure" },
];

const binStateLabels = {
  ready: "Ready for Bin",
  inBin: "In Recycle Bin",
  needsReview: "Needs review",
  safeToRemove: "Safe to remove",
  restore: "Restore from Recycle Bin",
  moveToBin: "Move to Recycle Bin",
  daysRemaining: "Days remaining",
  expired: "Expired",
  restoreWindowEnded: "Restore window ended",
  approachingExpiry: "Approaching permanent deletion",
  needsChecking: "Needs checking",
  playbackIssue: "Playback issue",
  wontPlay: "Won't play",
} as const;

const recommendationStateLabels: Record<DuplicateRecommendation["state"], string> = {
  SAFE_TO_MOVE_EXTRAS: "Safe to move extra copies",
  REVIEW_REQUIRED: "Review required",
  DO_NOT_MOVE: "Do not move",
  ALREADY_IN_BIN: "Already in Recycle Bin",
  EXPIRED_IN_BIN: "Restore window ended",
};

const recommendationReasonLabels: Record<string, string> = {
  GROUP_ALREADY_IN_BIN: "Already in the Recycle Bin",
  BIN_RESTORE_EXPIRED: "Restore window expired",
  CANONICAL_MAPPING_MISSING: "Keep copy mapping missing",
  KEEP_COPY_UNHEALTHY: "Keep copy unhealthy",
  KEEP_COPY_SUSPECT: "Keep copy suspect",
  KEEP_COPY_UNKNOWN: "Keep copy health unknown",
  EXTRA_COPIES_UNHEALTHY_ONLY: "Extra copies have playback issues",
  SAFE_TO_MOVE_REVIEWED_DUPLICATES: "Reviewed and ready",
  MIXED_EXTRA_HEALTH: "Mixed extra-copy health",
  EXTRA_HEALTH_UNKNOWN: "Extra-copy health unknown",
  REVIEW_REQUIRED_BY_OPERATOR_STATE: "Operator review not approved",
  REVIEW_STALE: "Review is stale",
  INTEGRITY_EVIDENCE_STALE: "Integrity evidence stale",
  NO_ACTIVE_EXTRAS: "No active extra copies",
};

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

function parseTimestamp(value: string | null | undefined): number | null {
  if (!value) return null;
  const parsed = new Date(value).getTime();
  return Number.isFinite(parsed) ? parsed : null;
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

function getRecommendationPresentation(recommendation: DuplicateRecommendation | null | undefined) {
  if (!recommendation) {
    return {
      label: "Recommendation unavailable",
      severity: "neutral" as const,
    };
  }
  switch (recommendation.state) {
    case "SAFE_TO_MOVE_EXTRAS":
      return { label: recommendationStateLabels[recommendation.state], severity: "success" as const };
    case "REVIEW_REQUIRED":
      return { label: recommendationStateLabels[recommendation.state], severity: "caution" as const };
    case "DO_NOT_MOVE":
      return { label: recommendationStateLabels[recommendation.state], severity: "destructive" as const };
    case "ALREADY_IN_BIN":
      return { label: recommendationStateLabels[recommendation.state], severity: "info" as const };
    case "EXPIRED_IN_BIN":
      return { label: recommendationStateLabels[recommendation.state], severity: "caution" as const };
  }
}

function currentReviewMark(group: DuplicateGroup): ReviewMark | undefined {
  if (group.is_stale) return undefined;
  return group.review_status ?? undefined;
}

function getDuplicateRecommendation(group: DuplicateGroup): DuplicateRecommendation | null {
  return group.duplicate_recommendation ?? null;
}

function isReadyForBinRecommendation(group: DuplicateGroup): boolean {
  return getDuplicateRecommendation(group)?.state === "SAFE_TO_MOVE_EXTRAS";
}

function getRecommendationReasonLabels(recommendation: DuplicateRecommendation | null | undefined): string[] {
  if (!recommendation) return [];
  return recommendation.reason_codes.map((code) => recommendationReasonLabels[code] ?? code);
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
  if (value === "ready-for-bin" || value === "recycle-bin" || value === "playback-issues") return value;
  if (value === "removal" || value === "process") return "ready-for-bin";
  return "review";
}

function hasRestoreWindowEnded(expiresAt: string | null | undefined): boolean {
  if (!expiresAt) return false;
  const expiresAtMs = new Date(expiresAt).getTime();
  return Number.isFinite(expiresAtMs) && expiresAtMs < Date.now();
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

function getDuplicateBinOperationDiagnostics(payload: unknown): DuplicateBinOperationDiagnostics {
  if (!payload || typeof payload !== "object") return {};
  const diagnostics = (payload as { diagnostics?: DuplicateBinOperationDiagnostics }).diagnostics;
  return diagnostics && typeof diagnostics === "object" ? diagnostics : {};
}

function isPendingRemovalStatus(status: DuplicateGroup["reclaim_status"] | undefined | null) {
  return status === "ARCHIVED" || status === "RESTORED" || status === "SCHEDULED_FOR_DELETE";
}

function deriveActionableReadyGroups(groups: DuplicateGroup[]) {
  // Ready for Bin is a UI workflow bucket over server-derived recommendation state only.
  return groups.filter((group) => isReadyForBinRecommendation(group));
}

function getKeepCopy(group: DuplicateGroup): DuplicateFile | null {
  return group.duplicates.find((file) => file.is_canonical) ?? group.duplicates[0] ?? null;
}

function getExtraCopies(group: DuplicateGroup): DuplicateFile[] {
  return group.duplicates.filter((file) => !file.is_canonical);
}

function renderRecommendationDetails(recommendation: DuplicateRecommendation | null | undefined) {
  if (!recommendation) return null;
  const reasonLabels = getRecommendationReasonLabels(recommendation);
  return (
    <div className="space-y-2">
      <p className="text-sm text-muted-foreground">{recommendation.operator_explanation}</p>
      <div className="flex flex-wrap items-center gap-2">
        {reasonLabels.map((label) => (
          <StatusBadge key={label} label={label} severity="neutral" />
        ))}
      </div>
    </div>
  );
}

function getGalleryActionSummary(groupCount: number, appliedCount: number) {
  const groupLabel = `${groupCount} group${groupCount === 1 ? "" : "s"}`;
  const fileLabel = `${appliedCount} duplicate file${appliedCount === 1 ? "" : "s"}`;
  return `${fileLabel} moved from ${groupLabel} into the Recycle Bin. The keep copy stayed in place.`;
}

function getGalleryNoOpSummary(
  scope: "selected" | "all" | "single",
  diagnostics: DuplicateBinOperationDiagnostics = {},
) {
  if (diagnostics.result_type === "planned_skipped") {
    if (scope === "selected") {
      return "The selected groups were planned for move, but the duplicate files were skipped during apply. The list has been refreshed.";
    }
    if (scope === "single") {
      return "This group was planned for move, but its duplicate files were skipped during apply. The list has been refreshed.";
    }
    return "Eligible groups were planned for move, but their duplicate files were skipped during apply. The list has been refreshed.";
  }

  const missingCanonical = diagnostics.group_results?.some(
    (groupResult) => groupResult.reason === "missing_canonical_file_content_mapping",
  );
  if (missingCanonical) {
    if (scope === "single") {
      return "No files were moved from this group because the planner could not confirm a keep-copy mapping. The list has been refreshed.";
    }
    if (scope === "selected") {
      return "No files were moved from the selected groups because one or more groups no longer had a planner-confirmed keep-copy mapping. The list has been refreshed.";
    }
    return "No files were moved because one or more eligible groups no longer had a planner-confirmed keep-copy mapping. The list has been refreshed.";
  }

  if (scope === "selected") {
    return "No files were moved from the selected groups because no duplicate files were eligible to plan for this move. The list has been refreshed.";
  }
  if (scope === "single") {
    return "No files were moved from this group because no duplicate files were eligible to plan for this move. The list has been refreshed.";
  }
  return "No files were moved because no duplicate files were eligible to plan for this move. The list has been refreshed.";
}

export default function DuplicatesPage() {
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [selectedDuplicateId, setSelectedDuplicateId] = useState<string | null>(null);
  const [reviewFilter, setReviewFilter] = useState<ReviewFilter>("unreviewed");
  const [isReviewQueueOpen, setIsReviewQueueOpen] = useState(false);
  const [readyForBinViewMode, setReadyForBinViewMode] = useState<DuplicateWorkspaceViewMode>("focus");
  const [recycleBinViewMode, setRecycleBinViewMode] = useState<DuplicateWorkspaceViewMode>("gallery");
  const [selectedReadyGroupIds, setSelectedReadyGroupIds] = useState<string[]>([]);
  const [focusedReadyGroupId, setFocusedReadyGroupId] = useState<string | null>(null);
  const [focusedArchivedItemId, setFocusedArchivedItemId] = useState<string | null>(null);
  const [recycleBinPage, setRecycleBinPage] = useState(1);
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
  const duplicateBinPolicyQuery = useQuery({
    queryKey: queryKeys.duplicateBinPolicy,
    queryFn: async () => (await getDuplicateBinPolicy()).data,
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

  const duplicateBinItemsQuery = useQuery({
    queryKey: queryKeys.duplicateBinItems(recycleBinPage, 50),
    queryFn: async () => (await getDuplicateBinItems({ page: recycleBinPage, limit: 50 })).data,
  });

  const playbackIssuesQuery = useQuery({
    queryKey: queryKeys.integrityIssues({ page: 1, limit: 200 }),
    queryFn: async () => (await getIntegrityIssues({ page: 1, limit: 200 })).data,
    enabled: activeTab === "playback-issues",
  });

  const moveToBinMutation = useMutation({
    mutationFn: (payload: { content_ids: string[]; retention_days: number }) => moveDuplicatesToBin(payload),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.duplicates });
      void queryClient.invalidateQueries({ queryKey: queryKeys.duplicateBinItemsRoot });
    },
  });

  const restoreFromBinMutation = useMutation({
    mutationFn: (fileInstanceId: string) => restoreDuplicatesFromBin({ file_instance_ids: [fileInstanceId] }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.duplicates });
      void queryClient.invalidateQueries({ queryKey: queryKeys.duplicateBinItemsRoot });
    },
  });

  const groups = (duplicatesQuery.data as DuplicateGroup[] | undefined) ?? [];
  const duplicateBinPolicy = (duplicateBinPolicyQuery.data as DuplicateBinPolicy | undefined) ?? null;
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

  const duplicateBinItemsPage = (duplicateBinItemsQuery.data as PaginatedResponse<DuplicateBinItem> | undefined) ?? undefined;
  const duplicateBinItems = duplicateBinItemsPage?.items ?? [];
  const recycleBinTotalCount = duplicateBinItemsPage?.total ?? duplicateBinItems.length;
  const recycleBinTotalPages = duplicateBinItemsPage?.total_pages ?? 1;
  const recycleBinItems = duplicateBinItems
    .filter((item) => item.item_status === "ARCHIVED")
    .map<RecycleBinDisplayItem>((item) => {
      const restoreWindowEnded = hasRestoreWindowEnded(item.expires_at);
      return {
        ...item,
        recycle_bin_state: restoreWindowEnded ? "expired" : "restorable",
        restore_allowed: !restoreWindowEnded,
      };
    });
  const restorableRecycleBinItems = recycleBinItems.filter((item) => item.restore_allowed);
  const expiredRecycleBinItems = recycleBinItems.filter((item) => !item.restore_allowed);
  const recycleBinLifecycleGroupIds = useMemo(
    () =>
      new Set(
        sortedGroups
          .filter((group) => group.reclaim_status === "ARCHIVED" || group.reclaim_status === "SCHEDULED_FOR_DELETE")
          .map((group) => group.group_id),
      ),
    [sortedGroups],
  );
  const restoredItems = duplicateBinItems.filter((item) => item.item_status === "RESTORED");
  const restoredItemsByGroupId = useMemo(
    () =>
      restoredItems.reduce<Record<string, DuplicateBinItem[]>>((acc, item) => {
        if (!acc[item.content_id]) acc[item.content_id] = [];
        acc[item.content_id].push(item);
        return acc;
      }, {}),
    [restoredItems],
  );
  const groupsById = useMemo(
    () =>
      sortedGroups.reduce<Record<string, DuplicateGroup>>((acc, group) => {
        acc[group.group_id] = group;
        return acc;
      }, {}),
    [sortedGroups],
  );
  const restoredReviewGroupIds = useMemo(() => {
    return new Set(
      sortedGroups
        .filter((group) => {
          const restoredGroupItems = restoredItemsByGroupId[group.group_id] ?? [];
          if (!restoredGroupItems.length) return false;

          const reviewedAtMs = parseTimestamp(group.reviewed_at);
          return restoredGroupItems.some((item) => {
            const restoredAtMs = parseTimestamp(item.restored_at);
            if (restoredAtMs === null) return reviewedAtMs === null;
            if (reviewedAtMs === null) return true;
            return restoredAtMs > reviewedAtMs;
          });
        })
        .map((group) => group.group_id),
    );
  }, [restoredItemsByGroupId, sortedGroups]);
  const filteredGroups = useMemo(
    () =>
      sortedGroups.filter((group) => {
        if (reviewFilter === "all") return true;
        if (reviewFilter === "restored") return restoredReviewGroupIds.has(group.group_id);
        const mark = currentReviewMark(group);
        if (reviewFilter === "unreviewed") return !mark;
        return mark === reviewFilter;
      }),
    [reviewFilter, restoredReviewGroupIds, sortedGroups],
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
  const readyGroups = deriveActionableReadyGroups(sortedGroups);
  const readyExtraCopyCount = readyGroups.reduce((sum, group) => sum + (group.reclaimable_file_count ?? 0), 0);
  const readyEstimatedBytes = readyGroups.reduce((sum, group) => sum + (group.estimated_reclaim_bytes ?? 0), 0);
  const readyGroupIds = new Set(readyGroups.map((group) => group.group_id));
  const selectedReadyGroups = readyGroups.filter((group) => selectedReadyGroupIds.includes(group.group_id));
  const focusedReadyGroup = readyGroups.find((group) => group.group_id === focusedReadyGroupId) ?? readyGroups[0] ?? null;
  const focusedReadyIndex = focusedReadyGroup
    ? readyGroups.findIndex((group) => group.group_id === focusedReadyGroup.group_id)
    : -1;
  const focusedArchivedItem =
    recycleBinItems.find((item) => item.file_instance_id === focusedArchivedItemId) ?? recycleBinItems[0] ?? null;
  const focusedArchivedIndex = focusedArchivedItem
    ? recycleBinItems.findIndex((item) => item.file_instance_id === focusedArchivedItem.file_instance_id)
    : -1;
  const archiveRoot = duplicateBinPolicy?.current_move_root?.trim() ?? "";
  const archiveRetentionDays = duplicateBinPolicy?.current_retention_days ?? null;
  const recycleConfigWarning =
    duplicateBinPolicyQuery.error || !archiveRoot || !archiveRetentionDays
      ? "Recycle Bin details are unavailable right now. The app cannot confirm the configured Recycle Bin location or retention window for this page."
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
  const selectedNeedsRestoredReview = selected ? restoredReviewGroupIds.has(selected.group_id) : false;

  const readyGroupIdList = readyGroups.map((group) => group.group_id).join("|");

  useEffect(() => {
    if (duplicateBinItemsPage && recycleBinPage > recycleBinTotalPages) {
      setRecycleBinPage(Math.max(1, recycleBinTotalPages));
    }
  }, [duplicateBinItemsPage, recycleBinPage, recycleBinTotalPages]);

  useEffect(() => {
    setSelectedReadyGroupIds((current) => current.filter((groupId) => readyGroupIds.has(groupId)));
  }, [readyGroupIdList]);

  useEffect(() => {
    if (!readyGroups.length) {
      setFocusedReadyGroupId(null);
      return;
    }
    if (!focusedReadyGroupId || !readyGroupIds.has(focusedReadyGroupId)) {
      setFocusedReadyGroupId(readyGroups[0].group_id);
    }
  }, [focusedReadyGroupId, readyGroupIdList, readyGroups, readyGroupIds]);

  const archivedItemIdList = recycleBinItems.map((item) => item.file_instance_id).join("|");

  useEffect(() => {
    if (!recycleBinItems.length) {
      setFocusedArchivedItemId(null);
      return;
    }
    if (!focusedArchivedItemId || !recycleBinItems.some((item) => item.file_instance_id === focusedArchivedItemId)) {
      setFocusedArchivedItemId(recycleBinItems[0].file_instance_id);
    }
  }, [archivedItemIdList, recycleBinItems, focusedArchivedItemId]);

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

  function moveReadyFocus(direction: -1 | 1) {
    if (!readyGroups.length || focusedReadyIndex < 0) return;
    const nextIndex = focusedReadyIndex + direction;
    if (nextIndex < 0 || nextIndex >= readyGroups.length) return;
    setFocusedReadyGroupId(readyGroups[nextIndex].group_id);
  }

  function moveArchivedFocus(direction: -1 | 1) {
    if (!recycleBinItems.length || focusedArchivedIndex < 0) return;
    const nextIndex = focusedArchivedIndex + direction;
    if (nextIndex < 0 || nextIndex >= recycleBinItems.length) return;
    setFocusedArchivedItemId(recycleBinItems[nextIndex].file_instance_id);
  }

  async function refreshRecycleBinQueries(targetPage: number | null = null) {
    const nextPage = targetPage ?? recycleBinPage;
    if (targetPage !== null && targetPage !== recycleBinPage) {
      setRecycleBinPage(targetPage);
    }
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: queryKeys.duplicates }),
      queryClient.invalidateQueries({ queryKey: queryKeys.duplicateBinItemsRoot }),
      queryClient.refetchQueries({ queryKey: queryKeys.duplicates, type: "active" }),
      queryClient.refetchQueries({ queryKey: queryKeys.duplicateBinItems(nextPage, 50), type: "active" }),
    ]);
  }

  async function handleMoveEligibleDuplicates(groupsToMove: DuplicateGroup[] = readyGroups, scope: "selected" | "all" | "single" = "all") {
    setRecycleBinFeedback(null);
    console.debug("duplicate_reclaim_debug: ui move request", {
      stage: "duplicate_reclaim_ui_request",
      scope,
      groupIds: groupsToMove.map((group) => group.group_id),
    });
    if (recycleConfigWarning) {
      setRecycleBinFeedback({ tone: "warning", message: recycleConfigWarning });
      return;
    }
    if (!groupsToMove.length) {
      setRecycleBinFeedback({
        tone: "warning",
        message:
          scope === "selected"
            ? "Select one or more actionable groups to move their extra copies into the Recycle Bin."
            : "No new files were moved. No eligible extra copies are left to move to the Recycle Bin.",
      });
      return;
    }

    const actionableGroups = groupsToMove.filter((group) => readyGroupIds.has(group.group_id));
    const targetGroupIds = new Set(groupsToMove.map((group) => group.group_id));

    if (!actionableGroups.length) {
      setSelectedReadyGroupIds((current) => current.filter((groupId) => !targetGroupIds.has(groupId)));
      await refreshRecycleBinQueries();
      setRecycleBinFeedback({
        tone: "warning",
        message: getGalleryNoOpSummary(scope),
      });
      return;
    }

    const actionableGroupIds = new Set(actionableGroups.map((group) => group.group_id));
    const groupsNeedingSync = actionableGroups.filter((group) => group.reclaim_status !== "REVIEWED_SAFE_TO_RECLAIM");
    const synced = await runPreflightReclaimSync(groupsNeedingSync);
    if (!synced) return;

    try {
      const result = await moveToBinMutation.mutateAsync({
        content_ids: actionableGroups.map((group) => group.group_id),
        retention_days: archiveRetentionDays ?? 14,
      });
      const summary = getMutationSummary(result.data);
      const diagnostics = getDuplicateBinOperationDiagnostics(result.data);
      console.debug("duplicate_reclaim_debug: ui move result", {
        stage: "duplicate_reclaim_ui_result",
        scope,
        requestedGroupIds: actionableGroups.map((group) => group.group_id),
        summary,
        diagnostics,
      });
      const applied = Number(summary.applied_count ?? 0);
      if (applied > 0) {
        setSelectedReadyGroupIds((current) => current.filter((groupId) => !actionableGroupIds.has(groupId)));
        await refreshRecycleBinQueries(1);
        setRecycleBinFeedback({
          tone: "success",
          message: getGalleryActionSummary(actionableGroups.length, applied),
        });
      } else {
        await refreshRecycleBinQueries();
        setSelectedReadyGroupIds((current) => current.filter((groupId) => !actionableGroupIds.has(groupId)));
        setRecycleBinFeedback({
          tone: "warning",
          message: getGalleryNoOpSummary(scope, diagnostics),
        });
      }
    } catch {
      setRecycleBinFeedback({
        tone: "warning",
        message: "The move action did not complete. No result was confirmed on this page.",
      });
    }
  }

  async function handleRestore(item: DuplicateBinItem) {
    setRecycleBinFeedback(null);
    try {
      const result = await restoreFromBinMutation.mutateAsync(item.file_instance_id);
      const summary = getMutationSummary(result.data);
      const applied = Number(summary.applied_count ?? 0);
      setRecycleBinFeedback(
        applied > 0
          ? {
              tone: "success",
              message: `${applied} file${applied === 1 ? "" : "s"} restored from the Recycle Bin. Restored groups stay out of Ready for Bin until they are reviewed again.`,
            }
          : {
              tone: "warning",
              message: "No files were restored. These items are no longer available in the Recycle Bin.",
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

    if (selectedNeedsRestoredReview) {
      void syncReclaimBridge(
        selected,
        mark === "looks_right" ? "REVIEWED_SAFE_TO_RECLAIM" : "UNREVIEWED",
        mark === "looks_right"
          ? `Saved “Looks right” for ${basename(selected.canonical_path)}, but the app could not return it to Ready for Bin.`
          : `Saved the review change for ${basename(selected.canonical_path)}, but the app could not clear its restored-review state.`,
      );
    } else if (isPendingRemovalStatus(selected.reclaim_status)) {
      markBridgeBlocked(selected.group_id, false);
    } else if (mark === "looks_right") {
      void syncReclaimBridge(
        selected,
        "REVIEWED_SAFE_TO_RECLAIM",
        `Saved “Looks right” for ${basename(selected.canonical_path)}, but the app could not add it to Ready for Bin. Try again from the Recycle Bin tab.`,
      );
    } else if (
      selected.reclaim_status === "REVIEWED_SAFE_TO_RECLAIM" ||
      reclaimBridgeBlockedIds.includes(selected.group_id)
    ) {
      void syncReclaimBridge(
        selected,
        "UNREVIEWED",
        `Saved the review change for ${basename(selected.canonical_path)}, but the app could not remove it from Ready for Bin.`,
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
    const recommendation = getDuplicateRecommendation(group);
    if (!keepCopy) return null;
    const isSelected = selectedReadyGroupIds.includes(group.group_id);
    const isFocused = focusedReadyGroupId === group.group_id;

    return (
      <Card
        key={group.group_id}
        data-testid={`ready-for-bin-gallery-card-${group.group_id}`}
        className={cn(
          "rounded-[24px] border-border/70 bg-card/95 shadow-sm transition-all",
          isFocused && "border-primary/30 shadow-md",
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
              <div className="pt-1">
                <StatusBadge
                  label={getRecommendationPresentation(recommendation).label}
                  severity={getRecommendationPresentation(recommendation).severity}
                />
              </div>
            </div>
            <div className="flex items-center gap-2">
              <Checkbox
                checked={isSelected}
                aria-label={`Select group ${basename(group.canonical_path)}`}
                onCheckedChange={(checked) => toggleReadyGroupSelection(group.group_id, Boolean(checked))}
                onClick={(event) => event.stopPropagation()}
              />
              <span className="text-xs text-muted-foreground">{isSelected ? "Selected" : isFocused ? "Focused" : "Select"}</span>
            </div>
          </div>

          <div
            role="button"
            tabIndex={0}
            className="space-y-4 outline-none"
            onClick={() => setFocusedReadyGroupId(group.group_id)}
            onKeyDown={(event) => {
              if (event.key === " " || event.key === "Enter") {
                event.preventDefault();
                setFocusedReadyGroupId(group.group_id);
              }
            }}
          >
            {recommendation ? (
              <div className="rounded-[18px] border border-border/70 bg-background/70 px-3 py-2.5">
                <p className="text-sm text-muted-foreground">{recommendation.operator_explanation}</p>
              </div>
            ) : null}
            <div className="grid gap-3 xl:grid-cols-[minmax(0,1.2fr)_minmax(0,0.8fr)]">
              <div className="space-y-2">
                <p className="text-xs uppercase tracking-[0.18em] text-muted-foreground">Keep copy</p>
                <DuplicateMediaPreview
                  src={keepCopy.preview_url ?? (keepCopy.is_image ? keepCopy.media_url ?? keepCopy.thumbnail_url : null)}
                  alt={basename(keepCopy.path)}
                  isImage={keepCopy.is_image}
                  mediaType={keepCopy.media_type}
                  className="aspect-[4/3] sm:aspect-[16/10]"
                  fit="contain"
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
                      className="aspect-square max-h-32"
                      fit="contain"
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
            <p className="text-xs text-muted-foreground">Only the extra copies in this group move into the Recycle Bin.</p>
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => void handleMoveEligibleDuplicates([group], "single")}
              disabled={moveToBinMutation.isPending || Boolean(recycleConfigWarning)}
            >
              Move to Recycle Bin
            </Button>
          </div>
        </CardContent>
      </Card>
    );
  }

  function renderGalleryHoldingCard(item: RecycleBinDisplayItem) {
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
              <div className="flex flex-wrap items-center gap-2">
                <StatusBadge
                  label={item.restore_allowed ? binStateLabels.inBin : binStateLabels.expired}
                  severity={item.restore_allowed ? "neutral" : "caution"}
                />
                {item.expires_at ? (
                  <StatusBadge
                    label={
                      item.restore_allowed
                        ? formatDaysRemaining(item.expires_at) ?? binStateLabels.daysRemaining
                        : binStateLabels.restoreWindowEnded
                    }
                    severity={item.restore_allowed ? "info" : "caution"}
                  />
                ) : null}
              </div>
              <p className="truncate text-base font-semibold text-foreground">{basename(item.original_path)}</p>
              <p className="text-sm text-muted-foreground">
                {item.restore_allowed
                  ? "Restore from the Recycle Bin here while the restore window is still open."
                  : "Restore window ended. This file stays visible here until a later purge removes it."}
              </p>
            </div>
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => void handleRestore(item)}
              disabled={restoreFromBinMutation.isPending || !item.restore_allowed}
            >
              Restore from Recycle Bin
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
                  fit="contain"
                />
              ) : (
                <div className="rounded-[24px] border border-border/70 bg-background/70 p-4 text-sm text-muted-foreground">
                  Keep copy preview is not available for this item.
                </div>
              )}
            </div>
            <div className="space-y-2">
              <p className="text-xs uppercase tracking-[0.18em] text-muted-foreground">Extra copy in Recycle Bin</p>
              {movedCopy ? (
                <DuplicateMediaPreview
                  src={movedCopy.preview_url ?? (movedCopy.is_image ? movedCopy.media_url ?? movedCopy.thumbnail_url : null)}
                  alt={basename(movedCopy.path)}
                  isImage={movedCopy.is_image}
                  mediaType={movedCopy.media_type}
                  className="aspect-[4/3]"
                  fit="contain"
                />
              ) : (
                <div className="rounded-[24px] border border-border/70 bg-background/70 p-4 text-sm text-muted-foreground">
                  Preview is not available for this held extra copy.
                </div>
              )}
            </div>
          </div>
          <div className="space-y-1">
            <p className="truncate text-xs font-medium text-foreground">{basename(item.original_path)}</p>
            <p className="truncate text-xs text-muted-foreground">{item.archive_path}</p>
          </div>
        </CardContent>
      </Card>
    );
  }

  function renderFocusedReadyGroup(group: DuplicateGroup) {
    const keepCopy = getKeepCopy(group);
    if (!keepCopy) return null;
    const extraCopies = getExtraCopies(group);
    const recommendation = getDuplicateRecommendation(group);
    return (
      <div
        data-testid="ready-for-bin-focused-panel"
        className="rounded-[22px] border border-border/70 bg-background/80 p-4"
      >
        <div className="flex flex-col gap-3 border-b border-border/70 pb-4 lg:flex-row lg:items-start lg:justify-between">
          <div className="min-w-0 space-y-1">
            <p className="text-xs uppercase tracking-[0.18em] text-muted-foreground">Focused Ready for Bin group</p>
            <p data-testid="ready-for-bin-focused-title" className="truncate text-lg font-semibold text-foreground">
              {basename(group.canonical_path)}
            </p>
            <p className="text-sm text-muted-foreground">
              {focusedReadyIndex + 1} of {readyGroups.length} ready groups • {extraCopies.length === 1 ? "1 extra copy" : `${extraCopies.length} extra copies`} • {formatBytes(group.estimated_reclaim_bytes ?? 0)}
            </p>
            <div className="pt-1">
              <StatusBadge
                label={getRecommendationPresentation(recommendation).label}
                severity={getRecommendationPresentation(recommendation).severity}
              />
            </div>
          </div>
          <div className="flex flex-wrap gap-2">
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => moveReadyFocus(-1)}
              disabled={focusedReadyIndex <= 0}
            >
              <ChevronLeft className="mr-1 h-4 w-4" />
              Previous
            </Button>
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => moveReadyFocus(1)}
              disabled={focusedReadyIndex < 0 || focusedReadyIndex >= readyGroups.length - 1}
            >
              Next
              <ChevronRight className="ml-1 h-4 w-4" />
            </Button>
          </div>
        </div>

        {recommendation ? (
          <div className="mt-4 rounded-[18px] border border-primary/20 bg-primary/5 px-4 py-3">
            <p className="text-xs uppercase tracking-[0.18em] text-muted-foreground">Recommendation</p>
            <div className="mt-2 space-y-2">
              <p className="text-sm text-foreground">{recommendation.operator_explanation}</p>
              <div className="flex flex-wrap gap-2">
                {getRecommendationReasonLabels(recommendation).map((label) => (
                  <StatusBadge key={label} label={label} severity="neutral" />
                ))}
              </div>
            </div>
          </div>
        ) : null}

        <div className="mt-4 grid gap-4 xl:grid-cols-[minmax(0,1.2fr)_minmax(0,0.8fr)]">
          <div className="space-y-2">
            <p className="text-xs uppercase tracking-[0.18em] text-muted-foreground">Keep copy</p>
            <DuplicateMediaPreview
              src={keepCopy.preview_url ?? (keepCopy.is_image ? keepCopy.media_url ?? keepCopy.thumbnail_url : null)}
              alt={basename(keepCopy.path)}
              isImage={keepCopy.is_image}
              mediaType={keepCopy.media_type}
              className="aspect-[4/3] max-h-[28rem]"
              fit="contain"
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
                  className="aspect-square max-h-36"
                  fit="contain"
                />
              ))}
            </div>
            {extraCopies.length > 4 ? (
              <p className="text-xs text-muted-foreground">+{extraCopies.length - 4} more extra copies</p>
            ) : null}
          </div>
        </div>

        <div className="mt-4 flex flex-col gap-3 border-t border-border/70 pt-4 lg:flex-row lg:items-center lg:justify-between">
          <p className="text-sm text-muted-foreground">
            Move only this group&apos;s extra copies into the Recycle Bin. The keep copy stays in place.
          </p>
          <div className="flex flex-wrap gap-2">
            <Button
              type="button"
              size="sm"
              onClick={() => void handleMoveEligibleDuplicates([group], "single")}
              disabled={moveToBinMutation.isPending || Boolean(recycleConfigWarning)}
            >
              Move to Recycle Bin
            </Button>
          </div>
        </div>
      </div>
    );
  }

  function renderFocusedArchivedItem(item: RecycleBinDisplayItem) {
    const group = groupsById[item.content_id];
    const keepCopy = group ? getKeepCopy(group) : null;
    const movedCopy =
      group?.duplicates.find((file) => file.file_instance_id === item.file_instance_id) ??
      group?.duplicates.find((file) => !file.is_canonical) ??
      null;

    return (
      <div data-testid="recycle-bin-focused-panel" className="rounded-[22px] border border-border/70 bg-background/80 p-4">
        <div className="flex flex-col gap-3 border-b border-border/70 pb-4 lg:flex-row lg:items-start lg:justify-between">
          <div className="min-w-0 space-y-1">
            <p className="text-xs uppercase tracking-[0.18em] text-muted-foreground">Focused Recycle Bin item</p>
            <p data-testid="recycle-bin-focused-title" className="truncate text-lg font-semibold text-foreground">
              {basename(item.original_path)}
            </p>
            <p className="text-sm text-muted-foreground">
              {focusedArchivedIndex + 1} of {recycleBinItems.length} items in Recycle Bin
              {item.expires_at
                ? ` • ${item.restore_allowed ? formatDaysRemaining(item.expires_at) ?? binStateLabels.daysRemaining : binStateLabels.restoreWindowEnded}`
                : ""}
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => moveArchivedFocus(-1)}
              disabled={focusedArchivedIndex <= 0}
            >
              <ChevronLeft className="mr-1 h-4 w-4" />
              Previous
            </Button>
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => moveArchivedFocus(1)}
              disabled={focusedArchivedIndex < 0 || focusedArchivedIndex >= recycleBinItems.length - 1}
            >
              Next
              <ChevronRight className="ml-1 h-4 w-4" />
            </Button>
          </div>
        </div>

        <div className="mt-4 grid gap-4 xl:grid-cols-[minmax(0,1.1fr)_minmax(0,0.9fr)]">
          <div className="space-y-2">
            <p className="text-xs uppercase tracking-[0.18em] text-muted-foreground">Keep copy</p>
            {keepCopy ? (
              <DuplicateMediaPreview
                src={keepCopy.preview_url ?? (keepCopy.is_image ? keepCopy.media_url ?? keepCopy.thumbnail_url : null)}
                alt={basename(keepCopy.path)}
                isImage={keepCopy.is_image}
                mediaType={keepCopy.media_type}
                className="aspect-[4/3] max-h-[24rem]"
                fit="contain"
              />
            ) : (
              <div className="rounded-[24px] border border-border/70 bg-background/70 p-4 text-sm text-muted-foreground">
                Keep copy preview is not available for this item.
              </div>
            )}
          </div>
          <div className="space-y-2">
            <p className="text-xs uppercase tracking-[0.18em] text-muted-foreground">In Recycle Bin</p>
            {movedCopy ? (
              <DuplicateMediaPreview
                src={movedCopy.preview_url ?? (movedCopy.is_image ? movedCopy.media_url ?? movedCopy.thumbnail_url : null)}
                alt={basename(movedCopy.path)}
                isImage={movedCopy.is_image}
                mediaType={movedCopy.media_type}
                className="aspect-[4/3] max-h-[20rem]"
                fit="contain"
              />
            ) : (
              <div className="rounded-[24px] border border-border/70 bg-background/70 p-4 text-sm text-muted-foreground">
                Preview is not available for this Recycle Bin item.
              </div>
            )}
            <div className="space-y-1">
              <StatusBadge
                label={item.restore_allowed ? binStateLabels.inBin : binStateLabels.expired}
                severity={item.restore_allowed ? "neutral" : "caution"}
              />
              <p className="truncate text-xs font-medium text-foreground">{basename(item.original_path)}</p>
              <p className="truncate text-xs text-muted-foreground">{item.archive_path}</p>
            </div>
          </div>
        </div>

        <div className="mt-4 flex flex-col gap-3 border-t border-border/70 pt-4 lg:flex-row lg:items-center lg:justify-between">
          <p className="text-sm text-muted-foreground">
            {item.restore_allowed
              ? "Restore this extra copy from the Recycle Bin back to its original location."
              : "Restore window ended. This extra copy remains visible here until it is purged."}
          </p>
          <Button
            type="button"
            size="sm"
            onClick={() => void handleRestore(item)}
            disabled={restoreFromBinMutation.isPending || !item.restore_allowed}
          >
            Restore from Recycle Bin
          </Button>
        </div>
      </div>
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
        description="Compare duplicates, move extra copies to the Recycle Bin, restore them if needed, and keep playback review separate."
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
      {moveToBinMutation.error && (
        <ErrorAlert message={getErrorMessage(moveToBinMutation.error) || "Failed to move duplicates to the Recycle Bin"} />
      )}
      {restoreFromBinMutation.error && (
        <ErrorAlert message={getErrorMessage(restoreFromBinMutation.error) || "Failed to restore duplicate from the Recycle Bin"} />
      )}
      {playbackIssuesQuery.error && activeTab === "playback-issues" ? (
        <ErrorAlert message={getErrorMessage(playbackIssuesQuery.error) || "Failed to load playback issues for duplicates"} />
      ) : null}
      {reclaimBridgeWarning && activeTab === "ready-for-bin" ? <ErrorAlert message={reclaimBridgeWarning} /> : null}

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
                <TabsTrigger value="ready-for-bin">Ready for Bin</TabsTrigger>
                <TabsTrigger value="recycle-bin">Recycle Bin</TabsTrigger>
                <TabsTrigger value="playback-issues">Playback issues</TabsTrigger>
              </TabsList>

              <TabsContent value="review" className="mt-0">
                <div className="space-y-2">
                  <div className="flex flex-col gap-2 lg:flex-row lg:items-center lg:justify-between">
                    <div>
                      <h2 className="text-lg font-semibold tracking-tight text-foreground">Review duplicates</h2>
                      <p className="mt-1 text-sm text-muted-foreground">
                        Compare one group at a time, follow the system recommendation, and keep your own review decision separate.
                      </p>
                    </div>
                    <p className="text-sm text-muted-foreground">{reviewProgressLabel} in sequence</p>
                  </div>
                </div>
              </TabsContent>

              <TabsContent value="ready-for-bin" className="mt-0">
                <div className="space-y-2">
                  <h2 className="text-xl font-semibold tracking-tight text-foreground">Ready for Bin</h2>
                  <p className="text-sm text-muted-foreground">
                    These groups are currently recommended as safe to move into the Recycle Bin. Restore happens only on the Recycle Bin tab.
                  </p>
                </div>
              </TabsContent>

              <TabsContent value="recycle-bin" className="mt-0">
                <div className="space-y-2">
                  <h2 className="text-xl font-semibold tracking-tight text-foreground">Recycle Bin</h2>
                  <p className="text-sm text-muted-foreground">
                    Browse extra copies already in the Recycle Bin and restore them when needed.
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
                            const presentation = restoredReviewGroupIds.has(group.group_id)
                              ? { label: "Restored", severity: "info" as const }
                              : getReviewPresentation(currentReviewMark(group), Boolean(group.is_stale));
                            return (
                            <DuplicateQueueItem
                              key={group.group_id}
                              index={index}
                              active={selected?.group_id === group.group_id}
                              group={group}
                              markLabel={presentation.label}
                              secondaryStatusText={recycleBinLifecycleGroupIds.has(group.group_id) ? "In Recycle Bin" : null}
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
                          <div
                            data-testid="review-recommendation-card"
                            className="rounded-[18px] border border-primary/20 bg-primary/5 px-3 py-3"
                          >
                            <div className="space-y-2">
                              <p className="text-xs uppercase tracking-[0.18em] text-muted-foreground">System recommendation</p>
                              <div className="flex flex-wrap items-center gap-2">
                                <StatusBadge
                                  label={getRecommendationPresentation(getDuplicateRecommendation(selected)).label}
                                  severity={getRecommendationPresentation(getDuplicateRecommendation(selected)).severity}
                                />
                              </div>
                              {renderRecommendationDetails(getDuplicateRecommendation(selected))}
                            </div>
                          </div>
                          <div
                            data-testid="review-human-review-card"
                            className="rounded-[18px] border border-border/70 bg-background/70 px-3 py-3"
                          >
                            <div className="space-y-2">
                              <p className="text-xs uppercase tracking-[0.18em] text-muted-foreground">Human review</p>
                              <div className="flex flex-wrap items-center gap-2">
                                <StatusBadge
                                  label={getReviewPresentation(currentReviewMark(selected), Boolean(selected.is_stale)).label}
                                  severity={getReviewPresentation(currentReviewMark(selected), Boolean(selected.is_stale)).severity}
                                />
                              </div>
                              <p className="text-sm text-muted-foreground">
                                {selected.reviewed_at
                                  ? `Last reviewed ${new Date(selected.reviewed_at).toLocaleString()}.`
                                  : "No saved review yet. Choose the mark that best fits this group."}
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
                            progressLabel={reviewProgressLabel}
                          />
                          {selectedNeedsRestoredReview ? (
                            <div className="flex flex-col gap-1 rounded-[18px] border border-primary/20 bg-primary/5 px-3 py-2.5">
                              <p className="text-sm font-semibold text-foreground">Restored from Recycle Bin</p>
                              <p className="text-sm text-muted-foreground">Review again before this group can re-enter Ready for Bin.</p>
                            </div>
                          ) : null}
                          {selected && recycleBinLifecycleGroupIds.has(selected.group_id) ? (
                            <div className="flex flex-col gap-1 rounded-[18px] border border-border/70 bg-background/70 px-3 py-2.5">
                              <p className="text-sm font-medium text-foreground">In Recycle Bin</p>
                              <p className="text-sm text-muted-foreground">Extra copies are already in the Recycle Bin. The keep copy stays in place.</p>
                            </div>
                          ) : null}
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

          <TabsContent value="ready-for-bin" className="mt-0">
            <div className="space-y-4">
              <div className="grid gap-3 md:grid-cols-2">
                <Card className="rounded-[22px] border-border/70 bg-card/95 shadow-sm">
                  <CardContent className="space-y-1 p-4">
                    <p className="text-xs uppercase tracking-[0.18em] text-muted-foreground">Ready for Bin</p>
                    <p className="text-2xl font-semibold text-foreground">{readyGroups.length}</p>
                    <p className="text-sm text-muted-foreground">{readyExtraCopyCount} extra copies are ready for the Recycle Bin.</p>
                  </CardContent>
                </Card>
                <Card className="rounded-[22px] border-border/70 bg-card/95 shadow-sm">
                  <CardContent className="space-y-1 p-4">
                    <p className="text-xs uppercase tracking-[0.18em] text-muted-foreground">Space you could free up</p>
                    <p className="text-2xl font-semibold text-foreground">{formatBytes(readyEstimatedBytes)}</p>
                    <p className="text-sm text-muted-foreground">Estimated space if the ready extra copies move out of the main library.</p>
                  </CardContent>
                </Card>
              </div>

              <Card className="rounded-[24px] border-border/70 bg-card/95 shadow-sm">
                <CardContent className="flex flex-col gap-3 p-4 lg:flex-row lg:items-center lg:justify-between">
                  <div>
                    <p className="text-sm font-semibold text-foreground">View</p>
                    <p className="text-sm text-muted-foreground">Focus is the primary workflow here. Switch quietly to list or gallery only when you need to scan or bulk-select groups.</p>
                  </div>
                  <ToggleGroup
                    type="single"
                    value={readyForBinViewMode}
                    onValueChange={(value) => {
                      if (value === "focus" || value === "gallery" || value === "list") setReadyForBinViewMode(value);
                    }}
                    variant="outline"
                    size="sm"
                    className="justify-start"
                    data-testid="ready-for-bin-view-toggle"
                  >
                    <ToggleGroupItem value="focus" aria-label="Focus view" data-testid="ready-for-bin-view-focus">
                      <PanelLeft className="h-4 w-4" />
                      Focus
                    </ToggleGroupItem>
                    <ToggleGroupItem value="list" aria-label="List view" data-testid="ready-for-bin-view-list">
                      <List className="h-4 w-4" />
                      List
                    </ToggleGroupItem>
                    <ToggleGroupItem value="gallery" aria-label="Gallery view" data-testid="ready-for-bin-view-gallery">
                      <LayoutGrid className="h-4 w-4" />
                      Gallery
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
                      <p className="text-sm font-semibold text-foreground">Ready for Bin</p>
                      <p className="text-sm text-muted-foreground">This workflow view is filtered from the backend recommendation. The keep copy always stays in place.</p>
                    </div>
                    {readyForBinViewMode !== "focus" ? (
                      <div className="flex flex-wrap gap-2">
                        <Button
                          type="button"
                          variant="outline"
                          onClick={() => void handleMoveEligibleDuplicates(readyGroups, "all")}
                          disabled={moveToBinMutation.isPending || readyGroups.length === 0 || Boolean(recycleConfigWarning)}
                        >
                          Move all eligible groups
                        </Button>
                      </div>
                    ) : null}
                  </div>
                  <div className="rounded-[18px] border border-border/70 bg-background/70 px-4 py-3 text-sm text-muted-foreground">
                    {recycleConfigWarning ? (
                      <p className="text-caution">{recycleConfigWarning}</p>
                    ) : (
                      <p>
                        Recycle Bin: <span className="font-mono text-foreground">{archiveRoot}</span>. Current restore window: {archiveRetentionDays} day{archiveRetentionDays === 1 ? "" : "s"}.
                      </p>
                    )}
                  </div>

                  {restoredReviewGroupIds.size ? (
                    <div className="flex flex-col gap-3 rounded-[18px] border border-border/70 bg-background/70 px-4 py-3 text-sm text-muted-foreground lg:flex-row lg:items-center lg:justify-between">
                      <p>
                        {restoredReviewGroupIds.size} restored group{restoredReviewGroupIds.size === 1 ? "" : "s"} {restoredReviewGroupIds.size === 1 ? "needs" : "need"} review before {restoredReviewGroupIds.size === 1 ? "it can" : "they can"} re-enter Ready for Bin.
                      </p>
                      <Button
                        type="button"
                        variant="outline"
                        size="sm"
                        onClick={() => {
                          setReviewFilter("restored");
                          setActiveTab("review");
                        }}
                      >
                        Review restored groups
                      </Button>
                    </div>
                  ) : null}

                  {!readyGroups.length ? (
                    <p className="text-sm text-muted-foreground">No eligible extra copies are left to move to the Recycle Bin.</p>
                  ) : null}

                  {readyForBinViewMode === "focus" ? (
                    focusedReadyGroup ? renderFocusedReadyGroup(focusedReadyGroup) : null
                  ) : null}

                  {readyForBinViewMode !== "focus" && selectedReadyGroups.length ? (
                    <div
                      data-testid="ready-for-bin-bulk-action-bar"
                      className="flex flex-col gap-3 rounded-[20px] border border-primary/20 bg-primary/5 px-4 py-3 lg:flex-row lg:items-center lg:justify-between"
                    >
                      <div className="space-y-1">
                        <p className="text-sm font-semibold text-foreground">
                          {selectedReadyGroups.length} selected group{selectedReadyGroups.length === 1 ? "" : "s"}
                        </p>
                        <p className="text-sm text-muted-foreground">Move only the extra copies from the selected groups into the Recycle Bin.</p>
                      </div>
                      <div className="flex flex-wrap gap-2">
                        <Button
                          type="button"
                          onClick={() => void handleMoveEligibleDuplicates(selectedReadyGroups, "selected")}
                          disabled={moveToBinMutation.isPending || Boolean(recycleConfigWarning)}
                        >
                          Move selected groups
                        </Button>
                        <Button type="button" variant="outline" onClick={clearReadyGroupSelection}>
                          Clear selection
                        </Button>
                      </div>
                    </div>
                  ) : null}

                  {readyGroups.length && readyForBinViewMode === "gallery" ? (
                    <div data-testid="ready-for-bin-gallery" className="grid gap-4 xl:grid-cols-2">
                      {readyGroups.map((group) => renderGalleryReadyCard(group))}
                    </div>
                  ) : null}

                  {readyGroups.length && readyForBinViewMode === "list" ? (
                    <div data-testid="ready-for-bin-list" className="space-y-3">
                      {readyGroups.map((group) => {
                        const isSelected = selectedReadyGroupIds.includes(group.group_id);
                        const recommendation = getDuplicateRecommendation(group);
                        return (
                          <div
                            key={group.group_id}
                            role="button"
                            tabIndex={0}
                            className={cn(
                              "flex flex-col gap-3 rounded-[22px] border border-border/70 bg-background/70 p-4 lg:flex-row lg:items-center lg:justify-between",
                              focusedReadyGroupId === group.group_id && "border-primary/30 shadow-sm",
                              isSelected && "border-primary/45 ring-2 ring-primary/15",
                            )}
                            onClick={() => setFocusedReadyGroupId(group.group_id)}
                            onKeyDown={(event) => {
                              if (event.key === " " || event.key === "Enter") {
                                event.preventDefault();
                                setFocusedReadyGroupId(group.group_id);
                              }
                            }}
                          >
                            <div className="flex min-w-0 items-start gap-3">
                              <Checkbox
                                checked={isSelected}
                                aria-label={`Select group ${basename(group.canonical_path)}`}
                                onCheckedChange={(checked) => toggleReadyGroupSelection(group.group_id, Boolean(checked))}
                                onClick={(event) => event.stopPropagation()}
                              />
                              <div className="min-w-0 space-y-2">
                                <div className="flex flex-wrap items-center gap-2">
                                  <StatusBadge label={binStateLabels.ready} severity="success" />
                                  <StatusBadge
                                    label={getRecommendationPresentation(recommendation).label}
                                    severity={getRecommendationPresentation(recommendation).severity}
                                  />
                                  <StatusBadge
                                    label={`${group.reclaimable_file_count ?? 0} extra cop${(group.reclaimable_file_count ?? 0) === 1 ? "y" : "ies"}`}
                                    severity="neutral"
                                  />
                                  <StatusBadge label={formatBytes(group.estimated_reclaim_bytes ?? 0)} severity="info" />
                                </div>
                                <p className="truncate text-sm font-semibold text-foreground">{basename(group.canonical_path)}</p>
                                <p className="text-xs text-muted-foreground">
                                  {recommendation?.operator_explanation ?? "Move only the extra copies from this group into the Recycle Bin."}
                                </p>
                              </div>
                            </div>
                            <Button
                              type="button"
                              variant="outline"
                              size="sm"
                              onClick={(event) => {
                                event.stopPropagation();
                                void handleMoveEligibleDuplicates([group], "single");
                              }}
                              disabled={moveToBinMutation.isPending || Boolean(recycleConfigWarning)}
                            >
                              Move this group
                            </Button>
                          </div>
                        );
                      })}
                    </div>
                  ) : null}
                </CardContent>
              </Card>

            </div>
          </TabsContent>

          <TabsContent value="recycle-bin" className="mt-0">
            <div className="space-y-4">
              <div className="grid gap-3 md:grid-cols-3">
                <Card className="rounded-[22px] border-border/70 bg-card/95 shadow-sm">
                  <CardContent className="space-y-1 p-4">
                    <p className="text-xs uppercase tracking-[0.18em] text-muted-foreground">In Recycle Bin</p>
                    <p className="text-2xl font-semibold text-foreground">{recycleBinTotalCount}</p>
                    <p className="text-sm text-muted-foreground">These extra copies still physically exist in the Recycle Bin across all pages.</p>
                  </CardContent>
                </Card>
                <Card className="rounded-[22px] border-border/70 bg-card/95 shadow-sm">
                  <CardContent className="space-y-1 p-4">
                    <p className="text-xs uppercase tracking-[0.18em] text-muted-foreground">Restore available on this page</p>
                    <p className="text-2xl font-semibold text-foreground">{restorableRecycleBinItems.length}</p>
                    <p className="text-sm text-muted-foreground">These loaded items can still be restored from the Recycle Bin.</p>
                  </CardContent>
                </Card>
                <Card className="rounded-[22px] border-border/70 bg-card/95 shadow-sm">
                  <CardContent className="space-y-1 p-4">
                    <p className="text-xs uppercase tracking-[0.18em] text-muted-foreground">Restore window ended on this page</p>
                    <p className="text-2xl font-semibold text-foreground">{expiredRecycleBinItems.length}</p>
                    <p className="text-sm text-muted-foreground">These loaded expired items stay visible here until they are purged.</p>
                  </CardContent>
                </Card>
              </div>

              <Card className="rounded-[24px] border-border/70 bg-card/95 shadow-sm">
                <CardContent className="flex flex-col gap-3 p-4 lg:flex-row lg:items-center lg:justify-between">
                  <div>
                    <p className="text-sm font-semibold text-foreground">View</p>
                    <p className="text-sm text-muted-foreground">Gallery is the primary browsing workflow here. Switch to list for denser scanning or focus for a single-item drill-in.</p>
                  </div>
                  <ToggleGroup
                    type="single"
                    value={recycleBinViewMode}
                    onValueChange={(value) => {
                      if (value === "focus" || value === "gallery" || value === "list") setRecycleBinViewMode(value);
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
                    <ToggleGroupItem value="focus" aria-label="Focus view" data-testid="recycle-bin-view-focus">
                      <PanelLeft className="h-4 w-4" />
                      Focus
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

                  <div>
                    <p className="text-sm font-semibold text-foreground">In Recycle Bin</p>
                    <p className="text-sm text-muted-foreground">Browse already moved extra copies here. Restore is available only while the restore window remains open.</p>
                  </div>

                  {recycleConfigWarning ? (
                    <div className="rounded-[18px] border border-border/70 bg-background/70 px-4 py-3 text-sm text-caution">
                      {recycleConfigWarning}
                    </div>
                  ) : (
                    <div className="rounded-[18px] border border-border/70 bg-background/70 px-4 py-3 text-sm text-muted-foreground">
                      Recycle Bin: <span className="font-mono text-foreground">{archiveRoot}</span>. Current restore window: {archiveRetentionDays} day{archiveRetentionDays === 1 ? "" : "s"}.
                    </div>
                  )}

                  {recycleBinTotalPages > 1 ? (
                    <div className="flex flex-col gap-3 rounded-[18px] border border-border/70 bg-background/70 px-4 py-3 text-sm text-muted-foreground lg:flex-row lg:items-center lg:justify-between">
                      <p>
                        Showing page {recycleBinPage} of {recycleBinTotalPages} for Recycle Bin items.
                      </p>
                      <div className="flex gap-2">
                        <Button
                          type="button"
                          variant="outline"
                          size="sm"
                          onClick={() => setRecycleBinPage((current) => Math.max(1, current - 1))}
                          disabled={recycleBinPage <= 1}
                        >
                          Previous page
                        </Button>
                        <Button
                          type="button"
                          variant="outline"
                          size="sm"
                          onClick={() => setRecycleBinPage((current) => Math.min(recycleBinTotalPages, current + 1))}
                          disabled={recycleBinPage >= recycleBinTotalPages}
                        >
                          Next page
                        </Button>
                      </div>
                    </div>
                  ) : null}

                  {!recycleBinItems.length ? (
                    <p className="text-sm text-muted-foreground">No duplicate files are in the Recycle Bin right now.</p>
                  ) : recycleBinViewMode === "gallery" ? (
                    <div data-testid="recycle-bin-gallery" className="grid gap-4 xl:grid-cols-3">
                      {recycleBinItems.map((item) => renderGalleryHoldingCard(item))}
                    </div>
                  ) : recycleBinViewMode === "list" ? (
                    <div data-testid="recycle-bin-list" className="space-y-3">
                      {recycleBinItems.map((item) => (
                        <div
                          key={item.file_instance_id}
                          className="flex flex-col gap-3 rounded-[22px] border border-border/70 bg-background/70 p-4 lg:flex-row lg:items-center lg:justify-between"
                        >
                          <div className="min-w-0 space-y-2">
                            <div className="flex flex-wrap items-center gap-2">
                              <StatusBadge
                                label={item.restore_allowed ? binStateLabels.inBin : binStateLabels.expired}
                                severity={item.restore_allowed ? "neutral" : "caution"}
                              />
                              <StatusBadge
                                label={item.restore_allowed ? formatDaysRemaining(item.expires_at) ?? binStateLabels.daysRemaining : binStateLabels.restoreWindowEnded}
                                severity={item.restore_allowed ? "info" : "caution"}
                              />
                            </div>
                            <p className="truncate text-sm font-semibold text-foreground">{basename(item.original_path)}</p>
                            <p className="truncate text-xs text-muted-foreground">{item.archive_path}</p>
                          </div>
                          <Button
                            type="button"
                            variant="outline"
                            onClick={() => void handleRestore(item)}
                            disabled={restoreFromBinMutation.isPending || !item.restore_allowed}
                          >
                            Restore from Recycle Bin
                          </Button>
                        </div>
                      ))}
                    </div>
                  ) : (
                    focusedArchivedItem ? renderFocusedArchivedItem(focusedArchivedItem) : null
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
