import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ApiClientError } from "@/lib/api/client";
import OperationsPage from "@/pages/OperationsPage";

const mocks = vi.hoisted(() => ({
  getDirectoryPickerListing: vi.fn(),
  getDirectoryPickerCapability: vi.fn(),
  getPolicy: vi.fn(),
  getRuns: vi.fn(),
  invalidateReadsAfterOperation: vi.fn(),
  runApply: vi.fn(),
  runCanonicalRecompute: vi.fn(),
  runIngest: vi.fn(),
  runPlan: vi.fn(),
  runTagEnrichment: vi.fn(),
}));

vi.mock("@/lib/api/endpoints", () => ({
  getDirectoryPickerListing: mocks.getDirectoryPickerListing,
  getDirectoryPickerCapability: mocks.getDirectoryPickerCapability,
  getPolicy: mocks.getPolicy,
  getRuns: mocks.getRuns,
  invalidateReadsAfterOperation: mocks.invalidateReadsAfterOperation,
  runApply: mocks.runApply,
  runCanonicalRecompute: mocks.runCanonicalRecompute,
  runIngest: mocks.runIngest,
  runPlan: mocks.runPlan,
  runTagEnrichment: mocks.runTagEnrichment,
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
        <OperationsPage />
      </QueryClientProvider>
    </MemoryRouter>,
  );
}

describe("Import page", () => {
  beforeEach(() => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue({
      ok: true,
      json: async () => [],
    } as Response);
    mocks.getDirectoryPickerCapability.mockResolvedValue({
      data: { enabled: true, roots: [{ label: "Incoming", path: "/media/incoming" }] },
    });
    mocks.getDirectoryPickerListing.mockResolvedValue({
      data: {
        path: "/media/incoming",
        parent_path: null,
        directories: [],
      },
    });
    mocks.getRuns.mockResolvedValue({
      data: {
        items: [
          {
            operation_run_id: "plan-operation-1",
            operation_type: "PLAN",
            status: "COMPLETED",
            started_at: "2026-03-15T10:00:00Z",
            completed_at: "2026-03-15T10:01:00Z",
            duration_ms: 500,
            linked_run_id: "durable-run-1",
          },
        ],
      },
    });
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
    mocks.invalidateReadsAfterOperation.mockResolvedValue(undefined);
    mocks.runApply.mockResolvedValue({
      data: {
        operation: "APPLY",
        success: true,
        summary: "Applied saved work.",
        details: { run_id: "durable-run-1" },
        duration_ms: 42,
      },
    });
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it("renders the redesigned Import sections", async () => {
    renderPage();

    expect(await screen.findByText("Import")).toBeInTheDocument();
    expect(screen.getByText("Start from Folder")).toBeInTheDocument();
    expect(screen.getByText("Continue a Saved Plan")).toBeInTheDocument();
    expect(screen.getByText("Recheck a Folder")).toBeInTheDocument();
    expect(screen.getByText("Refresh Library Decisions")).toBeInTheDocument();
    expect(screen.getByText("Add Searchable Details")).toBeInTheDocument();
    expect(screen.queryByText("Legacy Composite Run")).not.toBeInTheDocument();
    expect(screen.queryByText("Mutating")).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Open Organize" })).toBeInTheDocument();
    expect(await screen.findByText("[ WAITING FOR LOGS ]")).toBeInTheDocument();
  });

  it("shows wizard-aligned guidance headings and keeps only one panel open", async () => {
    renderPage();

    const startPanelButton = await screen.findByRole("button", { name: /Start from Folder/ });
    expect(screen.queryByText("What this step does")).not.toBeInTheDocument();
    expect(startPanelButton.closest("[data-panel-state='open']")).toBeTruthy();

    fireEvent.click(screen.getAllByRole("button", { name: /Step Guidance/ })[0]);
    expect(await screen.findByText("What this step does")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /Continue a Saved Plan/ }));

    expect(startPanelButton.closest("[data-panel-state='closed']")).toBeTruthy();
    const continuePanelButton = screen.getByRole("button", { name: /Continue a Saved Plan/ });
    expect(continuePanelButton.closest("[data-panel-state='open']")).toBeTruthy();
    expect(screen.queryByText("What this step does")).not.toBeInTheDocument();

    fireEvent.click(screen.getAllByRole("button", { name: /Step Guidance/ })[0]);
    await screen.findByText("Before you run");
    expect(screen.getByText("What success looks like")).toBeInTheDocument();
    expect(screen.getByText("Risk level")).toBeInTheDocument();
  });

  it("uses softened state styling for open and closed panels", async () => {
    renderPage();

    const startPanel = (await screen.findByRole("button", { name: /Start from Folder/ })).closest("[data-panel-state='open']");
    const continuePanel = screen.getByRole("button", { name: /Continue a Saved Plan/ }).closest("[data-panel-state='closed']");

    expect(startPanel?.className).toContain("border-emerald-200");
    expect(continuePanel?.className).toContain("border-[#cfcfcf]");
    expect(screen.getAllByText("Checks before changing anything").length).toBeGreaterThan(0);
  });

  it("keeps controls visible while guidance stays collapsed by default", async () => {
    renderPage();

    await screen.findByRole("button", { name: /Continue a Saved Plan/ });
    fireEvent.click(screen.getByRole("button", { name: /Continue a Saved Plan/ }));

    expect(screen.getByRole("button", { name: /Step Guidance/ })).toBeInTheDocument();
    expect(screen.queryByText("What this step does")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Apply Saved Work" })).toBeInTheDocument();
  });

  it("keeps separate guidance toggles for recheck discovery and planning", async () => {
    renderPage();

    await screen.findByRole("button", { name: /Recheck a Folder/ });
    fireEvent.click(screen.getByRole("button", { name: /Recheck a Folder/ }));

    expect(screen.getByRole("button", { name: /Refresh Discovery Guidance/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Prepare Plan Guidance/ })).toBeInTheDocument();
    expect(screen.queryByText("What this step does")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /Refresh Discovery Guidance/ }));
    expect(await screen.findByText("Refresh Discovery Guidance")).toBeInTheDocument();
  });

  it("shows recheck naming controls and sends them with manual plan requests", async () => {
    mocks.runPlan.mockResolvedValue({
      data: {
        operation: "PLAN",
        success: true,
        summary: "Prepared plan.",
        details: { run_id: "run-1" },
        duration_ms: 42,
      },
    });

    renderPage();

    await screen.findByText("Recheck a Folder");
    fireEvent.click(screen.getByRole("button", { name: /Recheck a Folder/ }));
    fireEvent.click(screen.getByRole("button", { name: "Browse Folders" }));
    fireEvent.click(await screen.findByRole("button", { name: "Use This Path" }));

    expect(screen.getByLabelText("Owner")).toHaveValue("LL");
    expect(screen.getByLabelText("Context")).toHaveValue("General");
    expect(screen.getByText("Duplicate owns date (standardized)")).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("Owner"), { target: { value: "TripA" } });
    fireEvent.change(screen.getByLabelText("Context"), { target: { value: "Family" } });
    fireEvent.click(screen.getByRole("button", { name: "Prepare Plan" }));
    fireEvent.click(await screen.findByRole("button", { name: "Confirm" }));

    await waitFor(() =>
      expect(mocks.runPlan).toHaveBeenCalledWith({
        folder_path: "/media/incoming",
        strict_metadata: false,
        owner: "TripA",
        context: "Family",
        naming_strategy: "DUPLICATE_OWNS_DATE_STANDARDIZED",
        owner_context_override_confirmed: false,
      }),
    );
  });

  it("blocks prepare plan when naming inputs are invalid and clears once fixed", async () => {
    renderPage();

    await screen.findByText("Recheck a Folder");
    fireEvent.click(screen.getByRole("button", { name: /Recheck a Folder/ }));
    fireEvent.click(screen.getByRole("button", { name: "Browse Folders" }));
    fireEvent.click(await screen.findByRole("button", { name: "Use This Path" }));

    fireEvent.change(screen.getByLabelText("Context"), { target: { value: "FEM-INSPO" } });

    expect(screen.getByText("context must contain only alphanumeric characters or underscore")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Prepare Plan" })).toBeDisabled();

    fireEvent.change(screen.getByLabelText("Context"), { target: { value: "FEM_INSPO" } });

    await waitFor(() =>
      expect(
        screen.queryByText("context must contain only alphanumeric characters or underscore"),
      ).not.toBeInTheDocument(),
    );
    expect(screen.getByRole("button", { name: "Prepare Plan" })).toBeEnabled();
  });

  it("shows correction confirmation on recheck plan conflicts and retries with override", async () => {
    mocks.runPlan
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
            },
          },
        ]),
      )
      .mockResolvedValueOnce({
        data: {
          operation: "PLAN",
          success: true,
          summary: "Prepared plan.",
          details: { run_id: "run-override" },
          duration_ms: 42,
        },
      });

    renderPage();

    await screen.findByText("Recheck a Folder");
    fireEvent.click(screen.getByRole("button", { name: /Recheck a Folder/ }));
    fireEvent.click(screen.getByRole("button", { name: "Browse Folders" }));
    fireEvent.click(await screen.findByRole("button", { name: "Use This Path" }));

    fireEvent.change(screen.getByLabelText("Owner"), { target: { value: "TripB" } });
    fireEvent.change(screen.getByLabelText("Context"), { target: { value: "Family" } });
    fireEvent.click(screen.getByRole("button", { name: "Prepare Plan" }));
    fireEvent.click(await screen.findByRole("button", { name: "Confirm" }));

    expect(await screen.findByText("Correction confirmation is required")).toBeInTheDocument();

    fireEvent.click(screen.getByLabelText(/Confirm owner\/context correction/));
    fireEvent.click(screen.getByRole("button", { name: "Prepare Plan" }));
    fireEvent.click(await screen.findByRole("button", { name: "Confirm" }));

    await waitFor(() =>
      expect(mocks.runPlan).toHaveBeenLastCalledWith({
        folder_path: "/media/incoming",
        strict_metadata: false,
        owner: "TripB",
        context: "Family",
        naming_strategy: "DUPLICATE_OWNS_DATE_STANDARDIZED",
        owner_context_override_confirmed: true,
      }),
    );
  }, 10000);

  it("closes the apply confirmation dialog immediately and keeps execution on the main panel", async () => {
    let resolveApply: ((value: { data: Record<string, unknown> }) => void) | null = null;
    mocks.runApply.mockReturnValue(
      new Promise((resolve) => {
        resolveApply = resolve;
      }),
    );

    renderPage();

    await screen.findByText("Continue a Saved Plan");
    fireEvent.click(
      screen.getByRole("button", {
        name: /Continue a Saved Plan/,
      }),
    );

    fireEvent.click(screen.getByRole("button", { name: "Apply Saved Work" }));
    fireEvent.click(await screen.findByRole("button", { name: "Confirm" }));

    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    await waitFor(() => expect(screen.getByRole("button", { name: "Apply Saved Work" })).toBeDisabled());
    expect(screen.getByText("Apply started. You can monitor progress below while the main screen stays available.")).toBeInTheDocument();

    resolveApply?.({
      data: {
        operation: "APPLY",
        success: true,
        summary: "Applied saved work.",
        details: { run_id: "durable-run-1" },
        duration_ms: 42,
      },
    });
  });

  it("applies saved work with a manually entered run id fallback", async () => {
    renderPage();

    await screen.findByText("Continue a Saved Plan");
    fireEvent.click(
      screen.getByRole("button", {
        name: /Continue a Saved Plan/,
      }),
    );

    fireEvent.click(screen.getByRole("button", { name: "Enter Run ID Instead" }));
    fireEvent.change(screen.getByPlaceholderText("00000000-0000-0000-0000-000000000000"), {
      target: { value: "manual-run-42" },
    });

    fireEvent.click(screen.getByRole("button", { name: "Apply Saved Work" }));
    fireEvent.click(await screen.findByRole("button", { name: "Confirm" }));

    await waitFor(() =>
      expect(mocks.runApply).toHaveBeenCalledWith({
        run_id: "manual-run-42",
        collision_mode: "rename",
      }),
    );
  });

  it("applies saved work using linked_run_id rather than the plan operation history id", async () => {
    renderPage();

    await screen.findByText("Continue a Saved Plan");
    fireEvent.click(
      screen.getByRole("button", {
        name: /Continue a Saved Plan/,
      }),
    );

    fireEvent.click(screen.getByRole("button", { name: "Apply Saved Work" }));
    fireEvent.click(await screen.findByRole("button", { name: "Confirm" }));

    await waitFor(() =>
      expect(mocks.runApply).toHaveBeenCalledWith({
        run_id: "durable-run-1",
        collision_mode: "rename",
      }),
    );
  });

  it("blocks apply when a selected saved plan is missing linked_run_id", async () => {
    mocks.getRuns.mockResolvedValueOnce({
      data: {
        items: [
          {
            operation_run_id: "plan-operation-without-link",
            operation_type: "PLAN",
            status: "COMPLETED",
            started_at: "2026-03-15T10:00:00Z",
            completed_at: "2026-03-15T10:01:00Z",
            duration_ms: 500,
            linked_run_id: null,
          },
        ],
      },
    });

    renderPage();

    await screen.findByText("Continue a Saved Plan");
    fireEvent.click(
      screen.getByRole("button", {
        name: /Continue a Saved Plan/,
      }),
    );

    expect(await screen.findByText("Not available for this saved plan.")).toBeInTheDocument();
    expect(
      screen.getByText(
        "This saved plan cannot be applied from Import because the completed PLAN entry does not include a durable run ID.",
      ),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Apply Saved Work" })).toBeDisabled();
    expect(mocks.runApply).not.toHaveBeenCalled();
  });

  it("shows finalizing ingest on the shared panel while refresh discovery is still finishing", async () => {
    let resolveIngest: ((value: { data: Record<string, unknown> }) => void) | null = null;
    mocks.runIngest.mockReturnValue(
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

    fireEvent.click(await screen.findByRole("button", { name: /Recheck a Folder/ }));
    fireEvent.click(screen.getByRole("button", { name: "Browse Folders" }));
    fireEvent.click(await screen.findByRole("button", { name: "Use This Path" }));
    fireEvent.click(await screen.findByRole("button", { name: "Refresh Discovery" }));
    fireEvent.click(await screen.findByRole("button", { name: "Confirm" }));

    expect(await screen.findByText("[ FINALIZING INGEST ]")).toBeInTheDocument();

    resolveIngest?.({
      data: {
        operation: "INGEST",
        success: true,
        summary: "Discovery refreshed.",
        details: { files_scanned: 2850 },
        duration_ms: 42,
      },
    });
  }, 10000);

  it("shows apply as running from request state even when no log KPI is available", async () => {
    let resolveApply: ((value: { data: Record<string, unknown> }) => void) | null = null;
    mocks.runApply.mockReturnValue(
      new Promise((resolve) => {
        resolveApply = resolve;
      }),
    );
    vi.spyOn(globalThis, "fetch").mockResolvedValue({
      ok: true,
      json: async () => [],
    } as Response);

    renderPage();

    await screen.findByText("Continue a Saved Plan");
    fireEvent.click(screen.getByRole("button", { name: /Continue a Saved Plan/ }));
    fireEvent.click(screen.getByRole("button", { name: "Apply Saved Work" }));
    fireEvent.click(await screen.findByRole("button", { name: "Confirm" }));

    expect(await screen.findByText("[ APPLY RUNNING ]")).toBeInTheDocument();

    resolveApply?.({
      data: {
        operation: "APPLY",
        success: true,
        summary: "Applied saved work.",
        details: { run_id: "durable-run-1" },
        duration_ms: 42,
      },
    });
  });

  it("shows canonical refresh as running from request state", async () => {
    let resolveCanonical: ((value: { data: Record<string, unknown> }) => void) | null = null;
    mocks.runCanonicalRecompute.mockReturnValue(
      new Promise((resolve) => {
        resolveCanonical = resolve;
      }),
    );
    vi.spyOn(globalThis, "fetch").mockResolvedValue({
      ok: true,
      json: async () => [],
    } as Response);

    renderPage();

    fireEvent.click(await screen.findByRole("button", { name: /Refresh Library Decisions/ }));
    fireEvent.click(screen.getByRole("button", { name: "Preview Refresh" }));
    fireEvent.click(await screen.findByRole("button", { name: "Confirm" }));

    expect(await screen.findByText("[ CANONICAL RUNNING ]")).toBeInTheDocument();

    resolveCanonical?.({
      data: {
        operation: "CANONICAL_RECOMPUTE",
        success: true,
        summary: "Previewed canonical refresh.",
        details: { changed_count: 1 },
        duration_ms: 42,
      },
    });
  });

  it("shows tag enrichment as running from request state", async () => {
    let resolveTag: ((value: { data: Record<string, unknown> }) => void) | null = null;
    mocks.runTagEnrichment.mockReturnValue(
      new Promise((resolve) => {
        resolveTag = resolve;
      }),
    );
    vi.spyOn(globalThis, "fetch").mockResolvedValue({
      ok: true,
      json: async () => [],
    } as Response);

    renderPage();

    fireEvent.click(await screen.findByRole("button", { name: /Add Searchable Details/ }));
    fireEvent.click(screen.getByRole("button", { name: "Add Searchable Details" }));
    fireEvent.click(await screen.findByRole("button", { name: "Confirm" }));

    expect(await screen.findByText("[ TAG RUNNING ]")).toBeInTheDocument();

    resolveTag?.({
      data: {
        operation: "TAG_ENRICHMENT",
        success: true,
        summary: "Enriched tags.",
        details: { number_of_items_processed: 2 },
        duration_ms: 42,
      },
    });
  });
});
