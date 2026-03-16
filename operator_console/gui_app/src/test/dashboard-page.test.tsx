import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import DashboardPage from "@/pages/DashboardPage";

const mocks = vi.hoisted(() => ({
  getHome: vi.fn(),
}));

vi.mock("@/lib/api/endpoints", () => ({
  getHome: mocks.getHome,
}));

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
        <DashboardPage />
      </QueryClientProvider>
    </MemoryRouter>,
  );
}

describe("Dashboard page", () => {
  beforeEach(() => {
    mocks.getHome.mockResolvedValue({
      data: {
        library_summary: {
          total_assets: 81,
          images: 50,
          videos: 24,
          duplicate_groups: 9,
          canonical_assets: 81,
          recent_import_count: 12,
        },
        recent_media: [],
        recent_images: [],
        recent_videos: [],
        attention_summary: {
          duplicate_groups: 9,
          failed_runs: 1,
          active_runs: 0,
          untagged_assets: 3,
          unresolved_items: 4,
        },
        recent_activity: [],
        collections: [],
        status_strip: {
          workflow_label: "Guided workflow available",
          active_phase: "Ready",
          last_run_status: "COMPLETED",
          last_run_type: "PLAN",
          regression_status: "UNKNOWN",
        },
        guided_entry: {
          label: "Open Organize Media",
          route: "/pipeline-wizard",
          helper: "Guided ingest, planning, apply, and review",
        },
      },
    });
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it("renders the shared top-surface header with the dashboard quick links", async () => {
    renderPage();

    expect(await screen.findByText("Library Overview")).toBeInTheDocument();
    expect(screen.getByText("Media Manager")).toBeInTheDocument();
    expect(
      screen.getByText("Browse recent media, review what needs attention, and jump into the guided workflow when you're ready."),
    ).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Open Organize Media" })).toBeInTheDocument();
    expect(screen.getByText("Quick Links")).toBeInTheDocument();
  });
});
