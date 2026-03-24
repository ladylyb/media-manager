import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ApiClientError } from "@/lib/api/client";
import PipelineWizard from "@/pages/PipelineWizard";

const mocks = vi.hoisted(() => ({
  getCanonical: vi.fn(),
  getDirectoryPickerCapability: vi.fn(),
  getDuplicates: vi.fn(),
  getPolicy: vi.fn(),
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
  getPolicy: mocks.getPolicy,
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
    mocks.getPolicy.mockResolvedValue({
      data: {
        canonical_priority: {
          selected_policy: "FIRST_SEEN",
          preferred_roots: [],
        },
        naming: {
          strategy: "DUPLICATE_OWNS_DATE_STANDARDIZED",
        },
        recanonicalization: {
          enabled: false,
        },
        metadata: {
          version: 3,
          updated_at: "2026-03-22T10:00:00Z",
        },
        tie_breaker_rules: {
          policy_name: "default",
          policy_version: 1,
          effective_order: ["first_seen_at ASC", "file_instance_id ASC"],
        },
      },
    });
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

  it("shows batch naming controls on the plan step and sends them in the plan request", async () => {
    mocks.runWizardIngest.mockResolvedValue({
      data: { summary: { files_scanned: 10, new_contents: 5, new_instances: 5, duplicates_detected: 0 } },
    });
    mocks.runWizardPlan.mockResolvedValue({
      data: {
        run_id: "run-123",
        summary: { scanned_count: 10, duplicate_actions: 1, move_actions: 2 },
      },
    });

    renderPage();

    fireEvent.change(await screen.findByLabelText("Folder Path"), {
      target: { value: "/media/incoming" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Run Ingest" }));
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Continue to Review Ingest" })).toBeEnabled(),
    );
    fireEvent.click(screen.getByRole("button", { name: "Continue to Review Ingest" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "Continue to Plan" })).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: "Continue to Plan" }));

    expect(await screen.findByLabelText("Owner")).toHaveValue("LL");
    expect(screen.getByLabelText("Context")).toHaveValue("General");
    expect(screen.getByText("Duplicate owns date (standardized)")).toBeInTheDocument();
    expect(screen.getByText("Planning This Folder")).toBeInTheDocument();
    expect(screen.getByText("Previous Step Details")).toBeInTheDocument();
    expect(screen.getByText("Naming Inputs Summary")).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("Owner"), { target: { value: "TripA" } });
    fireEvent.change(screen.getByLabelText("Context"), { target: { value: "Family" } });
    fireEvent.click(screen.getByRole("button", { name: "Create Plan" }));

    await waitFor(() =>
      expect(mocks.runWizardPlan).toHaveBeenCalledWith({
        folder_path: "/media/incoming",
        strict_metadata: false,
        owner: "TripA",
        context: "Family",
        naming_strategy: "DUPLICATE_OWNS_DATE_STANDARDIZED",
        owner_context_override_confirmed: false,
      }),
    );
  });

  it("keeps plan details available in collapsible summary panels", async () => {
    mocks.runWizardIngest.mockResolvedValue({
      data: { summary: { files_scanned: 10, new_contents: 5, new_instances: 5, duplicates_detected: 0 } },
    });

    renderPage();

    fireEvent.change(await screen.findByLabelText("Folder Path"), {
      target: { value: "/media/incoming" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Run Ingest" }));
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Continue to Review Ingest" })).toBeEnabled(),
    );
    fireEvent.click(screen.getByRole("button", { name: "Continue to Review Ingest" }));
    fireEvent.click(await screen.findByRole("button", { name: "Continue to Plan" }));

    const planningPanel = screen.getByText("Planning This Folder").closest("[data-panel-state='open']");
    expect(planningPanel).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: /Planning This Folder/ }));
    expect(screen.getByText("Owner: LL")).toBeInTheDocument();
    expect(screen.getByText("Context: General")).toBeInTheDocument();
    expect(screen.getByText("Naming strategy: Duplicate owns date (standardized)")).toBeInTheDocument();
  });

  it("blocks plan creation early when owner or context is invalid", async () => {
    mocks.runWizardIngest.mockResolvedValue({
      data: { summary: { files_scanned: 4, new_contents: 4, new_instances: 4, duplicates_detected: 0 } },
    });

    renderPage();

    fireEvent.change(await screen.findByLabelText("Folder Path"), {
      target: { value: "/media/incoming" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Run Ingest" }));
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Continue to Review Ingest" })).toBeEnabled(),
    );
    fireEvent.click(screen.getByRole("button", { name: "Continue to Review Ingest" }));
    fireEvent.click(await screen.findByRole("button", { name: "Continue to Plan" }));

    fireEvent.change(await screen.findByLabelText("Context"), { target: { value: "FEM-INSPO" } });

    expect(screen.getByText("context must contain only alphanumeric characters or underscore")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Create Plan" })).toBeDisabled();

    fireEvent.change(screen.getByLabelText("Context"), { target: { value: "FEM_INSPO" } });

    await waitFor(() =>
      expect(
        screen.queryByText("context must contain only alphanumeric characters or underscore"),
      ).not.toBeInTheDocument(),
    );
    expect(screen.getByRole("button", { name: "Create Plan" })).toBeEnabled();
  });

  it("shows override confirmation when plan detects conflicting owner/context values and retries with confirmation", async () => {
    mocks.runWizardIngest.mockResolvedValue({
      data: { summary: { files_scanned: 2, new_contents: 0, new_instances: 0, duplicates_detected: 2 } },
    });
    mocks.runWizardPlan
      .mockRejectedValueOnce(
        new ApiClientError("override required", 400, [
          {
            code: "OWNER_CONTEXT_OVERRIDE_REQUIRED",
            message: "override required",
            details: {
              requested_owner: "TripB",
              requested_context: "Family",
              existing_owner: "LL",
              existing_context: "General",
              conflicting_group_count: 1,
              sample_content_id: "content-1",
              sample_paths: ["/archive/a.jpg"],
            },
          },
        ]),
      )
      .mockResolvedValueOnce({
        data: {
          run_id: "run-override",
          summary: { scanned_count: 2, duplicate_actions: 1, move_actions: 0 },
        },
      });

    renderPage();

    fireEvent.change(await screen.findByLabelText("Folder Path"), {
      target: { value: "/media/incoming" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Run Ingest" }));
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Continue to Review Ingest" })).toBeEnabled(),
    );
    fireEvent.click(screen.getByRole("button", { name: "Continue to Review Ingest" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "Continue to Plan" })).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: "Continue to Plan" }));

    fireEvent.change(await screen.findByLabelText("Owner"), { target: { value: "TripB" } });
    fireEvent.change(screen.getByLabelText("Context"), { target: { value: "Family" } });
    fireEvent.click(screen.getByRole("button", { name: "Create Plan" }));

    expect(await screen.findByText("Owner/context correction requires confirmation")).toBeInTheDocument();

    fireEvent.click(screen.getByLabelText(/Confirm owner\/context correction/));
    fireEvent.click(screen.getByRole("button", { name: "Create Plan" }));

    await waitFor(() =>
      expect(mocks.runWizardPlan).toHaveBeenLastCalledWith({
        folder_path: "/media/incoming",
        strict_metadata: false,
        owner: "TripB",
        context: "Family",
        naming_strategy: "DUPLICATE_OWNS_DATE_STANDARDIZED",
        owner_context_override_confirmed: true,
      }),
    );
  });

  it("shows classification guidance when plan detects unclassified owner/context metadata", async () => {
    mocks.runWizardIngest.mockResolvedValue({
      data: { summary: { files_scanned: 2, new_contents: 2, new_instances: 2, duplicates_detected: 0 } },
    });
    mocks.runWizardPlan.mockRejectedValueOnce(
      new ApiClientError("classification required", 400, [
        {
          code: "OWNER_CONTEXT_CLASSIFICATION_REQUIRED",
          message: "classification required",
          details: {
            unclassified_group_count: 2,
            sample_content_id: "content-unknown",
            sample_paths: ["/media/incoming/a.jpg"],
          },
        },
      ]),
    );

    renderPage();

    fireEvent.change(await screen.findByLabelText("Folder Path"), {
      target: { value: "/media/incoming" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Run Ingest" }));
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Continue to Review Ingest" })).toBeEnabled(),
    );
    fireEvent.click(screen.getByRole("button", { name: "Continue to Review Ingest" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "Continue to Plan" })).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: "Continue to Plan" }));
    fireEvent.click(screen.getByRole("button", { name: "Create Plan" }));

    expect(await screen.findByText("Explicit classification is required")).toBeInTheDocument();
    expect(screen.getByText("Unclassified groups: 2")).toBeInTheDocument();
    expect(screen.getByText("Example content group: content-unknown")).toBeInTheDocument();
  });

  it("closes the apply confirmation dialog immediately and keeps execution on the main wizard screen", async () => {
    let resolveApply: ((value: { data: Record<string, unknown> }) => void) | null = null;
    mocks.runWizardIngest.mockResolvedValue({
      data: { summary: { files_scanned: 3, new_contents: 3, new_instances: 3, duplicates_detected: 0 } },
    });
    mocks.runWizardPlan.mockResolvedValue({
      data: {
        run_id: "run-apply",
        summary: { scanned_count: 3, duplicate_actions: 0, move_actions: 1 },
      },
    });
    mocks.runWizardApply.mockReturnValue(
      new Promise((resolve) => {
        resolveApply = resolve;
      }),
    );

    renderPage();

    fireEvent.change(await screen.findByLabelText("Folder Path"), {
      target: { value: "/media/incoming" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Run Ingest" }));
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Continue to Review Ingest" })).toBeEnabled(),
    );
    fireEvent.click(screen.getByRole("button", { name: "Continue to Review Ingest" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "Continue to Plan" })).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: "Continue to Plan" }));
    fireEvent.click(await screen.findByRole("button", { name: "Create Plan" }));
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Continue to Duplicate Review" })).toBeEnabled(),
    );
    fireEvent.click(screen.getByRole("button", { name: "Continue to Duplicate Review" }));
    fireEvent.click(await screen.findByRole("button", { name: "Continue to Apply" }));

    const applyButton = await screen.findByRole("button", { name: "Apply Plan" });
    fireEvent.click(applyButton);
    fireEvent.click(await screen.findByRole("button", { name: "Confirm" }));

    await waitFor(() => expect(mocks.runWizardApply).toHaveBeenCalled());
    expect(screen.queryByText("Execute Apply?")).not.toBeInTheDocument();
    await waitFor(() => expect(screen.getByRole("button", { name: "Apply Plan" })).toBeDisabled());
    expect(screen.getByText("Apply started. You can monitor progress below while the wizard stays available.")).toBeInTheDocument();

    resolveApply?.({
      data: {
        run_id: "run-apply",
        summary: { applied_count: 1, moves_count: 1, duplicates_count: 0, errors_count: 0 },
      },
    });
  }, 10000);
});
