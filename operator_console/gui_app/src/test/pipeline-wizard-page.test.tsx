import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import PipelineWizard from "@/pages/PipelineWizard";

const mocks = vi.hoisted(() => ({
  getCanonical: vi.fn(),
  getDirectoryPickerCapability: vi.fn(),
  getDuplicates: vi.fn(),
  invalidateReadsAfterOperation: vi.fn(),
  runWizardApply: vi.fn(),
  runWizardCanonicalRecompute: vi.fn(),
  runWizardIngest: vi.fn(),
  runWizardPlan: vi.fn(),
  runWizardTagEnrichment: vi.fn(),
}));

vi.mock("@/lib/api/endpoints", () => ({
  getCanonical: mocks.getCanonical,
  getDirectoryPickerCapability: mocks.getDirectoryPickerCapability,
  getDuplicates: mocks.getDuplicates,
  invalidateReadsAfterOperation: mocks.invalidateReadsAfterOperation,
  runWizardApply: mocks.runWizardApply,
  runWizardCanonicalRecompute: mocks.runWizardCanonicalRecompute,
  runWizardIngest: mocks.runWizardIngest,
  runWizardPlan: mocks.runWizardPlan,
  runWizardTagEnrichment: mocks.runWizardTagEnrichment,
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
        <PipelineWizard />
      </QueryClientProvider>
    </MemoryRouter>,
  );
}

describe("Pipeline Wizard page", () => {
  beforeEach(() => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue({
      ok: true,
      json: async () => [],
    } as Response);
    mocks.getDirectoryPickerCapability.mockResolvedValue({
      data: { enabled: true, roots: [{ label: "Incoming", path: "/media/incoming" }] },
    });
    mocks.getDuplicates.mockResolvedValue({ data: [] });
    mocks.getCanonical.mockResolvedValue({
      data: { items: [], total_count: 0, page: 1, limit: 1, total_pages: 0 },
    });
    mocks.invalidateReadsAfterOperation.mockResolvedValue(undefined);
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it("renders the compact shared top-surface header above the progress workspace", async () => {
    renderPage();

    expect(await screen.findByText("Guided Workflow")).toBeInTheDocument();
    expect(screen.getByText("Organize")).toBeInTheDocument();
    expect(
      screen.getByText(
        "Guided ingest, planning, apply, chosen-version review, and enrichment with short checkpoints between stages.",
      ),
    ).toBeInTheDocument();
    expect(screen.getAllByText("Progress").length).toBeGreaterThan(0);
    expect(screen.getByRole("button", { name: "Abort Wizard" })).toBeInTheDocument();
    expect(await screen.findByText("[ INGEST READY ]")).toBeInTheDocument();
  });

  it("shows finalizing ingest while the request is still in flight after scan progress reaches 100%", async () => {
    let resolveIngest: ((value: { data: Record<string, unknown> }) => void) | null = null;
    mocks.runWizardIngest.mockReturnValue(
      new Promise((resolve) => {
        resolveIngest = resolve;
      }),
    );
    vi.spyOn(globalThis, "fetch").mockResolvedValue({
      ok: true,
      json: async () => [
        "2026-03-21 INFO media_manager.app.persistence.ingest phase=ingest action=PROGRESS processed_count=2850 total_count=2850 progress_percent=100.0 throughput_fps=25.0 Progress: 2850/2850 files (100.0%) | 25.0 files/sec | elapsed 113.9s",
      ],
    } as Response);

    renderPage();

    fireEvent.change(await screen.findByLabelText("Folder Path"), {
      target: { value: "/media/incoming" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Run Ingest" }));

    expect(await screen.findByText("[ FINALIZING INGEST ]")).toBeInTheDocument();
    await waitFor(() => expect(screen.getByRole("button", { name: "Run Ingest" })).toBeDisabled());

    resolveIngest?.({ data: { files_scanned: 2850 } });
  });
});
