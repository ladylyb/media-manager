import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import DuplicatesPage from "@/pages/DuplicatesPage";

function buildRecommendation(
  overrides: Partial<{
    state: string;
    classification: string;
    primary_reason_code: string;
    reason_codes: string[];
    operator_explanation: string;
    review_is_stale: boolean;
    integrity_is_stale: boolean;
    lifecycle_context: {
      already_in_bin: boolean;
      restore_expired: boolean;
    };
    keep_summary: {
      identity_status: string;
      integrity_status: string;
    };
    extra_summary: {
      health_class: string;
      active_count: number;
      healthy_count: number;
      suspect_count: number;
      broken_count: number;
      unknown_count: number;
    };
  }> = {},
) {
  return {
    state: "REVIEW_REQUIRED",
    classification: "WARN",
    primary_reason_code: "REVIEW_REQUIRED_BY_OPERATOR_STATE",
    reason_codes: ["REVIEW_REQUIRED_BY_OPERATOR_STATE"],
    operator_explanation: "This group is not yet operator-approved for movement.",
    review_is_stale: false,
    integrity_is_stale: false,
    lifecycle_context: {
      already_in_bin: false,
      restore_expired: false,
    },
    keep_summary: {
      identity_status: "KNOWN",
      integrity_status: "OK",
    },
    extra_summary: {
      health_class: "EXTRAS_ALL_HEALTHY",
      active_count: 1,
      healthy_count: 1,
      suspect_count: 0,
      broken_count: 0,
      unknown_count: 0,
    },
    ...overrides,
  };
}

const mocks = vi.hoisted(() => ({
  moveDuplicatesToBin: vi.fn(),
  getDuplicateBinPolicy: vi.fn(),
  getDuplicates: vi.fn(),
  getDuplicateBinItems: vi.fn(),
  getIntegrityIssues: vi.fn(),
  restoreDuplicatesFromBin: vi.fn(),
  setDuplicateReclaim: vi.fn(),
  setDuplicateReview: vi.fn(),
}));

vi.mock("@/lib/api/endpoints", () => ({
  moveDuplicatesToBin: mocks.moveDuplicatesToBin,
  getDuplicateBinPolicy: mocks.getDuplicateBinPolicy,
  getDuplicates: mocks.getDuplicates,
  getDuplicateBinItems: mocks.getDuplicateBinItems,
  getIntegrityIssues: mocks.getIntegrityIssues,
  restoreDuplicatesFromBin: mocks.restoreDuplicatesFromBin,
  setDuplicateReclaim: mocks.setDuplicateReclaim,
  setDuplicateReview: mocks.setDuplicateReview,
}));

function buildGroup(id: string, canonicalName: string, duplicateNames: string[]) {
  return {
    group_id: id,
    hash: `${id}-hash`,
    canonical_path: `/library/${canonicalName}`,
    integrity_issue_count: 0,
    integrity_broken_count: 0,
    integrity_suspect_count: 0,
    reclaimable_file_count: duplicateNames.length,
    estimated_reclaim_bytes: 4 * 1024 * 1024,
    duplicate_recommendation: buildRecommendation({
      extra_summary: {
        health_class: duplicateNames.length ? "EXTRAS_ALL_HEALTHY" : "NO_ACTIVE_EXTRAS",
        active_count: duplicateNames.length,
        healthy_count: duplicateNames.length,
        suspect_count: 0,
        broken_count: 0,
        unknown_count: 0,
      },
    }),
    duplicates: [
      {
        file_instance_id: `${id}-canonical`,
        path: `/library/${canonicalName}`,
        media_type: "image",
        is_image: true,
        media_url: `/media/${id}-canonical`,
        preview_url: `/api/thumbnail/${id}-canonical`,
        thumbnail_url: null,
        is_canonical: true,
      },
      ...duplicateNames.map((name, index) => ({
        file_instance_id: `${id}-duplicate-${index}`,
        path: `/library/${name}`,
        media_type: "image",
        is_image: true,
        media_url: `/media/${id}-duplicate-${index}`,
        preview_url: `/api/thumbnail/${id}-duplicate-${index}`,
        thumbnail_url: null,
        is_canonical: false,
      })),
    ],
  };
}

function buildVideoGroup(id: string, canonicalName: string, duplicateNames: string[]) {
  return {
    group_id: id,
    hash: `${id}-hash`,
    canonical_path: `/library/${canonicalName}`,
    reclaimable_file_count: duplicateNames.length,
    estimated_reclaim_bytes: 4 * 1024 * 1024,
    duplicate_recommendation: buildRecommendation({
      extra_summary: {
        health_class: duplicateNames.length ? "EXTRAS_ALL_HEALTHY" : "NO_ACTIVE_EXTRAS",
        active_count: duplicateNames.length,
        healthy_count: duplicateNames.length,
        suspect_count: 0,
        broken_count: 0,
        unknown_count: 0,
      },
    }),
    duplicates: [
      {
        file_instance_id: `${id}-canonical`,
        path: `/library/${canonicalName}`,
        media_type: "VID",
        is_image: false,
        media_url: null,
        preview_url: `/api/video-thumbnail/${id}-canonical`,
        thumbnail_url: null,
        is_canonical: true,
      },
      ...duplicateNames.map((name, index) => ({
        file_instance_id: `${id}-duplicate-${index}`,
        path: `/library/${name}`,
        media_type: "VID",
        is_image: false,
        media_url: null,
        preview_url: `/api/video-thumbnail/${id}-duplicate-${index}`,
        thumbnail_url: null,
        is_canonical: false,
      })),
    ],
  };
}

function markGroupSafeToMove<T extends Record<string, unknown>>(group: T, explanation?: string): T {
  return {
    ...group,
    review_status: "looks_right",
    duplicate_recommendation: buildRecommendation({
      state: "SAFE_TO_MOVE_EXTRAS",
      classification: "INFO",
      primary_reason_code: "SAFE_TO_MOVE_REVIEWED_DUPLICATES",
      reason_codes: ["SAFE_TO_MOVE_REVIEWED_DUPLICATES"],
      operator_explanation: explanation ?? "Keep copy is healthy and the group is approved for movement.",
      extra_summary: {
        health_class: "EXTRAS_ALL_HEALTHY",
        active_count: Number(group.reclaimable_file_count ?? 0),
        healthy_count: Number(group.reclaimable_file_count ?? 0),
        suspect_count: 0,
        broken_count: 0,
        unknown_count: 0,
      },
    }),
  };
}

function renderPage(initialEntry = "/duplicates") {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
      },
    },
  });

  return render(
    <MemoryRouter initialEntries={[initialEntry]}>
      <QueryClientProvider client={queryClient}>
        <DuplicatesPage />
      </QueryClientProvider>
    </MemoryRouter>,
  );
}

