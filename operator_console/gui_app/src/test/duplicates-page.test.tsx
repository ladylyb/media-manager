import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import DuplicatesPage from "@/pages/DuplicatesPage";

const mocks = vi.hoisted(() => ({
  executeDuplicateReclaim: vi.fn(),
  getDuplicateBinPolicy: vi.fn(),
  getDuplicates: vi.fn(),
  getDuplicateReclaimItems: vi.fn(),
  getIntegrityIssues: vi.fn(),
  restoreDuplicateReclaim: vi.fn(),
  setDuplicateReclaim: vi.fn(),
  setDuplicateReview: vi.fn(),
}));

vi.mock("@/lib/api/endpoints", () => ({
  executeDuplicateReclaim: mocks.executeDuplicateReclaim,
  getDuplicateBinPolicy: mocks.getDuplicateBinPolicy,
  getDuplicates: mocks.getDuplicates,
  getDuplicateReclaimItems: mocks.getDuplicateReclaimItems,
  getIntegrityIssues: mocks.getIntegrityIssues,
  restoreDuplicateReclaim: mocks.restoreDuplicateReclaim,
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

  beforeEach(() => {
    groupsData = [
      buildGroup("group-alpha", "alpha-main.jpg", ["alpha-copy.jpg", "alpha-copy-2.jpg"]),
      buildGroup("group-beta", "beta-main.jpg", ["beta-copy.jpg"]),
      buildGroup("group-gamma", "gamma-main.jpg", ["gamma-copy.jpg"]),
    ];
    reclaimItemsData = [];
    mocks.getDuplicates.mockImplementation(async () => ({ data: groupsData }));
    mocks.getDuplicateBinPolicy.mockResolvedValue({
      data: {
        current_move_root: "/tmp/media-manager/recycle-bin",
        current_retention_days: 21,
        target_recycle_bin_root: "/tmp/media-manager/recycle-bin",
        implementation: "reclaim_compatibility",
      },
    });
    mocks.getDuplicateReclaimItems.mockImplementation(async () => ({ data: { items: reclaimItemsData } }));
    mocks.getIntegrityIssues.mockResolvedValue({ data: { items: [] } });
    mocks.executeDuplicateReclaim.mockResolvedValue({
      data: { summary: { applied_count: 1, skipped_count: 0, moves_count: 1 } },
    });
    mocks.restoreDuplicateReclaim.mockResolvedValue({
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
      {
        ...buildGroup("group-alpha", "alpha-main.jpg", ["alpha-copy.jpg"]),
        review_status: "looks_right",
      },
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
        "Move eligible extra copies into the Recycle Bin here. Restore happens only on the Recycle Bin tab.",
      ),
    ).toBeInTheDocument();
  });

  it("defaults Ready for Bin to Focus and Recycle Bin to Gallery, with quiet alternate toggles", async () => {
    groupsData = [
      {
        ...buildGroup("group-alpha", "alpha-main.jpg", ["alpha-copy.jpg"]),
        review_status: "looks_right",
      },
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
      expect(screen.getByTestId("ready-for-bin-review-gallery")).toBeInTheDocument();
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

  it("supports focused Previous and Next navigation across ready groups on Ready for Bin", async () => {
    groupsData = [
      {
        ...buildGroup("group-alpha", "alpha-main.jpg", ["alpha-copy.jpg"]),
        review_status: "looks_right",
      },
      {
        ...buildGroup("group-beta", "beta-main.jpg", ["beta-copy.jpg"]),
        review_status: "looks_right",
      },
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
      {
        ...buildGroup("group-alpha", "alpha-main.jpg", ["alpha-copy.jpg"]),
        review_status: "looks_right",
      },
      {
        ...buildGroup("group-beta", "beta-main.jpg", ["beta-copy.jpg"]),
        review_status: "looks_right",
      },
      buildGroup("group-gamma", "gamma-main.jpg", ["gamma-copy.jpg"]),
    ];
    mocks.getDuplicates.mockImplementation(async () => ({ data: groupsData }));
    mocks.executeDuplicateReclaim.mockResolvedValue({
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
      expect(mocks.executeDuplicateReclaim).toHaveBeenCalledWith({
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
        reclaim_status: "REVIEWED_SAFE_TO_RECLAIM",
      },
      {
        ...buildGroup("group-beta", "beta-main.jpg", ["beta-copy.jpg"]),
        review_status: "looks_right",
      },
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
        reclaim_status: "REVIEWED_SAFE_TO_RECLAIM",
        duplicate_reclaim_actionable: false,
        duplicate_reclaim_unavailable_reason: "missing_canonical_file_content_mapping",
      },
      {
        ...buildGroup("group-beta", "beta-main.jpg", ["beta-copy.jpg"]),
        review_status: "looks_right",
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
    expect(
      screen.getByText("This group cannot move yet because the planner could not confirm a keep-copy mapping."),
    ).toBeInTheDocument();
  });

  it("uses Looks right groups as the only move-eligible groups and shows move and restore feedback", async () => {
    groupsData = [
      {
        ...buildGroup("group-alpha", "alpha-main.jpg", ["alpha-copy.jpg"]),
        review_status: "looks_right",
      },
      buildGroup("group-beta", "beta-main.jpg", ["beta-copy.jpg"]),
    ];
    mocks.getDuplicates.mockImplementation(async () => ({ data: groupsData }));
    reclaimItemsData = [];
    mocks.executeDuplicateReclaim.mockImplementation(async () => {
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
    mocks.restoreDuplicateReclaim.mockImplementation(async () => {
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
      await screen.findByText("Only groups marked “Looks right” can be moved to the Recycle Bin. The keep copy always stays in place."),
    ).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Mark safe to remove" })).not.toBeInTheDocument();
    expect(screen.getAllByText("alpha-main.jpg").length).toBeGreaterThan(0);
    expect(screen.getAllByText("beta-main.jpg").length).toBeGreaterThan(0);

    fireEvent.click(screen.getByTestId("ready-for-bin-view-gallery"));
    fireEvent.click(screen.getByRole("button", { name: "Move all eligible groups" }));

    await waitFor(() => {
      expect(mocks.setDuplicateReclaim).toHaveBeenCalledWith({
        content_id: "group-alpha",
        reclaim_status: "REVIEWED_SAFE_TO_RECLAIM",
      });
      expect(mocks.executeDuplicateReclaim).toHaveBeenCalledWith({
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
      expect(mocks.restoreDuplicateReclaim).toHaveBeenCalledWith({
        file_instance_ids: ["group-alpha-duplicate-0"],
      });
      expect(
        screen.getByText(
          "1 file restored from the Recycle Bin. Restored groups stay out of Ready for Bin until they are reviewed again.",
        ),
      ).toBeInTheDocument();
      expect(
        screen.getByText(
          "1 restored file already left the Recycle Bin. Those groups stay out of Ready for Bin until they are reviewed again.",
        ),
      ).toBeInTheDocument();
      expect(screen.getByText("No duplicate files are in the Recycle Bin right now.")).toBeInTheDocument();
    });
  });

  it("shows explicit sync failure feedback and blocks the move action when the bridge update fails", async () => {
    groupsData = [
      {
        ...buildGroup("group-alpha", "alpha-main.jpg", ["alpha-copy.jpg"]),
        review_status: "looks_right",
      },
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
      expect(mocks.executeDuplicateReclaim).not.toHaveBeenCalled();
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
        ...buildGroup("group-alpha", "alpha-main.jpg", ["alpha-copy.jpg"]),
        review_status: "looks_right",
        reclaim_status: "REVIEWED_SAFE_TO_RECLAIM",
      },
    ];
    mocks.getDuplicates.mockImplementation(async () => ({ data: groupsData }));
    mocks.executeDuplicateReclaim.mockResolvedValue({
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
      expect(mocks.executeDuplicateReclaim).toHaveBeenCalledWith({
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
        ...buildGroup("group-alpha", "alpha-main.jpg", ["alpha-copy.jpg"]),
        review_status: "looks_right",
        reclaim_status: "REVIEWED_SAFE_TO_RECLAIM",
      },
    ];
    mocks.getDuplicates.mockImplementation(async () => ({ data: groupsData }));
    mocks.executeDuplicateReclaim.mockResolvedValue({
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
        ...buildGroup("group-alpha", "alpha-main.jpg", ["alpha-copy.jpg"]),
        review_status: "looks_right",
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
