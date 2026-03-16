import { render, screen } from "@testing-library/react";
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
    expect(screen.getByText("Progress")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Abort Wizard" })).toBeInTheDocument();
  });
});