describe("DuplicatesPage", () => {
  let groupsData: ReturnType<typeof buildGroup>[];
  let reclaimItemsData: Array<Record<string, unknown>>;
  let reclaimItemsTotalCount: number;
  let duplicateBinItemsPageSize: number;

  beforeEach(() => {
    groupsData = [
      buildGroup("group-alpha", "alpha-main.jpg", ["alpha-copy.jpg", "alpha-copy-2.jpg"]),
      buildGroup("group-beta", "beta-main.jpg", ["beta-copy.jpg"]),
      buildGroup("group-gamma", "gamma-main.jpg", ["gamma-copy.jpg"]),
    ];
    reclaimItemsData = [];
    reclaimItemsTotalCount = 0;
    duplicateBinItemsPageSize = 50;
    mocks.getDuplicates.mockImplementation(async () => ({ data: groupsData }));
    mocks.getDuplicateBinPolicy.mockResolvedValue({
      data: {
        current_move_root: "/tmp/media-manager/recycle-bin",
        current_retention_days: 21,
        target_recycle_bin_root: "/tmp/media-manager/recycle-bin",
        implementation: "reclaim_compatibility",
      },
    });
    mocks.getDuplicateBinItems.mockImplementation(async (params?: { page?: number; limit?: number }) => {
      const page = params?.page ?? 1;
      const limit = params?.limit ?? duplicateBinItemsPageSize;
      const totalCount = reclaimItemsTotalCount || reclaimItemsData.length;
      return {
        data: {
          total: totalCount,
          page,
          page_size: limit,
          total_pages: Math.max(1, Math.ceil(totalCount / limit)),
          items: reclaimItemsData,
        },
      };
    });
    mocks.getIntegrityIssues.mockResolvedValue({ data: { items: [] } });
    mocks.moveDuplicatesToBin.mockResolvedValue({
      data: { summary: { applied_count: 1, skipped_count: 0, moves_count: 1 } },
    });
    mocks.restoreDuplicatesFromBin.mockResolvedValue({
      data: { summary: { applied_count: 1, skipped_count: 0, moves_count: 1 } },
    });
    mocks.setDuplicateReclaim.mockImplementation(
      async (payload: { content_id: string; reclaim_status: string }) => {
        groupsData = groupsData.map((group) =>
          group.group_id === payload.content_id
            ? {
                ...group,
                reclaim_status: payload.reclaim_status,
              }
            : group,
        );
        return { data: { reclaim_status: payload.reclaim_status } };
      },
    );
    mocks.setDuplicateReview.mockImplementation(
      async (payload: { content_id: string; review_status: string; reviewed_canonical_instance_id: string }) => {
        groupsData = groupsData.map((group) =>
          group.group_id === payload.content_id
            ? {
                ...group,
                review_status: payload.review_status,
                reviewed_at: "2026-03-21T10:00:00+00:00",
                reviewed_canonical_instance_id: payload.reviewed_canonical_instance_id,
                is_stale: false,
                stale_reason: null,
              }
            : group,
        );
        return { data: {} };
      },
    );
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it("defaults to the review tab with comparison content dominant and no Recycle Bin actions", async () => {
    renderPage();

    expect(await screen.findByRole("heading", { name: "Review duplicates" })).toBeInTheDocument();
    expect(screen.getByTestId("review-group-navigation-hidden")).toBeInTheDocument();
    expect(screen.getAllByText("alpha-main.jpg").length).toBeGreaterThan(0);
    expect(screen.getByRole("button", { name: "Back" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Next" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Mark as looks right" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Move to Recycle Bin" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Mark safe to remove" })).not.toBeInTheDocument();
  });

  it("shows the system recommendation separately from the human review state on Review duplicates", async () => {
    groupsData = [
      {
        ...buildGroup("group-alpha", "alpha-main.jpg", ["alpha-copy.jpg"]),
        review_status: "looks_right",
        duplicate_recommendation: buildRecommendation({
          state: "SAFE_TO_MOVE_EXTRAS",
          classification: "INFO",
          primary_reason_code: "EXTRA_COPIES_UNHEALTHY_ONLY",
          reason_codes: ["EXTRA_COPIES_UNHEALTHY_ONLY"],
          operator_explanation: "Keep copy is healthy. Some extras have playback issues, but extras can still move.",
          extra_summary: {
            health_class: "EXTRAS_ALL_UNHEALTHY",
            active_count: 1,
            healthy_count: 0,
            suspect_count: 0,
            broken_count: 1,
            unknown_count: 0,
          },
        }),
      },
    ];
    mocks.getDuplicates.mockImplementation(async () => ({ data: groupsData }));

    renderPage();
    fireEvent.click(await screen.findByRole("button", { name: "Looks right" }));

    expect(await screen.findByTestId("review-recommendation-card")).toBeInTheDocument();
    expect(screen.getByTestId("review-recommendation-card")).toHaveTextContent("System recommendation");
    expect(screen.getByTestId("review-recommendation-card")).toHaveTextContent("Safe to move extra copies");
    expect(screen.getByTestId("review-recommendation-card")).toHaveTextContent(
      "Keep copy is healthy. Some extras have playback issues, but extras can still move.",
    );
    expect(screen.getByTestId("review-recommendation-details")).toHaveTextContent(
      "Keep copy is healthy. Some extras have playback issues, but extras can still move.",
    );
    expect(screen.getByTestId("review-recommendation-reasons")).toHaveTextContent("Extra copies have playback issues");
    expect(screen.getByTestId("review-human-review-card")).toHaveTextContent("Human review");
    expect(screen.getByTestId("review-human-review-card")).toHaveTextContent("Looks right");
    expect(screen.getByTestId("review-human-review-card")).not.toHaveTextContent("Extra copies have playback issues");
  });

  it("toggles the side navigation open and closed without breaking the comparison area", async () => {
    renderPage();

    expect(await screen.findByTestId("primary-comparison-preview")).toBeInTheDocument();
    expect(screen.queryByTestId("review-group-navigation")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Show group navigation" }));

    expect(await screen.findByTestId("review-group-navigation")).toBeInTheDocument();
    expect(screen.getByText("Group navigation")).toBeInTheDocument();
    expect(screen.getByTestId("primary-comparison-preview")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Hide group navigation" }));

    await waitFor(() => expect(screen.queryByTestId("review-group-navigation")).not.toBeInTheDocument());
    expect(screen.getByTestId("primary-comparison-preview")).toBeInTheDocument();
  });

  it("keeps group jumping working through the secondary navigation panel", async () => {
    renderPage();

    fireEvent.click(await screen.findByRole("button", { name: "Show group navigation" }));
    fireEvent.click(screen.getByRole("button", { name: /beta-main\.jpg/i }));

    await waitFor(() => expect(screen.getByTestId("review-group-title")).toHaveTextContent("beta-main.jpg"));
  });

  it("uses Back and Next as first-class review navigation controls", async () => {
    renderPage();

    expect(await screen.findByTestId("review-group-title")).toHaveTextContent("alpha-main.jpg");
    expect(screen.getByRole("button", { name: "Back" })).toBeDisabled();

    fireEvent.click(screen.getByRole("button", { name: "Next" }));
    await waitFor(() => expect(screen.getByTestId("review-group-title")).toHaveTextContent("beta-main.jpg"));

    fireEvent.click(screen.getByRole("button", { name: "Back" }));
    await waitFor(() => expect(screen.getByTestId("review-group-title")).toHaveTextContent("alpha-main.jpg"));
  });

  it("marks a group and auto-advances to the next one on the review tab", async () => {
    renderPage();

    expect((await screen.findAllByText("alpha-main.jpg")).length).toBeGreaterThan(0);

    fireEvent.click(screen.getByRole("button", { name: "Mark as looks right" }));

    await waitFor(() => {
      expect(screen.getByText("2 of 3")).toBeInTheDocument();
      expect(mocks.setDuplicateReclaim).toHaveBeenCalledWith({
        content_id: "group-alpha",
        reclaim_status: "REVIEWED_SAFE_TO_RECLAIM",
      });
    });
  });

  it("filters the review queue by review mark after a group has been reviewed", async () => {
    renderPage();

    expect((await screen.findAllByText("alpha-main.jpg")).length).toBeGreaterThan(0);
    fireEvent.click(screen.getByRole("button", { name: "Mark as looks right" }));

    await waitFor(() => expect(screen.getByText("2 of 3")).toBeInTheDocument());

    fireEvent.click(screen.getByRole("button", { name: "Looks right" }));

    await waitFor(() => {
      expect(screen.getAllByText("alpha-main.jpg").length).toBeGreaterThan(0);
      expect(screen.queryAllByText("beta-main.jpg")).toHaveLength(0);
    });
  });

  it("ignores marking shortcuts when focus is inside an input", async () => {
    renderPage();

    expect(await screen.findByText("1 of 3")).toBeInTheDocument();

    const input = document.createElement("input");
    document.body.appendChild(input);
    input.focus();

    fireEvent.keyDown(input, { key: "2", bubbles: true });
    expect(screen.getByText("1 of 3")).toBeInTheDocument();

    fireEvent.keyDown(window, { key: "2" });

    await waitFor(() => expect(screen.getByText("2 of 3")).toBeInTheDocument());
    document.body.removeChild(input);
  });

  it("updates the active comparison pane when a duplicate thumbnail is selected", async () => {
    renderPage();

    expect(await screen.findByTestId("secondary-comparison-title")).toHaveTextContent("Extra copy: alpha-copy.jpg");

    fireEvent.click(screen.getByRole("button", { name: "Compare duplicate 2: alpha-copy-2.jpg" }));

    await waitFor(() => {
      expect(screen.getByTestId("secondary-comparison-title")).toHaveTextContent("Extra copy: alpha-copy-2.jpg");
      expect(screen.getByTestId("active-duplicate-caption")).toHaveTextContent("Comparing: alpha-copy-2.jpg");
      expect(screen.getByRole("button", { name: "Compare duplicate 2: alpha-copy-2.jpg" })).toHaveAttribute("aria-pressed", "true");
    });

    const preview = screen.getByTestId("secondary-comparison-preview");
    expect(within(preview).getByRole("img", { name: "alpha-copy-2.jpg" })).toHaveAttribute(
      "src",
      "/api/thumbnail/group-alpha-duplicate-1",
    );
  });

  it("renders the secondary navigation as a text-only list without thumbnails", async () => {
    renderPage();

    fireEvent.click(await screen.findByRole("button", { name: "Show group navigation" }));

    const navigation = await screen.findByTestId("review-group-navigation");
    expect(within(navigation).getAllByTestId("review-queue-no-thumbnails").length).toBeGreaterThan(0);
    expect(within(navigation).queryByRole("img")).toBeNull();
  });

  it("maps the legacy removal deep link to Ready for Bin and keeps restore actions separate", async () => {
    groupsData = [
      markGroupSafeToMove(buildGroup("group-alpha", "alpha-main.jpg", ["alpha-copy.jpg"])),
    ];
    mocks.getDuplicates.mockImplementation(async () => ({ data: groupsData }));

    renderPage("/duplicates?tab=removal");

    expect(await screen.findByRole("heading", { name: "Ready for Bin" })).toBeInTheDocument();
    expect(screen.getAllByText("Ready for Bin").length).toBeGreaterThan(0);
    expect(screen.getByTestId("ready-for-bin-view-focus")).toBeInTheDocument();
    expect(screen.getByTestId("ready-for-bin-focused-panel")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Move to Recycle Bin" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Restore from Recycle Bin" })).not.toBeInTheDocument();
    expect(
      screen.getByText(
        "These groups are currently recommended as safe to move into the Recycle Bin. Restore happens only on the Recycle Bin tab.",
      ),
    ).toBeInTheDocument();
  });

  it("uses SAFE_TO_MOVE_EXTRAS as the only Ready for Bin bucket filter", async () => {
    groupsData = [
      markGroupSafeToMove(buildGroup("group-alpha", "alpha-main.jpg", ["alpha-copy.jpg"])),
      {
        ...buildGroup("group-safe-warning", "safe-warning-main.jpg", ["safe-warning-copy.jpg"]),
        duplicate_recommendation: buildRecommendation({
          state: "SAFE_TO_MOVE_EXTRAS",
          classification: "INFO",
          primary_reason_code: "EXTRA_COPIES_UNHEALTHY_ONLY",
          reason_codes: ["EXTRA_COPIES_UNHEALTHY_ONLY"],
          operator_explanation: "Keep copy is healthy. Some extras have playback issues, but extras can still move.",
          review_is_stale: true,
          integrity_is_stale: true,
        }),
      },
      {
        ...buildGroup("group-beta", "beta-main.jpg", ["beta-copy.jpg"]),
        duplicate_recommendation: buildRecommendation({
          state: "REVIEW_REQUIRED",
          classification: "WARN",
          primary_reason_code: "KEEP_COPY_UNKNOWN",
          reason_codes: ["KEEP_COPY_UNKNOWN"],
          operator_explanation: "Keep copy health is not confirmed yet. Refresh integrity evidence first.",
        }),
      },
      {
        ...buildGroup("group-gamma", "gamma-main.jpg", ["gamma-copy.jpg"]),
        duplicate_recommendation: buildRecommendation({
          state: "DO_NOT_MOVE",
          classification: "BLOCK",
          primary_reason_code: "KEEP_COPY_UNHEALTHY",
          reason_codes: ["KEEP_COPY_UNHEALTHY"],
          operator_explanation: "The keep copy has playback issues. Do not move extras yet.",
        }),
      },
      {
        ...buildGroup("group-delta", "delta-main.jpg", ["delta-copy.jpg"]),
        duplicate_recommendation: buildRecommendation({
          state: "ALREADY_IN_BIN",
          classification: "INFO",
          primary_reason_code: "GROUP_ALREADY_IN_BIN",
          reason_codes: ["GROUP_ALREADY_IN_BIN"],
          operator_explanation: "This group is already in the bin. Manage it there instead of moving it again.",
        }),
      },
      {
        ...buildGroup("group-epsilon", "epsilon-main.jpg", ["epsilon-copy.jpg"]),
        duplicate_recommendation: buildRecommendation({
          state: "EXPIRED_IN_BIN",
          classification: "INFO",
          primary_reason_code: "BIN_RESTORE_EXPIRED",
          reason_codes: ["BIN_RESTORE_EXPIRED"],
          operator_explanation: "This group is already in the bin and the restore window has expired.",
        }),
      },
      {
        ...buildGroup("group-favorable-looking", "favorable-main.jpg", ["favorable-copy.jpg"]),
        duplicate_recommendation: buildRecommendation({
          state: "REVIEW_REQUIRED",
          classification: "WARN",
          primary_reason_code: "SAFE_TO_MOVE_REVIEWED_DUPLICATES",
          reason_codes: ["SAFE_TO_MOVE_REVIEWED_DUPLICATES"],
          operator_explanation: "Keep copy is healthy and the group is approved for movement.",
          review_is_stale: false,
          integrity_is_stale: false,
        }),
      },
    ];
    mocks.getDuplicates.mockImplementation(async () => ({ data: groupsData }));

    renderPage("/duplicates?tab=ready-for-bin");
    fireEvent.click(await screen.findByTestId("ready-for-bin-view-gallery"));

    expect(await screen.findByTestId("ready-for-bin-gallery-card-group-alpha")).toBeInTheDocument();
    expect(screen.getByTestId("ready-for-bin-gallery-card-group-safe-warning")).toBeInTheDocument();
    expect(screen.queryByTestId("ready-for-bin-gallery-card-group-beta")).not.toBeInTheDocument();
    expect(screen.queryByTestId("ready-for-bin-gallery-card-group-gamma")).not.toBeInTheDocument();
    expect(screen.queryByTestId("ready-for-bin-gallery-card-group-delta")).not.toBeInTheDocument();
    expect(screen.queryByTestId("ready-for-bin-gallery-card-group-epsilon")).not.toBeInTheDocument();
    expect(screen.queryByTestId("ready-for-bin-gallery-card-group-favorable-looking")).not.toBeInTheDocument();
  });

  it("defaults Ready for Bin to Focus and Recycle Bin to Gallery, with quiet alternate toggles", async () => {
    groupsData = [
      markGroupSafeToMove(buildGroup("group-alpha", "alpha-main.jpg", ["alpha-copy.jpg"])),
      {
        ...buildGroup("group-beta", "beta-main.jpg", ["beta-copy.jpg"]),
        review_status: "needs_review",
      },
      {
        ...buildGroup("group-gamma", "gamma-main.jpg", ["gamma-copy.jpg"]),
        review_status: "looks_right",
      },
    ];
    reclaimItemsData = [
      {
        file_instance_id: "archived-1",
        content_id: "group-gamma",
        original_path: "/library/gamma-copy.jpg",
        archive_path: "/archive/gamma-copy.jpg",
        item_status: "ARCHIVED",
        expires_at: "2026-04-10T10:00:00+00:00",
      },
    ];
    mocks.getDuplicates.mockImplementation(async () => ({ data: groupsData }));

    const processView = renderPage("/duplicates?tab=ready-for-bin");

    expect(await screen.findByTestId("ready-for-bin-focused-panel")).toBeInTheDocument();
    expect(screen.queryByTestId("ready-for-bin-gallery")).not.toBeInTheDocument();
    expect(screen.queryByTestId("ready-for-bin-list")).not.toBeInTheDocument();

    fireEvent.click(screen.getByTestId("ready-for-bin-view-gallery"));

    await waitFor(() => {
      expect(screen.queryByTestId("ready-for-bin-focused-panel")).not.toBeInTheDocument();
      expect(screen.getByTestId("ready-for-bin-gallery")).toBeInTheDocument();
      expect(screen.queryByText("Needs review before moving to Recycle Bin")).not.toBeInTheDocument();
    });

    processView.unmount();

    renderPage("/duplicates?tab=recycle-bin");

    expect(await screen.findByRole("heading", { name: "Recycle Bin" })).toBeInTheDocument();
    expect(screen.getByTestId("recycle-bin-gallery")).toBeInTheDocument();
    expect(screen.queryByTestId("recycle-bin-list")).not.toBeInTheDocument();
    expect(screen.queryByTestId("recycle-bin-focused-panel")).not.toBeInTheDocument();

    await waitFor(() => {
      expect(screen.getAllByText("In Recycle Bin").length).toBeGreaterThan(0);
    });

    fireEvent.click(screen.getByTestId("recycle-bin-view-list"));

    await waitFor(() => {
      expect(screen.getByTestId("recycle-bin-list")).toBeInTheDocument();
    });
  });

  it("keeps expired Recycle Bin items visible but disables restore after the restore window ends", async () => {
    reclaimItemsData = [
      {
        file_instance_id: "archived-restorable",
        content_id: "group-alpha",
        original_path: "/library/alpha-copy.jpg",
        archive_path: "/archive/alpha-copy.jpg",
        item_status: "ARCHIVED",
        expires_at: "2099-04-10T10:00:00+00:00",
      },
      {
        file_instance_id: "archived-expired",
        content_id: "group-beta",
        original_path: "/library/beta-copy.jpg",
        archive_path: "/archive/beta-copy.jpg",
        item_status: "ARCHIVED",
        expires_at: "2020-04-10T10:00:00+00:00",
      },
    ];

    renderPage("/duplicates?tab=recycle-bin");

    expect(await screen.findByTestId("recycle-bin-gallery")).toBeInTheDocument();
    expect(screen.getAllByText("Restore window ended").length).toBeGreaterThan(0);
    expect(screen.getByText("Expired")).toBeInTheDocument();

    const restoreButtons = screen.getAllByRole("button", { name: "Restore from Recycle Bin" });
    expect(restoreButtons).toHaveLength(2);
    expect(restoreButtons[0]).toBeEnabled();
    expect(restoreButtons[1]).toBeDisabled();
  });

  it("shows truthful global recycle-bin totals, labels page-scoped restore counts, and paginates independently of view mode", async () => {
    reclaimItemsTotalCount = 75;
    mocks.getDuplicateBinItems.mockImplementation(async (params?: { page?: number; limit?: number }) => {
      const page = params?.page ?? 1;
      const limit = params?.limit ?? 50;
      const items =
        page === 1
          ? Array.from({ length: 50 }, (_, index) => ({
              file_instance_id: `archived-${index + 1}`,
              content_id: index % 2 === 0 ? "group-alpha" : "group-beta",
              original_path: `/library/item-${index + 1}.jpg`,
              archive_path: `/archive/item-${index + 1}.jpg`,
              item_status: "ARCHIVED",
              expires_at: index < 30 ? "2099-04-10T10:00:00+00:00" : "2020-04-10T10:00:00+00:00",
            }))
          : Array.from({ length: 25 }, (_, index) => ({
              file_instance_id: `archived-page2-${index + 1}`,
              content_id: "group-gamma",
              original_path: `/library/page2-item-${index + 1}.jpg`,
              archive_path: `/archive/page2-item-${index + 1}.jpg`,
              item_status: "ARCHIVED",
              expires_at: "2099-04-10T10:00:00+00:00",
            }));
      return {
        data: {
          total: 75,
          page,
          page_size: limit,
          total_pages: 2,
          items,
        },
      };
    });

    renderPage("/duplicates?tab=recycle-bin");

    expect(await screen.findByRole("heading", { name: "Recycle Bin" })).toBeInTheDocument();
    expect(screen.getByText("These extra copies still physically exist in the Recycle Bin across all pages.")).toBeInTheDocument();
    expect(screen.getByText("Restore available on this page")).toBeInTheDocument();
    expect(screen.getByText("Restore window ended on this page")).toBeInTheDocument();
    expect(screen.getByText("Showing page 1 of 2 for Recycle Bin items.")).toBeInTheDocument();
    expect(screen.getByTestId("recycle-bin-gallery")).toBeInTheDocument();
    expect(screen.getAllByText("75").length).toBeGreaterThan(0);

    fireEvent.click(screen.getByTestId("recycle-bin-view-focus"));
    expect(await screen.findByTestId("recycle-bin-focused-panel")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Next page" }));

    await waitFor(() => {
      expect(mocks.getDuplicateBinItems).toHaveBeenCalledWith({ page: 2, limit: 50 });
      expect(screen.getByText("Showing page 2 of 2 for Recycle Bin items.")).toBeInTheDocument();
      expect(screen.getByTestId("recycle-bin-focused-title")).toHaveTextContent("page2-item-1.jpg");
    });

    fireEvent.click(screen.getByTestId("recycle-bin-view-gallery"));

    await waitFor(() => {
      expect(screen.getByTestId("recycle-bin-gallery")).toBeInTheDocument();
      expect(screen.getByText("Showing page 2 of 2 for Recycle Bin items.")).toBeInTheDocument();
    });
  });

  it("uses the mapped global pagination total for the In Recycle Bin KPI instead of the loaded page length", async () => {
    mocks.getDuplicateBinItems.mockResolvedValue({
      data: {
        total: 903,
        page: 1,
        page_size: 50,
        total_pages: 19,
        items: Array.from({ length: 50 }, (_, index) => ({
          file_instance_id: `archived-${index + 1}`,
          content_id: index % 2 === 0 ? "group-alpha" : "group-beta",
          original_path: `/library/item-${index + 1}.jpg`,
          archive_path: `/archive/item-${index + 1}.jpg`,
          item_status: "ARCHIVED",
          expires_at: "2099-04-10T10:00:00+00:00",
        })),
      },
    });

    renderPage("/duplicates?tab=recycle-bin");

    expect(await screen.findByRole("heading", { name: "Recycle Bin" })).toBeInTheDocument();
    expect(screen.getByText("These extra copies still physically exist in the Recycle Bin across all pages.")).toBeInTheDocument();
    expect(screen.getByText("Restore available on this page")).toBeInTheDocument();
    expect(screen.getAllByText("903").length).toBeGreaterThan(0);
    expect(screen.getAllByText("50").length).toBeGreaterThan(0);
    expect(screen.getByText("Showing page 1 of 19 for Recycle Bin items.")).toBeInTheDocument();
  });

  it("supports focused Previous and Next navigation across ready groups on Ready for Bin", async () => {
    groupsData = [
      markGroupSafeToMove(buildGroup("group-alpha", "alpha-main.jpg", ["alpha-copy.jpg"])),
      markGroupSafeToMove(buildGroup("group-beta", "beta-main.jpg", ["beta-copy.jpg"])),
      buildGroup("group-gamma", "gamma-main.jpg", ["gamma-copy.jpg"]),
    ];
    mocks.getDuplicates.mockImplementation(async () => ({ data: groupsData }));

    renderPage("/duplicates?tab=ready-for-bin");

    expect(await screen.findByTestId("ready-for-bin-focused-panel")).toBeInTheDocument();
    expect(screen.getByTestId("ready-for-bin-focused-title")).toHaveTextContent("alpha-main.jpg");
    expect(screen.getAllByText("Keep copy").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Extra copies").length).toBeGreaterThan(0);
    expect(screen.queryByRole("button", { name: "Select current group" })).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Next" }));

    await waitFor(() => expect(screen.getByTestId("ready-for-bin-focused-title")).toHaveTextContent("beta-main.jpg"));

    fireEvent.click(screen.getByRole("button", { name: "Previous" }));
    await waitFor(() => expect(screen.getByTestId("ready-for-bin-focused-title")).toHaveTextContent("alpha-main.jpg"));
  });

  it("supports group-level multi-select in Gallery and moves only the selected groups", async () => {
    groupsData = [
      markGroupSafeToMove(buildGroup("group-alpha", "alpha-main.jpg", ["alpha-copy.jpg"])),
      markGroupSafeToMove(buildGroup("group-beta", "beta-main.jpg", ["beta-copy.jpg"])),
      buildGroup("group-gamma", "gamma-main.jpg", ["gamma-copy.jpg"]),
    ];
    mocks.getDuplicates.mockImplementation(async () => ({ data: groupsData }));
    mocks.moveDuplicatesToBin.mockResolvedValue({
      data: { summary: { applied_count: 2, skipped_count: 0, moves_count: 2 } },
    });

    renderPage("/duplicates?tab=ready-for-bin");

    fireEvent.click(await screen.findByTestId("ready-for-bin-view-gallery"));

    expect(await screen.findByTestId("ready-for-bin-gallery-card-group-alpha")).toBeInTheDocument();
    fireEvent.click(screen.getByLabelText("Select group alpha-main.jpg"));
    fireEvent.click(screen.getByLabelText("Select group beta-main.jpg"));

    expect(screen.getByTestId("ready-for-bin-bulk-action-bar")).toBeInTheDocument();
    expect(screen.getByText("2 selected groups")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Move selected groups" }));

    await waitFor(() => {
      expect(mocks.moveDuplicatesToBin).toHaveBeenCalledWith({
        content_ids: ["group-alpha", "group-beta"],
        retention_days: 21,
      });
      expect(
        screen.getByText("2 duplicate files moved from 2 groups into the Recycle Bin. The keep copy stayed in place."),
      ).toBeInTheDocument();
    });
  });

  it("does not keep already processed groups selectable in Ready for Bin", async () => {
    groupsData = [
      {
        ...buildGroup("group-alpha", "alpha-main.jpg", ["alpha-copy.jpg"]),
        review_status: "looks_right",
        duplicate_recommendation: buildRecommendation({
          state: "ALREADY_IN_BIN",
          classification: "INFO",
          primary_reason_code: "GROUP_ALREADY_IN_BIN",
          reason_codes: ["GROUP_ALREADY_IN_BIN"],
          operator_explanation: "This group is already in the bin. Manage it there instead of moving it again.",
        }),
        reclaim_status: "REVIEWED_SAFE_TO_RECLAIM",
      },
      markGroupSafeToMove(buildGroup("group-beta", "beta-main.jpg", ["beta-copy.jpg"])),
    ];
    reclaimItemsData = [
      {
        file_instance_id: "group-alpha-duplicate-0",
        content_id: "group-alpha",
        original_path: "/library/alpha-copy.jpg",
        archive_path: "/tmp/media-manager/reclaim/group-alpha/group-alpha-duplicate-0-alpha-copy.jpg",
        item_status: "ARCHIVED",
        expires_at: "2026-04-10T10:00:00+00:00",
      },
    ];
    mocks.getDuplicates.mockImplementation(async () => ({ data: groupsData }));

    renderPage("/duplicates?tab=ready-for-bin");

    fireEvent.click(await screen.findByTestId("ready-for-bin-view-gallery"));

    expect(await screen.findByTestId("ready-for-bin-gallery")).toBeInTheDocument();
    expect(screen.queryByTestId("ready-for-bin-gallery-card-group-alpha")).not.toBeInTheDocument();
    expect(screen.getByTestId("ready-for-bin-gallery-card-group-beta")).toBeInTheDocument();
  });

  it("keeps planner-blocked groups out of Ready for Bin and explains the missing keep-copy mapping", async () => {
    groupsData = [
      {
        ...buildGroup("group-alpha", "alpha-main.jpg", ["alpha-copy.jpg"]),
        review_status: "looks_right",
        duplicate_recommendation: buildRecommendation({
          state: "DO_NOT_MOVE",
          classification: "BLOCK",
          primary_reason_code: "CANONICAL_MAPPING_MISSING",
          reason_codes: ["CANONICAL_MAPPING_MISSING"],
          operator_explanation: "The keep copy is not clearly identified. Resolve canonical mapping first.",
        }),
        reclaim_status: "REVIEWED_SAFE_TO_RECLAIM",
        duplicate_reclaim_actionable: false,
        duplicate_reclaim_unavailable_reason: "missing_canonical_file_content_mapping",
      },
      {
        ...markGroupSafeToMove(buildGroup("group-beta", "beta-main.jpg", ["beta-copy.jpg"])),
        reclaim_status: "REVIEWED_SAFE_TO_RECLAIM",
        duplicate_reclaim_actionable: true,
      },
    ];
    mocks.getDuplicates.mockImplementation(async () => ({ data: groupsData }));

    renderPage("/duplicates?tab=ready-for-bin");

    fireEvent.click(await screen.findByTestId("ready-for-bin-view-gallery"));

    expect(await screen.findByTestId("ready-for-bin-gallery")).toBeInTheDocument();
    expect(screen.queryByTestId("ready-for-bin-gallery-card-group-alpha")).not.toBeInTheDocument();
    expect(screen.getByTestId("ready-for-bin-gallery-card-group-beta")).toBeInTheDocument();
    expect(screen.queryByText("This group cannot move yet because the planner could not confirm a keep-copy mapping.")).not.toBeInTheDocument();
  });

  it("uses Looks right groups as the only move-eligible groups and shows move and restore feedback", async () => {
    groupsData = [
      markGroupSafeToMove(buildGroup("group-alpha", "alpha-main.jpg", ["alpha-copy.jpg"])),
      buildGroup("group-beta", "beta-main.jpg", ["beta-copy.jpg"]),
    ];
    mocks.getDuplicates.mockImplementation(async () => ({ data: groupsData }));
    reclaimItemsData = [];
    mocks.moveDuplicatesToBin.mockImplementation(async () => {
      groupsData = groupsData.map((group) =>
        group.group_id === "group-alpha"
          ? {
              ...group,
              reclaim_status: "ARCHIVED",
            }
          : group,
      );
      reclaimItemsData = [
        ...reclaimItemsData,
        {
          file_instance_id: "group-alpha-duplicate-0",
          content_id: "group-alpha",
          original_path: "/library/alpha-copy.jpg",
          archive_path: "/tmp/media-manager/reclaim/group-alpha/group-alpha-duplicate-0-alpha-copy.jpg",
          item_status: "ARCHIVED",
          expires_at: "2026-04-10T10:00:00+00:00",
        },
      ];
      return { data: { summary: { applied_count: 1, skipped_count: 0, moves_count: 1 } } };
    });
    mocks.restoreDuplicatesFromBin.mockImplementation(async () => {
      groupsData = groupsData.map((group) =>
        group.group_id === "group-alpha"
          ? {
              ...group,
              reclaim_status: "RESTORED",
            }
          : group,
      );
      reclaimItemsData = reclaimItemsData.map((item) =>
        item.file_instance_id === "group-alpha-duplicate-0"
          ? {
              ...item,
              item_status: "RESTORED",
            }
          : item,
      );
      return { data: { summary: { applied_count: 1, skipped_count: 0, moves_count: 1 } } };
    });

    const processView = renderPage("/duplicates?tab=ready-for-bin");

    expect(
      await screen.findByText("This workflow view is filtered from the backend recommendation. The keep copy always stays in place."),
    ).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Mark safe to remove" })).not.toBeInTheDocument();
    expect(screen.getAllByText("alpha-main.jpg").length).toBeGreaterThan(0);
    expect(screen.queryByText("beta-main.jpg")).not.toBeInTheDocument();

    fireEvent.click(screen.getByTestId("ready-for-bin-view-gallery"));
    fireEvent.click(screen.getByRole("button", { name: "Move all eligible groups" }));

    await waitFor(() => {
      expect(mocks.setDuplicateReclaim).toHaveBeenCalledWith({
        content_id: "group-alpha",
        reclaim_status: "REVIEWED_SAFE_TO_RECLAIM",
      });
      expect(mocks.moveDuplicatesToBin).toHaveBeenCalledWith({
        content_ids: ["group-alpha"],
        retention_days: 21,
      });
      expect(
        screen.getByText("1 duplicate file moved from 1 group into the Recycle Bin. The keep copy stayed in place."),
      ).toBeInTheDocument();
    });

    processView.unmount();
    renderPage("/duplicates?tab=recycle-bin");

    fireEvent.click(await screen.findByRole("button", { name: "Restore from Recycle Bin" }));

    await waitFor(() => {
      expect(mocks.restoreDuplicatesFromBin).toHaveBeenCalledWith({
        file_instance_ids: ["group-alpha-duplicate-0"],
      });
      expect(
        screen.getByText(
          "1 file restored from the Recycle Bin. Restored groups stay out of Ready for Bin until they are reviewed again.",
        ),
      ).toBeInTheDocument();
      expect(screen.getByText("No duplicate files are in the Recycle Bin right now.")).toBeInTheDocument();
    });
  });

  it("refreshes recycle-bin data on page 1 after a successful bulk move", async () => {
    groupsData = [
      markGroupSafeToMove(buildGroup("group-alpha", "alpha-main.jpg", ["alpha-copy.jpg"])),
    ];
    mocks.getDuplicates.mockImplementation(async () => ({ data: groupsData }));
    let moved = false;
    mocks.getDuplicateBinItems.mockImplementation(async (params?: { page?: number; limit?: number }) => {
      const page = params?.page ?? 1;
      return {
        data: {
          total: moved ? 60 : 0,
          page,
          page_size: params?.limit ?? 50,
          total_pages: moved ? 2 : 1,
          items:
            !moved
              ? []
              : page === 1
              ? [
                  {
                    file_instance_id: "group-alpha-duplicate-0",
                    content_id: "group-alpha",
                    original_path: "/library/alpha-copy.jpg",
                    archive_path: "/archive/alpha-copy.jpg",
                    item_status: "ARCHIVED",
                    expires_at: "2099-04-10T10:00:00+00:00",
                  },
                ]
              : [
                  {
                    file_instance_id: "older-item",
                    content_id: "group-beta",
                    original_path: "/library/older-item.jpg",
                    archive_path: "/archive/older-item.jpg",
                    item_status: "ARCHIVED",
                    expires_at: "2099-04-10T10:00:00+00:00",
                  },
                ],
        },
      };
    });
    mocks.moveDuplicatesToBin.mockImplementation(async () => {
      moved = true;
      return { data: { summary: { applied_count: 1, skipped_count: 0, moves_count: 1 } } };
    });

    renderPage("/duplicates?tab=ready-for-bin");

    fireEvent.click(await screen.findByTestId("ready-for-bin-view-gallery"));
    fireEvent.click(screen.getByRole("button", { name: "Move all eligible groups" }));

    await waitFor(() => {
      expect(mocks.moveDuplicatesToBin).toHaveBeenCalledWith({
        content_ids: ["group-alpha"],
        retention_days: 21,
      });
      expect(mocks.getDuplicateBinItems).toHaveBeenCalledWith({ page: 1, limit: 50 });
      expect(screen.getByText("1 duplicate file moved from 1 group into the Recycle Bin. The keep copy stayed in place.")).toBeInTheDocument();
    });
  });

  it("shows explicit sync failure feedback and blocks the move action when the bridge update fails", async () => {
    groupsData = [
      markGroupSafeToMove(buildGroup("group-alpha", "alpha-main.jpg", ["alpha-copy.jpg"])),
    ];
    mocks.getDuplicates.mockImplementation(async () => ({ data: groupsData }));
    mocks.setDuplicateReclaim.mockRejectedValue(new Error("bridge failed"));

    renderPage("/duplicates?tab=ready-for-bin");

    fireEvent.click(await screen.findByRole("button", { name: "Move to Recycle Bin" }));

    await waitFor(() => {
      expect(mocks.setDuplicateReclaim).toHaveBeenCalledWith({
        content_id: "group-alpha",
        reclaim_status: "REVIEWED_SAFE_TO_RECLAIM",
      });
      expect(mocks.moveDuplicatesToBin).not.toHaveBeenCalled();
      expect(
        screen.getAllByText(
          "Saved “Looks right” for alpha-main.jpg, but the app could not confirm move eligibility. Try again before moving duplicates.",
        ).length,
      ).toBeGreaterThan(0);
    });
  });

  it("shows explicit planned-but-skipped feedback when the move plans work but apply skips the file action", async () => {
    groupsData = [
      {
        ...markGroupSafeToMove(buildGroup("group-alpha", "alpha-main.jpg", ["alpha-copy.jpg"])),
        reclaim_status: "REVIEWED_SAFE_TO_RECLAIM",
      },
    ];
    mocks.getDuplicates.mockImplementation(async () => ({ data: groupsData }));
    mocks.moveDuplicatesToBin.mockResolvedValue({
      data: {
        summary: { applied_count: 0, skipped_count: 1, moves_count: 0 },
        diagnostics: { planned_action_count: 1, applied_count: 0, skipped_count: 1, result_type: "planned_skipped" },
      },
    });

    renderPage("/duplicates?tab=ready-for-bin");

    fireEvent.click(await screen.findByTestId("ready-for-bin-view-gallery"));
    fireEvent.click(await screen.findByLabelText("Select group alpha-main.jpg"));
    fireEvent.click(screen.getByRole("button", { name: "Move selected groups" }));

    await waitFor(() => {
      expect(mocks.moveDuplicatesToBin).toHaveBeenCalledWith({
        content_ids: ["group-alpha"],
        retention_days: 21,
      });
      expect(
        screen.getByText(
          "The selected groups were planned for move, but the duplicate files were skipped during apply. The list has been refreshed.",
        ),
      ).toBeInTheDocument();
      expect(screen.queryByTestId("ready-for-bin-bulk-action-bar")).not.toBeInTheDocument();
      expect(screen.getByTestId("ready-for-bin-gallery-card-group-alpha")).toBeInTheDocument();
    });
  });

  it("shows explicit zero-planned feedback when the backend rejects the selected group before planning", async () => {
    groupsData = [
      {
        ...markGroupSafeToMove(buildGroup("group-alpha", "alpha-main.jpg", ["alpha-copy.jpg"])),
        reclaim_status: "REVIEWED_SAFE_TO_RECLAIM",
      },
    ];
    mocks.getDuplicates.mockImplementation(async () => ({ data: groupsData }));
    mocks.moveDuplicatesToBin.mockResolvedValue({
      data: {
        summary: { applied_count: 0, skipped_count: 0, moves_count: 0 },
        diagnostics: {
          planned_action_count: 0,
          applied_count: 0,
          skipped_count: 0,
          result_type: "zero_planned",
          group_results: [{ content_id: "group-alpha", reason: "missing_canonical_file_content_mapping" }],
        },
      },
    });

    renderPage("/duplicates?tab=ready-for-bin");

    fireEvent.click(await screen.findByTestId("ready-for-bin-view-gallery"));
    fireEvent.click(await screen.findByLabelText("Select group alpha-main.jpg"));
    fireEvent.click(screen.getByRole("button", { name: "Move selected groups" }));

    await waitFor(() => {
      expect(
        screen.getByText(
          "No files were moved from the selected groups because one or more groups no longer had a planner-confirmed keep-copy mapping. The list has been refreshed.",
        ),
      ).toBeInTheDocument();
      expect(screen.queryByTestId("ready-for-bin-bulk-action-bar")).not.toBeInTheDocument();
    });
  });

  it("shows a config warning instead of vague retention claims when policy details are unavailable", async () => {
    mocks.getDuplicateBinPolicy.mockRejectedValue(new Error("policy unavailable"));

    renderPage("/duplicates?tab=ready-for-bin");

    expect(
      await screen.findByText(
        "Recycle Bin details are unavailable right now. The app cannot confirm the configured Recycle Bin location or retention window for this page.",
      ),
    ).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Move to Recycle Bin" })).not.toBeInTheDocument();
    expect(screen.queryByText(/Holding area:/)).not.toBeInTheDocument();
  });

  it("moves a reviewed group back out of Ready for Bin when its review state changes", async () => {
    groupsData = [
      {
        ...markGroupSafeToMove(buildGroup("group-alpha", "alpha-main.jpg", ["alpha-copy.jpg"])),
        reclaim_status: "REVIEWED_SAFE_TO_RECLAIM",
      },
    ];
    mocks.getDuplicates.mockImplementation(async () => ({ data: groupsData }));

    renderPage();

    fireEvent.click(await screen.findByRole("button", { name: "Looks right" }));
    fireEvent.click(await screen.findByRole("button", { name: "Mark as needs review" }));

    await waitFor(() =>
      expect(mocks.setDuplicateReclaim).toHaveBeenCalledWith({
        content_id: "group-alpha",
        reclaim_status: "UNREVIEWED",
      }),
    );
  });

  it("routes restored groups back into Review duplicates with a dedicated Restored filter", async () => {
    groupsData = [
      {
        ...markGroupSafeToMove(buildGroup("group-alpha", "alpha-main.jpg", ["alpha-copy.jpg"])),
        reviewed_at: "2026-03-21T10:00:00+00:00",
        reclaim_status: "RESTORED",
      },
      {
        ...markGroupSafeToMove(buildGroup("group-beta", "beta-main.jpg", ["beta-copy.jpg"])),
        reclaim_status: "REVIEWED_SAFE_TO_RECLAIM",
      },
    ];
    reclaimItemsData = [
      {
        file_instance_id: "group-alpha-duplicate-0",
        content_id: "group-alpha",
        original_path: "/library/alpha-copy.jpg",
        archive_path: "/archive/alpha-copy.jpg",
        item_status: "RESTORED",
        restored_at: "2026-03-22T10:00:00+00:00",
      },
    ];
    mocks.getDuplicates.mockImplementation(async () => ({ data: groupsData }));

    renderPage("/duplicates?tab=ready-for-bin");

    expect(await screen.findByText("1 restored group needs review before it can re-enter Ready for Bin.")).toBeInTheDocument();
    expect(screen.queryByText("Needs review before moving to Recycle Bin")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Review restored groups" }));

    await waitFor(() => {
      expect(screen.getByRole("heading", { name: "Review duplicates" })).toBeInTheDocument();
      expect(screen.getByRole("button", { name: "Restored" })).toBeInTheDocument();
      expect(screen.getAllByText("alpha-main.jpg").length).toBeGreaterThan(0);
      expect(screen.queryByText("beta-main.jpg")).not.toBeInTheDocument();
      expect(screen.getByText("Restored from Recycle Bin")).toBeInTheDocument();
      expect(screen.getByText("Review again before this group can re-enter Ready for Bin.")).toBeInTheDocument();
    });
  });

  it("shows a subdued In Recycle Bin lifecycle indicator only for groups whose extra copies are already moved", async () => {
    groupsData = [
      {
        ...buildGroup("group-alpha", "alpha-main.jpg", ["alpha-copy.jpg"]),
        review_status: "needs_review",
        reclaim_status: "ARCHIVED",
      },
      {
        ...buildGroup("group-beta", "beta-main.jpg", ["beta-copy.jpg"]),
        review_status: "needs_review",
      },
    ];
    reclaimItemsData = [
      {
        file_instance_id: "group-alpha-duplicate-0",
        content_id: "group-alpha",
        original_path: "/library/alpha-copy.jpg",
        archive_path: "/archive/alpha-copy.jpg",
        item_status: "ARCHIVED",
        expires_at: "2099-04-10T10:00:00+00:00",
      },
    ];
    reclaimItemsTotalCount = 1;
    mocks.getDuplicates.mockImplementation(async () => ({ data: groupsData }));

    renderPage("/duplicates?tab=review");

    expect(await screen.findByRole("heading", { name: "Review duplicates" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Needs review" }));
    expect(await screen.findByText("In Recycle Bin")).toBeInTheDocument();
    expect(await screen.findByText("Extra copies are already in the Recycle Bin. The keep copy stays in place.")).toBeInTheDocument();
    expect(screen.getAllByText("Needs review").length).toBeGreaterThan(0);

    fireEvent.click(screen.getByRole("button", { name: "Show group navigation" }));
    const navigation = await screen.findByTestId("review-group-navigation");
    const alphaButton = within(navigation).getByRole("button", { name: /alpha-main\.jpg/i });
    const betaButton = within(navigation).getByRole("button", { name: /beta-main\.jpg/i });

    expect(within(alphaButton).getByText("In Recycle Bin")).toBeInTheDocument();
    expect(within(betaButton).queryByText("In Recycle Bin")).not.toBeInTheDocument();
  });

  it("drops a restored group out of the Restored filter after it is reviewed again and returns it to Ready for Bin", async () => {
    groupsData = [
      {
        ...markGroupSafeToMove(buildGroup("group-alpha", "alpha-main.jpg", ["alpha-copy.jpg"])),
        reviewed_at: "2026-03-21T10:00:00+00:00",
        reclaim_status: "RESTORED",
      },
    ];
    reclaimItemsData = [
      {
        file_instance_id: "group-alpha-duplicate-0",
        content_id: "group-alpha",
        original_path: "/library/alpha-copy.jpg",
        archive_path: "/archive/alpha-copy.jpg",
        item_status: "RESTORED",
        restored_at: "2026-03-22T10:00:00+00:00",
      },
    ];
    mocks.getDuplicates.mockImplementation(async () => ({ data: groupsData }));
    mocks.setDuplicateReview.mockImplementationOnce(
      async (payload: { content_id: string; review_status: string; reviewed_canonical_instance_id: string }) => {
        groupsData = groupsData.map((group) =>
          group.group_id === payload.content_id
            ? {
                ...group,
                review_status: payload.review_status,
                reviewed_at: "2026-03-23T10:00:00+00:00",
                reviewed_canonical_instance_id: payload.reviewed_canonical_instance_id,
                is_stale: false,
                stale_reason: null,
              }
            : group,
        );
        return { data: {} };
      },
    );

    const reviewView = renderPage("/duplicates?tab=review");

    fireEvent.click(await screen.findByRole("button", { name: "Restored" }));
    expect(screen.getByText("Restored from Recycle Bin")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Mark as looks right" }));

    await waitFor(() => {
      expect(mocks.setDuplicateReview).toHaveBeenCalledWith({
        content_id: "group-alpha",
        review_status: "looks_right",
        reviewed_canonical_instance_id: "group-alpha-canonical",
      });
      expect(mocks.setDuplicateReclaim).toHaveBeenCalledWith({
        content_id: "group-alpha",
        reclaim_status: "REVIEWED_SAFE_TO_RECLAIM",
      });
      expect(screen.getByText("Select a group to compare")).toBeInTheDocument();
    });

    groupsData = groupsData.map((group) =>
      group.group_id === "group-alpha"
        ? {
            ...group,
            review_status: "looks_right",
            reviewed_at: "2026-03-23T10:00:00+00:00",
            reclaim_status: "REVIEWED_SAFE_TO_RECLAIM",
            duplicate_recommendation: buildRecommendation({
              state: "SAFE_TO_MOVE_EXTRAS",
              classification: "INFO",
              primary_reason_code: "SAFE_TO_MOVE_REVIEWED_DUPLICATES",
              reason_codes: ["SAFE_TO_MOVE_REVIEWED_DUPLICATES"],
              operator_explanation: "Keep copy is healthy and the group is approved for movement.",
            }),
          }
        : group,
    );

    reviewView.unmount();
    renderPage("/duplicates?tab=ready-for-bin");

    await waitFor(() => {
      expect(screen.getByTestId("ready-for-bin-focused-title")).toHaveTextContent("alpha-main.jpg");
      expect(screen.queryByText("Review restored groups")).not.toBeInTheDocument();
    });
  });

  it("surfaces duplicate-related playback issues without becoming a generic integrity dashboard", async () => {
    groupsData = [
      {
        ...buildGroup("group-alpha", "alpha-main.jpg", ["alpha-copy.jpg"]),
        integrity_issue_count: 2,
        integrity_broken_count: 1,
        integrity_suspect_count: 1,
      },
      buildGroup("group-beta", "beta-main.jpg", ["beta-copy.jpg"]),
    ];
    mocks.getDuplicates.mockImplementation(async () => ({ data: groupsData }));
    mocks.getIntegrityIssues.mockResolvedValue({
      data: {
        items: [
          {
            check_id: "check-1",
            file_instance_id: "group-alpha-duplicate-0",
            absolute_path: "/library/alpha-copy.jpg",
            status: "BROKEN",
            confidence: 1,
            signal_types: ["decode"],
          },
          {
            check_id: "check-2",
            file_instance_id: "group-alpha-canonical",
            absolute_path: "/library/alpha-main.jpg",
            status: "SUSPECT",
            confidence: 0.8,
            signal_types: ["probe"],
          },
          {
            check_id: "check-3",
            file_instance_id: "unrelated-file",
            absolute_path: "/library/unrelated.jpg",
            status: "BROKEN",
            confidence: 1,
            signal_types: ["decode"],
          },
        ],
      },
    });

    renderPage("/duplicates?tab=playback-issues");

    expect(await screen.findByRole("heading", { name: "Playback issues" })).toBeInTheDocument();
    expect(screen.getByText("Playback issues in duplicate groups")).toBeInTheDocument();
    expect(screen.getAllByText("alpha-main.jpg").length).toBeGreaterThan(0);
    expect(screen.getByText("Playback issue")).toBeInTheDocument();
    expect(screen.getByText("Needs checking")).toBeInTheDocument();
    expect(screen.queryByText("unrelated.jpg")).not.toBeInTheDocument();
    expect(screen.queryByText("Quick")).not.toBeInTheDocument();
  });

  it("renders video poster previews in the comparison cards and review queue", async () => {
    groupsData = [buildVideoGroup("group-video", "video-main.mp4", ["video-copy.mp4"])];
    mocks.getDuplicates.mockImplementation(async () => ({ data: groupsData }));

    renderPage();

    expect((await screen.findAllByText("video-main.mp4")).length).toBeGreaterThan(0);

    const previewImages = screen.getAllByRole("img", { name: "video-main.mp4" });
    expect(previewImages.some((image) => image.getAttribute("src") === "/api/video-thumbnail/group-video-canonical")).toBe(true);

    const duplicatePreviews = screen.getAllByRole("img", { name: "video-copy.mp4" });
    expect(duplicatePreviews.some((image) => image.getAttribute("src") === "/api/video-thumbnail/group-video-duplicate-0")).toBe(true);
  });

  it("falls back to the video placeholder when a video preview is unavailable", async () => {
    groupsData = [
      {
        group_id: "group-video-missing",
        hash: "group-video-missing-hash",
        canonical_path: "/library/video-main.mp4",
        reclaimable_file_count: 1,
        estimated_reclaim_bytes: 4 * 1024 * 1024,
        duplicates: [
          {
            file_instance_id: "group-video-missing-canonical",
            path: "/library/video-main.mp4",
            media_type: "VID",
            is_image: false,
            media_url: null,
            preview_url: null,
            thumbnail_url: null,
            is_canonical: true,
          },
          {
            file_instance_id: "group-video-missing-duplicate-0",
            path: "/library/video-copy.mp4",
            media_type: "VID",
            is_image: false,
            media_url: null,
            preview_url: null,
            thumbnail_url: null,
            is_canonical: false,
          },
        ],
      },
    ];
    mocks.getDuplicates.mockImplementation(async () => ({ data: groupsData }));

    renderPage();

    expect((await screen.findAllByText("video-main.mp4")).length).toBeGreaterThan(0);
    expect(screen.queryByRole("img", { name: "video-main.mp4" })).toBeNull();
    expect(screen.queryByRole("img", { name: "video-copy.mp4" })).toBeNull();
    expect(screen.getAllByText("Video").length).toBeGreaterThan(0);
  });

  it("constrains long filenames with truncation-friendly containers and title attributes", async () => {
    const longName =
      "very-long-filename-that-should-not-overflow-the-review-header-or-destabilize-the-comparison-layout-copy-two-final-version.jpg";
    groupsData = [buildGroup("group-long", longName, [`copy-${longName}`])];
    mocks.getDuplicates.mockImplementation(async () => ({ data: groupsData }));

    renderPage();

    const reviewTitle = await screen.findByTestId("review-group-title");
    const primaryTitle = screen.getByTestId("primary-comparison-title");
    const secondaryTitle = screen.getByTestId("secondary-comparison-title");

    expect(reviewTitle).toHaveClass("truncate");
    expect(primaryTitle).toHaveClass("truncate");
    expect(secondaryTitle).toHaveClass("truncate");
    expect(reviewTitle).toHaveAttribute("title", longName);
    expect(primaryTitle).toHaveAttribute("title", longName);
    expect(secondaryTitle).toHaveAttribute("title", `Extra copy: copy-${longName}`);
  });

  it("constrains long filenames safely inside the side navigation", async () => {
    const longName =
      "extremely-long-navigation-filename-that-should-stay-contained-inside-the-secondary-panel-without-bleeding.jpg";
    groupsData = [buildGroup("group-long-nav", longName, ["copy-a.jpg"])];
    mocks.getDuplicates.mockImplementation(async () => ({ data: groupsData }));

    renderPage();

    fireEvent.click(await screen.findByRole("button", { name: "Show group navigation" }));

    const queueTitle = await screen.findByTestId("review-queue-item-title");
    expect(queueTitle).toHaveClass("truncate");
    expect(queueTitle).toHaveAttribute("title", longName);
  });
});
