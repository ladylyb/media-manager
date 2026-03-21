import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import DuplicatesPage from "@/pages/DuplicatesPage";

const mocks = vi.hoisted(() => ({
  getDuplicates: vi.fn(),
  setDuplicateReview: vi.fn(),
}));

vi.mock("@/lib/api/endpoints", () => ({
  getDuplicates: mocks.getDuplicates,
  setDuplicateReview: mocks.setDuplicateReview,
}));

function buildGroup(id: string, canonicalName: string, duplicateNames: string[]) {
  return {
    group_id: id,
    hash: `${id}-hash`,
    canonical_path: `/library/${canonicalName}`,
    duplicates: [
      {
        file_instance_id: `${id}-canonical`,
        path: `/library/${canonicalName}`,
        media_type: "image",
        is_image: true,
        media_url: `/media/${id}-canonical`,
        thumbnail_url: null,
        is_canonical: true,
      },
      ...duplicateNames.map((name, index) => ({
        file_instance_id: `${id}-duplicate-${index}`,
        path: `/library/${name}`,
        media_type: "image",
        is_image: true,
        media_url: `/media/${id}-duplicate-${index}`,
        thumbnail_url: null,
        is_canonical: false,
      })),
    ],
  };
}

function renderPage() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
      },
    },
  });

  return render(
    <MemoryRouter>
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
    mocks.setDuplicateReview.mockImplementation(async (payload: { content_id: string; review_status: string; reviewed_canonical_instance_id: string }) => {
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
    });
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it("keeps technical details collapsed by default and omits unsupported destructive actions", async () => {
    renderPage();

    expect(await screen.findByText("1 of 3")).toBeInTheDocument();
    expect(screen.queryByText("Group members")).not.toBeInTheDocument();
    expect(screen.queryByText("Queue")).not.toBeInTheDocument();
    expect(screen.queryByText("Shortcuts")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /promote/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /remove/i })).not.toBeInTheDocument();
  });

  it("marks a group and auto-advances to the next one", async () => {
    renderPage();

    expect((await screen.findAllByText("alpha-main.jpg")).length).toBeGreaterThan(0);

    fireEvent.click(screen.getByRole("button", { name: "Mark as looks right" }));

    await waitFor(() => expect(screen.getByText("2 of 3")).toBeInTheDocument());
  });

  it("filters the queue by review mark after a group has been reviewed", async () => {
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
});
