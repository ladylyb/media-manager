import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import DuplicatesPage from "@/pages/DuplicatesPage";

const mocks = vi.hoisted(() => ({
  getDuplicates: vi.fn(),
}));

vi.mock("@/lib/api/endpoints", () => ({
  getDuplicates: mocks.getDuplicates,
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
        thumbnail_url: null,
        is_canonical: true,
      },
      ...duplicateNames.map((name, index) => ({
        file_instance_id: `${id}-duplicate-${index}`,
        path: `/library/${name}`,
        media_type: "image",
        is_image: true,
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
  beforeEach(() => {
    mocks.getDuplicates.mockResolvedValue({
      data: [
        buildGroup("group-alpha", "alpha-main.jpg", ["alpha-copy.jpg", "alpha-copy-2.jpg"]),
        buildGroup("group-beta", "beta-main.jpg", ["beta-copy.jpg"]),
        buildGroup("group-gamma", "gamma-main.jpg", ["gamma-copy.jpg"]),
      ],
    });
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it("keeps technical details collapsed by default and omits unsupported destructive actions", async () => {
    renderPage();

    expect(await screen.findByText("Group 1 of 3")).toBeInTheDocument();
    expect(screen.queryByText("Group members")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /promote/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /remove/i })).not.toBeInTheDocument();
  });

  it("marks a group and auto-advances to the next one", async () => {
    renderPage();

    expect(await screen.findByRole("heading", { name: "alpha-main.jpg" })).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Mark as looks right" }));

    await waitFor(() => expect(screen.getByText("1 reviewed")).toBeInTheDocument());
    await waitFor(() => expect(screen.getByRole("heading", { name: "beta-main.jpg" })).toBeInTheDocument());
  });

  it("filters the queue by review mark after a group has been reviewed", async () => {
    renderPage();

    expect(await screen.findByRole("heading", { name: "alpha-main.jpg" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Mark as looks right" }));

    await waitFor(() => expect(screen.getByRole("heading", { name: "beta-main.jpg" })).toBeInTheDocument());

    fireEvent.click(screen.getByRole("button", { name: "Looks right" }));

    await waitFor(() => {
      expect(screen.getByRole("heading", { name: "alpha-main.jpg" })).toBeInTheDocument();
      expect(screen.queryByText("beta-main.jpg")).not.toBeInTheDocument();
    });
  });

  it("ignores marking shortcuts when focus is inside an input", async () => {
    renderPage();

    expect(await screen.findByText("Group 1 of 3")).toBeInTheDocument();

    const input = document.createElement("input");
    document.body.appendChild(input);
    input.focus();

    fireEvent.keyDown(input, { key: "2", bubbles: true });
    expect(screen.getByText("0 reviewed")).toBeInTheDocument();

    window.dispatchEvent(new KeyboardEvent("keydown", { key: "2" }));

    await waitFor(() => expect(screen.getByText("1 reviewed")).toBeInTheDocument());
    document.body.removeChild(input);
  });
});
