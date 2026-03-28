import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import IntegrityPage from "@/pages/IntegrityPage";

const mocks = vi.hoisted(() => ({
  getPolicy: vi.fn(),
  getIntegrityDashboard: vi.fn(),
  getIntegrityFile: vi.fn(),
  getIntegrityIssues: vi.fn(),
  getIntegrityQuarantineItems: vi.fn(),
  setIntegrityReview: vi.fn(),
  startIntegrityScan: vi.fn(),
  quarantineIntegrityFile: vi.fn(),
  restoreIntegrityFile: vi.fn(),
}));

vi.mock("@/lib/api/endpoints", () => ({
  getPolicy: mocks.getPolicy,
  getIntegrityDashboard: mocks.getIntegrityDashboard,
  getIntegrityFile: mocks.getIntegrityFile,
  getIntegrityIssues: mocks.getIntegrityIssues,
  getIntegrityQuarantineItems: mocks.getIntegrityQuarantineItems,
  setIntegrityReview: mocks.setIntegrityReview,
  startIntegrityScan: mocks.startIntegrityScan,
  quarantineIntegrityFile: mocks.quarantineIntegrityFile,
  restoreIntegrityFile: mocks.restoreIntegrityFile,
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

function createDeferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (error?: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

describe("IntegrityPage", () => {
  beforeEach(() => {
    mocks.getPolicy.mockResolvedValue({
      data: {
        integrity: {
          default_scan_mode: "DEEP",
          issue_min_confidence: 0.9,
          notify_on_high_confidence: true,
        },
      },
    });
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
        high_confidence_unresolved_count: 1,
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
    mocks.getIntegrityQuarantineItems.mockResolvedValue({ data: { items: [] } });
    mocks.quarantineIntegrityFile.mockResolvedValue({ data: {} });
    mocks.restoreIntegrityFile.mockResolvedValue({ data: {} });
    mocks.startIntegrityScan.mockResolvedValue({
      data: {
        run_id: "run-1",
        scan_mode: "FAST",
        eligible_file_count: 12,
        scanned_count: 12,
        issues_found: 3,
      },
    });
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

  it("quick scan shows in-flight state and then success summary", async () => {
    const deferred = createDeferred<{ data: { run_id: string; scan_mode: "FAST"; eligible_file_count: number; scanned_count: number; issues_found: number } }>();
    mocks.startIntegrityScan.mockReturnValueOnce(deferred.promise);
    renderPage();

    fireEvent.click(await screen.findByRole("button", { name: "Quick Scan" }));

    expect(await screen.findByRole("button", { name: "Running Quick Scan..." })).toBeDisabled();
    expect(screen.getByText("Quick scan started")).toBeInTheDocument();
    deferred.resolve({
      data: {
        run_id: "run-1",
        scan_mode: "FAST",
        eligible_file_count: 12,
        scanned_count: 12,
        issues_found: 3,
      },
    });
    await waitFor(() => expect(mocks.startIntegrityScan).toHaveBeenCalledWith({ mode: "FAST" }));
    expect(await screen.findByText("Last scan summary")).toBeInTheDocument();
    expect(screen.getByText("Quick scan completed")).toBeInTheDocument();
    expect(screen.getByText("Mode used: Quick")).toBeInTheDocument();
    expect(screen.getByText("Eligible files: 12")).toBeInTheDocument();
    expect(screen.getByText("Files scanned: 12")).toBeInTheDocument();
    expect(screen.getByText("Issues found: 3")).toBeInTheDocument();
  });

  it("deep scan shows in-flight state and then success summary", async () => {
    const deferred = createDeferred<{ data: { run_id: string; scan_mode: "DEEP"; eligible_file_count: number; scanned_count: number; issues_found: number } }>();
    mocks.startIntegrityScan.mockReturnValueOnce(deferred.promise);

    renderPage();

    fireEvent.click(await screen.findByRole("button", { name: "Deep Scan" }));

    expect(await screen.findByRole("button", { name: "Running Deep Scan..." })).toBeDisabled();
    expect(screen.getByText("Deep scan started")).toBeInTheDocument();
    deferred.resolve({
      data: {
        run_id: "run-2",
        scan_mode: "DEEP",
        eligible_file_count: 12,
        scanned_count: 12,
        issues_found: 4,
      },
    });

    await waitFor(() => expect(mocks.startIntegrityScan).toHaveBeenCalledWith({ mode: "DEEP" }));
    expect(await screen.findByText("Deep scan completed")).toBeInTheDocument();
    expect(screen.getByText("Mode used: Deep")).toBeInTheDocument();
    expect(screen.getByText("Eligible files: 12")).toBeInTheDocument();
    expect(screen.getByText("Files scanned: 12")).toBeInTheDocument();
    expect(screen.getByText("Issues found: 4")).toBeInTheDocument();
  });

  it("shows a visible message when no eligible files were scanned", async () => {
    mocks.startIntegrityScan.mockResolvedValueOnce({
      data: {
        run_id: "run-3",
        scan_mode: "FAST",
        eligible_file_count: 0,
        scanned_count: 0,
        issues_found: 0,
      },
    });

    renderPage();

    fireEvent.click(await screen.findByRole("button", { name: "Quick Scan" }));

    expect(await screen.findByText("No eligible active files were scanned.")).toBeInTheDocument();
  });

  it("does not let persisted deep default override explicit quick scan", async () => {
    renderPage();

    expect(await screen.findByText("Saved default scan mode: Deep")).toBeInTheDocument();
    expect(screen.getByText("Quick Scan: readability and probe checks")).toBeInTheDocument();
    expect(screen.getByText("Deep Scan: quick scan plus decode-level verification on eligible active files")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Quick Scan" }));

    await waitFor(() => expect(mocks.startIntegrityScan).toHaveBeenCalledWith({ mode: "FAST" }));
  });

  it("shows a visible error when the scan fails", async () => {
    mocks.startIntegrityScan.mockRejectedValueOnce(new Error("ffprobe unavailable"));

    renderPage();

    fireEvent.click(await screen.findByRole("button", { name: "Quick Scan" }));

    expect(await screen.findByText("Quick scan failed: ffprobe unavailable")).toBeInTheDocument();
    expect(screen.getByText("Last scan summary")).toBeInTheDocument();
    expect(screen.getByText("Status: failed")).toBeInTheDocument();
  });

  it("keeps the last scan summary visible after completion", async () => {
    renderPage();

    fireEvent.click(await screen.findByRole("button", { name: "Quick Scan" }));

    expect(await screen.findByText("Last scan summary")).toBeInTheDocument();
    expect(screen.getByText("Quick scan completed")).toBeInTheDocument();
    expect(screen.getByText("Mode used: Quick")).toBeInTheDocument();
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
