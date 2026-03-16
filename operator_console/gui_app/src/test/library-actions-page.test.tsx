import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import OperationsPage from "@/pages/OperationsPage";

const mocks = vi.hoisted(() => ({
  getDirectoryPickerCapability: vi.fn(),
  getRuns: vi.fn(),
  invalidateReadsAfterOperation: vi.fn(),
  runApply: vi.fn(),
  runCanonicalRecompute: vi.fn(),
  runIngest: vi.fn(),
  runPlan: vi.fn(),
  runTagEnrichment: vi.fn(),
}));

vi.mock("@/lib/api/endpoints", () => ({
  getDirectoryPickerCapability: mocks.getDirectoryPickerCapability,
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

describe("Library Actions page", () => {
  beforeEach(() => {
    mocks.getDirectoryPickerCapability.mockResolvedValue({
      data: { enabled: true, roots: [{ label: "Incoming", path: "/media/incoming" }] },
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

  it("renders the redesigned Library Actions sections", async () => {
    renderPage();

    expect(await screen.findByText("Library Actions")).toBeInTheDocument();
    expect(screen.getByText("Start from Folder")).toBeInTheDocument();
    expect(screen.getByText("Continue a Saved Plan")).toBeInTheDocument();
    expect(screen.getByText("Recheck a Folder")).toBeInTheDocument();
    expect(screen.getByText("Refresh Library Decisions")).toBeInTheDocument();
    expect(screen.getByText("Add Searchable Details")).toBeInTheDocument();
    expect(screen.queryByText("Legacy Composite Run")).not.toBeInTheDocument();
    expect(screen.queryByText("Mutating")).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Open Organize Media" })).toBeInTheDocument();
  });

  it("shows wizard-aligned guidance headings and keeps only one panel open", async () => {
    renderPage();

    const startPanelButton = await screen.findByRole("button", { name: /Start from Folder/ });
    expect(screen.queryByText("What this step does")).not.toBeInTheDocument();
    expect(startPanelButton.closest("[data-panel-state='open']")).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "Show step guidance" }));
    expect(await screen.findByText("What this step does")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /Continue a Saved Plan/ }));

    expect(startPanelButton.closest("[data-panel-state='closed']")).toBeTruthy();
    const continuePanelButton = screen.getByRole("button", { name: /Continue a Saved Plan/ });
    expect(continuePanelButton.closest("[data-panel-state='open']")).toBeTruthy();
    expect(screen.queryByText("What this step does")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Show step guidance" }));
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

    expect(screen.getByRole("button", { name: "Show step guidance" })).toBeInTheDocument();
    expect(screen.queryByText("What this step does")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Apply Saved Work" })).toBeInTheDocument();
  });

  it("keeps separate guidance toggles for recheck discovery and planning", async () => {
    renderPage();

    await screen.findByRole("button", { name: /Recheck a Folder/ });
    fireEvent.click(screen.getByRole("button", { name: /Recheck a Folder/ }));

    expect(screen.getByRole("button", { name: "Show refresh guidance" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Show planning guidance" })).toBeInTheDocument();
    expect(screen.queryByText("What this step does")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Show refresh guidance" }));
    expect(await screen.findByText("Refresh Discovery Guidance")).toBeInTheDocument();
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
        "This saved plan cannot be applied from Library Actions because the completed PLAN entry does not include a durable run ID.",
      ),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Apply Saved Work" })).toBeDisabled();
    expect(mocks.runApply).not.toHaveBeenCalled();
  });
});
