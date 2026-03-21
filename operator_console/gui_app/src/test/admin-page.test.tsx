import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import AdminPage from "@/pages/AdminPage";

const mocks = vi.hoisted(() => ({
  adminDbReset: vi.fn(),
  cancelBenchmarkRun: vi.fn(),
  getAdminObservabilityFailures: vi.fn(),
  getAdminObservabilityMetricsSeries: vi.fn(),
  getAdminObservabilityOperationRuns: vi.fn(),
  getAdminObservabilitySummary: vi.fn(),
  getAnalytics: vi.fn(),
  getBenchmarkRun: vi.fn(),
  getBenchmarkRuns: vi.fn(),
  getHashAudit: vi.fn(),
  getMediaByHash: vi.fn(),
  getMediaByStatus: vi.fn(),
  getMediaHistory: vi.fn(),
  getPolicy: vi.fn(),
  getReappearances: vi.fn(),
  getRuns: vi.fn(),
  invalidateAllReadsAfterDbReset: vi.fn(),
  invalidateReadsAfterPolicyUpdate: vi.fn(),
  queueDiscoveryBenchmark: vi.fn(),
  queueMetadataBenchmark: vi.fn(),
  updatePolicy: vi.fn(),
}));

vi.mock("@/lib/api/endpoints", () => ({
  adminDbReset: mocks.adminDbReset,
  cancelBenchmarkRun: mocks.cancelBenchmarkRun,
  getAdminObservabilityFailures: mocks.getAdminObservabilityFailures,
  getAdminObservabilityMetricsSeries: mocks.getAdminObservabilityMetricsSeries,
  getAdminObservabilityOperationRuns: mocks.getAdminObservabilityOperationRuns,
  getAdminObservabilitySummary: mocks.getAdminObservabilitySummary,
  getAnalytics: mocks.getAnalytics,
  getBenchmarkRun: mocks.getBenchmarkRun,
  getBenchmarkRuns: mocks.getBenchmarkRuns,
  getHashAudit: mocks.getHashAudit,
  getMediaByHash: mocks.getMediaByHash,
  getMediaByStatus: mocks.getMediaByStatus,
  getMediaHistory: mocks.getMediaHistory,
  getPolicy: mocks.getPolicy,
  getReappearances: mocks.getReappearances,
  getRuns: mocks.getRuns,
  invalidateAllReadsAfterDbReset: mocks.invalidateAllReadsAfterDbReset,
  invalidateReadsAfterPolicyUpdate: mocks.invalidateReadsAfterPolicyUpdate,
  queueDiscoveryBenchmark: mocks.queueDiscoveryBenchmark,
  queueMetadataBenchmark: mocks.queueMetadataBenchmark,
  updatePolicy: mocks.updatePolicy,
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
    <MemoryRouter initialEntries={["/admin?tab=activity"]}>
      <QueryClientProvider client={queryClient}>
        <AdminPage />
      </QueryClientProvider>
    </MemoryRouter>,
  );
}

describe("Admin page", () => {
  beforeEach(() => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue({
      ok: true,
      json: async () => [],
    } as Response);
    mocks.getRuns.mockResolvedValue({
      data: {
        items: [
          {
            operation_run_id: "run-1",
            operation_type: "PLAN",
            status: "STARTED",
            started_at: "2026-03-15T10:00:00Z",
            completed_at: null,
            duration_ms: null,
            linked_run_id: "durable-1",
            context: {},
            details: {},
          },
        ],
      },
    });
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it("renders the live progress panel in the activity detail rail", async () => {
    renderPage();

    expect(await screen.findByRole("tab", { name: "Activity" })).toBeInTheDocument();
    expect(screen.getByText("What happened in this job")).toBeInTheDocument();
    expect(await screen.findByText("[ WAITING FOR LOGS ]")).toBeInTheDocument();
  });
});
