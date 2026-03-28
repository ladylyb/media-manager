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

vi.mock("@/components/progress/LiveProgressPanel", () => ({
  LiveProgressPanel: ({
    operationKind,
    operationStatus,
  }: {
    operationKind?: string;
    operationStatus?: string;
  }) => (
    <div data-testid="live-progress-panel">
      Live progress panel {operationKind ?? "none"} {operationStatus ?? "idle"}
    </div>
  ),
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
        last_checked_at: "2026-03-25T09:00:00+00:00",
        probe_status: "FAILED",
        decode_status: "SKIPPED",
        reviewed_decision: "MARK_OK",
        reviewed_at: "2026-03-25T11:00:00+00:00",
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
        skipped_count: 0,
        issues_found: 3,
        full_rescan: false,
      },
    });
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it("renders dashboard, queue, and detail data", async () => {
    renderPage();

    expect(await screen.findByText("Integrity Checks")).toBeInTheDocument();
    expect(screen.getByText("Integrity Scan Status")).toBeInTheDocument();
    expect(
      screen.getByText("Start a Quick Scan or Deep Scan above. Live activity and the latest scan summary will appear here."),
    ).toBeInTheDocument();
    expect(screen.getByText("Quick Scan checks file readability and basic media structure.")).toBeInTheDocument();
    expect(screen.getByText("Deep Scan adds a short playback-level check.")).toBeInTheDocument();
    expect(screen.getByText("By default, unchanged files are skipped.")).toBeInTheDocument();
    expect(screen.getByText("Full rescan checks everything again.")).toBeInTheDocument();
    expect(await screen.findByText(/Last library scan run/)).toBeInTheDocument();
    expect(screen.getByText("Playback Issues")).toBeInTheDocument();
    expect((await screen.findAllByText("problem.mp4")).length).toBeGreaterThan(0);
    expect(screen.getByText("Last checked for this file")).toBeInTheDocument();
    expect(screen.getByText("Review recorded")).toBeInTheDocument();
    expect(screen.getAllByText("ffprobe_failed").length).toBeGreaterThan(0);
  });

  it("quick scan shows in-flight state and then success summary", async () => {
    const deferred = createDeferred<{ data: { run_id: string; scan_mode: "FAST"; eligible_file_count: number; scanned_count: number; skipped_count: number; issues_found: number; full_rescan: boolean } }>();
    mocks.startIntegrityScan.mockReturnValueOnce(deferred.promise);
    renderPage();

    fireEvent.click(await screen.findByRole("button", { name: "Quick Scan" }));

    expect(await screen.findByRole("button", { name: "Running Quick Scan..." })).toBeDisabled();
    expect(screen.getByText("Scan Running")).toBeInTheDocument();
    expect(screen.getByText("Quick scan started.")).toBeInTheDocument();
    expect(screen.getByTestId("live-progress-panel")).toHaveTextContent("Live progress panel integrity running");
    deferred.resolve({
      data: {
        run_id: "run-1",
        scan_mode: "FAST",
        eligible_file_count: 12,
        scanned_count: 12,
        skipped_count: 0,
        issues_found: 3,
        full_rescan: false,
      },
    });
    await waitFor(() => expect(mocks.startIntegrityScan).toHaveBeenCalledWith({ mode: "FAST", full_rescan: false }));
    expect(await screen.findByText("Integrity Scan Result")).toBeInTheDocument();
    expect(screen.getByText("Scan Complete")).toBeInTheDocument();
    expect(screen.getByText("Quick scan finished. Unchanged files were skipped.")).toBeInTheDocument();
    expect(screen.getByText("The results below have been refreshed.")).toBeInTheDocument();
    expect(screen.getByText("Run ID")).toBeInTheDocument();
    expect(screen.getByText("Files considered")).toBeInTheDocument();
    expect(screen.getByText("Files checked now")).toBeInTheDocument();
    expect(screen.getByText("Files skipped because unchanged")).toBeInTheDocument();
    expect(screen.getByText("Files with problems")).toBeInTheDocument();
    expect(screen.getAllByText("Quick").length).toBeGreaterThan(0);
    expect(screen.getAllByText("12").length).toBeGreaterThan(1);
    expect(screen.getAllByText("3").length).toBeGreaterThan(0);
  });

  it("deep scan shows in-flight state and then success summary", async () => {
    const deferred = createDeferred<{ data: { run_id: string; scan_mode: "DEEP"; eligible_file_count: number; scanned_count: number; skipped_count: number; issues_found: number; full_rescan: boolean } }>();
    mocks.startIntegrityScan.mockReturnValueOnce(deferred.promise);

    renderPage();

    fireEvent.click(await screen.findByRole("button", { name: "Deep Scan" }));

    expect(await screen.findByRole("button", { name: "Running Deep Scan..." })).toBeDisabled();
    expect(screen.getByText("Deep scan started.")).toBeInTheDocument();
    expect(screen.getByTestId("live-progress-panel")).toHaveTextContent("Live progress panel integrity running");
    deferred.resolve({
      data: {
        run_id: "run-2",
        scan_mode: "DEEP",
        eligible_file_count: 12,
        scanned_count: 12,
        skipped_count: 0,
        issues_found: 4,
        full_rescan: false,
      },
    });

    await waitFor(() => expect(mocks.startIntegrityScan).toHaveBeenCalledWith({ mode: "DEEP", full_rescan: false }));
    expect(await screen.findByText("Deep scan finished. Unchanged files were skipped.")).toBeInTheDocument();
    expect(screen.getByText("Files considered")).toBeInTheDocument();
    expect(screen.getByText("Files checked now")).toBeInTheDocument();
    expect(screen.getByText("Files skipped because unchanged")).toBeInTheDocument();
    expect(screen.getByText("Files with problems")).toBeInTheDocument();
    expect(screen.getAllByText("Deep").length).toBeGreaterThan(0);
    expect(screen.getAllByText("12").length).toBeGreaterThan(1);
    expect(screen.getByText("4")).toBeInTheDocument();
  });

  it("shows a visible message when no eligible files were scanned", async () => {
    mocks.startIntegrityScan.mockResolvedValueOnce({
      data: {
        run_id: "run-3",
        scan_mode: "FAST",
        eligible_file_count: 0,
        scanned_count: 0,
        skipped_count: 0,
        issues_found: 0,
        full_rescan: false,
      },
    });

    renderPage();

    fireEvent.click(await screen.findByRole("button", { name: "Quick Scan" }));

    expect(await screen.findByText("No library files were ready to be checked right now.")).toBeInTheDocument();
  });

  it("does not let persisted deep default override explicit quick scan", async () => {
    renderPage();

    expect(await screen.findByText("Saved default scan mode: Deep")).toBeInTheDocument();
    expect(screen.getByText("Quick Scan checks file readability and basic media structure.")).toBeInTheDocument();
    expect(screen.getByText("Deep Scan adds a short playback-level check.")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Quick Scan" }));

    await waitFor(() => expect(mocks.startIntegrityScan).toHaveBeenCalledWith({ mode: "FAST", full_rescan: false }));
  });

  it("shows a visible error when the scan fails", async () => {
    mocks.startIntegrityScan.mockRejectedValueOnce(new Error("ffprobe unavailable"));

    renderPage();

    fireEvent.click(await screen.findByRole("button", { name: "Quick Scan" }));

    expect(await screen.findByText("Scan Failed")).toBeInTheDocument();
    expect(screen.getByText("Quick scan failed before the page could refresh with new results.")).toBeInTheDocument();
    expect(screen.getByText("ffprobe unavailable")).toBeInTheDocument();
  });

  it("keeps the last scan summary visible after completion", async () => {
    renderPage();

    fireEvent.click(await screen.findByRole("button", { name: "Quick Scan" }));

    expect(await screen.findByText("Integrity Scan Result")).toBeInTheDocument();
    expect(screen.getByText("Quick scan finished. Unchanged files were skipped.")).toBeInTheDocument();
    expect(screen.getAllByText("Quick").length).toBeGreaterThan(0);
  });

  it("sends the full rescan override and surfaces skipped files in the summary", async () => {
    mocks.startIntegrityScan.mockResolvedValueOnce({
      data: {
        run_id: "run-4",
        scan_mode: "FAST",
        eligible_file_count: 12,
        scanned_count: 12,
        skipped_count: 0,
        issues_found: 3,
        full_rescan: true,
      },
    });

    renderPage();

    fireEvent.click(await screen.findByLabelText("Full rescan"));
    fireEvent.click(screen.getByRole("button", { name: "Quick Scan" }));

    await waitFor(() =>
      expect(mocks.startIntegrityScan).toHaveBeenCalledWith({ mode: "FAST", full_rescan: true }),
    );
    expect(await screen.findByText("Quick scan finished as a full rescan. All files were checked again.")).toBeInTheDocument();
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
