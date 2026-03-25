import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import IntegrityPage from "@/pages/IntegrityPage";

const mocks = vi.hoisted(() => ({
  getIntegrityDashboard: vi.fn(),
  getIntegrityFile: vi.fn(),
  getIntegrityIssues: vi.fn(),
  setIntegrityReview: vi.fn(),
  startIntegrityScan: vi.fn(),
}));

vi.mock("@/lib/api/endpoints", () => ({
  getIntegrityDashboard: mocks.getIntegrityDashboard,
  getIntegrityFile: mocks.getIntegrityFile,
  getIntegrityIssues: mocks.getIntegrityIssues,
  setIntegrityReview: mocks.setIntegrityReview,
  startIntegrityScan: mocks.startIntegrityScan,
}));

function renderPage() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });

  return render(
    <MemoryRouter>
      <QueryClientProvider client={queryClient}>
        <IntegrityPage />
      </QueryClientProvider>
    </MemoryRouter>,
  );
}

describe("IntegrityPage", () => {
  beforeEach(() => {
    mocks.getIntegrityDashboard.mockResolvedValue({
      data: {
        total_files_scanned: 12,
        playback_issues: 3,
        quarantined: 0,
        last_scan_at: "2026-03-25T10:00:00+00:00",
        broken_count: 1,
        suspect_count: 2,
        ignored_count: 0,
        marked_ok_count: 1,
      },
    });
    mocks.getIntegrityIssues.mockResolvedValue({
      data: {
        items: [
          {
            check_id: "check-1",
            file_instance_id: "file-1",
            absolute_path: "/media/problem.mp4",
            status: "BROKEN",
            confidence: 0.93,
            probe_status: "FAILED",
            decode_status: "SKIPPED",
            reviewed_decision: null,
            reviewed_at: null,
            signal_types: ["ffprobe_failed"],
          },
        ],
      },
    });
    mocks.getIntegrityFile.mockResolvedValue({
      data: {
        check_id: "check-1",
        file_instance_id: "file-1",
        absolute_path: "/media/problem.mp4",
        status: "BROKEN",
        confidence: 0.93,
        probe_status: "FAILED",
        decode_status: "SKIPPED",
        reviewed_decision: null,
        reviewed_at: null,
        signals: [
          {
            signal_type: "ffprobe_failed",
            severity: "error",
            details: { stderr: "bad file" },
            created_at: "2026-03-25T10:00:00+00:00",
          },
        ],
      },
    });
    mocks.setIntegrityReview.mockResolvedValue({ data: {} });
    mocks.startIntegrityScan.mockResolvedValue({ data: { run_id: "run-1" } });
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it("renders dashboard, queue, and detail data", async () => {
    renderPage();

    expect(await screen.findByText("Integrity Review")).toBeInTheDocument();
    expect(screen.getByText("Playback Issues")).toBeInTheDocument();
    expect(await screen.findByText("problem.mp4")).toBeInTheDocument();
    expect(screen.getAllByText("ffprobe_failed").length).toBeGreaterThan(0);
  });

  it("starts a quick scan from the page header", async () => {
    renderPage();

    fireEvent.click(await screen.findByRole("button", { name: "Run Quick Scan" }));

    await waitFor(() => expect(mocks.startIntegrityScan).toHaveBeenCalledWith({ mode: "FAST" }));
  });

  it("submits mark as ok review decisions", async () => {
    renderPage();

    fireEvent.click(await screen.findByRole("button", { name: "Mark as OK" }));

    await waitFor(() =>
      expect(mocks.setIntegrityReview).toHaveBeenCalledWith({
        check_id: "check-1",
        decision: "MARK_OK",
      }),
    );
  });
});
