import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import DuplicatesPage from "@/pages/DuplicatesPage";

const mocks = vi.hoisted(() => ({
  executeDuplicateReclaim: vi.fn(),
  getDuplicates: vi.fn(),
  getDuplicateReclaimItems: vi.fn(),
  getIntegrityIssues: vi.fn(),
  getPolicy: vi.fn(),
  restoreDuplicateReclaim: vi.fn(),
  setDuplicateReclaim: vi.fn(),
  setDuplicateReview: vi.fn(),
}));

vi.mock("@/lib/api/endpoints", () => ({
  executeDuplicateReclaim: mocks.executeDuplicateReclaim,
  getDuplicates: mocks.getDuplicates,
  getDuplicateReclaimItems: mocks.getDuplicateReclaimItems,
  getIntegrityIssues: mocks.getIntegrityIssues,
  getPolicy: mocks.getPolicy,
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

  beforeEach(() => {
    groupsData = [
      buildGroup("group-alpha", "alpha-main.jpg", ["alpha-copy.jpg", "alpha-copy-2.jpg"]),
      buildGroup("group-beta", "beta-main.jpg", ["beta-copy.jpg"]),
      buildGroup("group-gamma", "gamma-main.jpg", ["gamma-copy.jpg"]),
    ];
    mocks.getDuplicates.mockImplementation(async () => ({ data: groupsData }));
    mocks.getPolicy.mockResolvedValue({
      data: {
        duplicate_reclaim: {
          default_retention_days: 21,
        },
      },
    });
    mocks.getDuplicateReclaimItems.mockResolvedValue({ data: { items: [] } });
    mocks.getIntegrityIssues.mockResolvedValue({ data: { items: [] } });
    mocks.executeDuplicateReclaim.mockResolvedValue({ data: {} });
    mocks.restoreDuplicateReclaim.mockResolvedValue({ data: {} });
    mocks.setDuplicateReclaim.mockResolvedValue({ data: {} });
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

  it("defaults to the review tab with comparison content dominant and no reclaim actions", async () => {
    renderPage();

    expect(await screen.findByRole("heading", { name: "Review duplicates" })).toBeInTheDocument();
    expect(screen.getByTestId("review-group-navigation-hidden")).toBeInTheDocument();
    expect(screen.getAllByText("alpha-main.jpg").length).toBeGreaterThan(0);
    expect(screen.getByRole("button", { name: "Back" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Next" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Mark as looks right" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Archive reclaimable" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Mark safe to reclaim" })).not.toBeInTheDocument();
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

    await waitFor(() => expect(screen.getByText("2 of 3")).toBeInTheDocument());
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

    expect(await screen.findByTestId("secondary-comparison-title")).toHaveTextContent("Selected copy: alpha-copy.jpg");

    fireEvent.click(screen.getByRole("button", { name: "Compare duplicate 2: alpha-copy-2.jpg" }));

    await waitFor(() => {
      expect(screen.getByTestId("secondary-comparison-title")).toHaveTextContent("Selected copy: alpha-copy-2.jpg");
      expect(screen.getByTestId("active-duplicate-caption")).toHaveTextContent("Active: alpha-copy-2.jpg");
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

  it("keeps deep-link tab navigation on the removal review tab", async () => {
    groupsData = [
      {
        ...buildGroup("group-alpha", "alpha-main.jpg", ["alpha-copy.jpg"]),
        reclaim_status: "REVIEWED_SAFE_TO_RECLAIM",
      },
    ];
    mocks.getDuplicates.mockImplementation(async () => ({ data: groupsData }));

    renderPage("/duplicates?tab=removal");

    expect(await screen.findByRole("heading", { name: "Removal review" })).toBeInTheDocument();
    expect(screen.getAllByText("Ready to archive").length).toBeGreaterThan(0);
    expect(screen.getByRole("button", { name: "Archive reclaimable" })).toBeInTheDocument();
  });

  it("keeps reclaim actions in removal review with explicit queue sections", async () => {
    groupsData = [
      {
        ...buildGroup("group-alpha", "alpha-main.jpg", ["alpha-copy.jpg"]),
        reclaim_status: "REVIEWED_SAFE_TO_RECLAIM",
      },
      buildGroup("group-beta", "beta-main.jpg", ["beta-copy.jpg"]),
    ];
    mocks.getDuplicates.mockImplementation(async () => ({ data: groupsData }));
    mocks.getDuplicateReclaimItems.mockResolvedValue({
      data: {
        items: [
          {
            file_instance_id: "archived-1",
            content_id: "group-archived",
            original_path: "/library/archived-copy.jpg",
            archive_path: "/archive/archived-copy.jpg",
            item_status: "ARCHIVED",
            expires_at: "2026-04-10T10:00:00+00:00",
          },
        ],
      },
    });

    renderPage("/duplicates?tab=removal");

    expect(await screen.findByText("Needs removal review")).toBeInTheDocument();
    expect(screen.getByText("Archived items / restore candidates")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Mark safe to reclaim" }));

    await waitFor(() =>
      expect(mocks.setDuplicateReclaim).toHaveBeenCalledWith({
        content_id: "group-beta",
        reclaim_status: "REVIEWED_SAFE_TO_RECLAIM",
      }),
    );

    fireEvent.click(screen.getByRole("button", { name: "Archive reclaimable" }));

    await waitFor(() =>
      expect(mocks.executeDuplicateReclaim).toHaveBeenCalledWith({
        content_ids: ["group-alpha"],
        retention_days: 21,
      }),
    );

    fireEvent.click(screen.getByRole("button", { name: "Restore" }));

    await waitFor(() =>
      expect(mocks.restoreDuplicateReclaim).toHaveBeenCalledWith({
        file_instance_ids: ["archived-1"],
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
    expect(screen.getByText("Duplicate-related playback exceptions")).toBeInTheDocument();
    expect(screen.getAllByText("alpha-main.jpg").length).toBeGreaterThan(0);
    expect(screen.getByText("Blocks removal in this view")).toBeInTheDocument();
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
    expect(secondaryTitle).toHaveAttribute("title", `Selected copy: copy-${longName}`);
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
