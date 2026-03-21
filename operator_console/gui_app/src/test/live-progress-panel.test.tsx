import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { LiveProgressPanel } from "@/components/progress/LiveProgressPanel";
import { fireEvent } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

function renderWithQuery(ui: React.ReactNode) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
      },
    },
  });

  return render(
    <QueryClientProvider client={queryClient}>
      {ui}
    </QueryClientProvider>,
  );
}

describe("LiveProgressPanel", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("starts collapsed, keeps polling, and expands to show parsed progress with highlighting", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValueOnce({
        ok: true,
        json: async () => [
          "2026-03-21 INFO media_manager.app.persistence.planner phase=plan stage=action_generation processed_count=50 total_count=100 progress_percent=50.0 throughput_fps=25.0 Progress: 50/100 files (50.0%) | 25.0 files/sec | elapsed 2.0s",
        ],
      } as Response)
      .mockResolvedValueOnce({
        ok: true,
        json: async () => [
          "2026-03-21 INFO media_manager.app.persistence.planner phase=plan stage=action_generation processed_count=50 total_count=100 progress_percent=50.0 throughput_fps=25.0 Progress: 50/100 files (50.0%) | 25.0 files/sec | elapsed 2.0s",
          "2026-03-21 WARNING media_manager.app.persistence.planner slow batch",
          "2026-03-21 ERROR media_manager.app.persistence.planner failed item",
        ],
      } as Response);

    renderWithQuery(<LiveProgressPanel />);

    expect(await screen.findByText("[ PLAN RUNNING ]")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Show live progress" })).toBeInTheDocument();
    expect(screen.queryByText("50.0%")).not.toBeInTheDocument();

    await waitFor(
      () => expect(fetchMock).toHaveBeenCalledTimes(2),
      { timeout: 2_500 },
    );
    fireEvent.click(screen.getByRole("button", { name: "Show live progress" }));

    expect(await screen.findByText("50.0%")).toBeInTheDocument();
    expect(screen.getByText(/Current stage:/)).toBeInTheDocument();
    expect(screen.getByText("Action Generation")).toBeInTheDocument();
    expect(screen.getByText("50 / 100")).toBeInTheDocument();
    expect(screen.getByText("25.0 files/sec")).toBeInTheDocument();
    expect(await screen.findByText(/slow batch/)).toBeInTheDocument();
    expect(screen.getByText(/slow batch/).className).toContain("text-caution");
    expect(screen.getByText(/failed item/).className).toContain("text-destructive");
    expect(fetchMock).toHaveBeenCalledTimes(2);
    fireEvent.click(screen.getByRole("button", { name: "Hide live progress" }));
    expect(screen.queryByText(/slow batch/)).not.toBeInTheDocument();
  });

  it("shows a muted polling warning when log fetch fails", async () => {
    vi.spyOn(globalThis, "fetch").mockRejectedValue(new Error("network down"));

    renderWithQuery(<LiveProgressPanel />);

    expect(screen.getByText("[ WAITING FOR LOGS ]")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Show live progress" }));
    await waitFor(() =>
      expect(screen.getByText(/Live log polling is temporarily unavailable/)).toBeInTheDocument(),
    );
  });

  it("shares one polling source across multiple mounted panels", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue({
      ok: true,
      json: async () => [
        "2026-03-21 INFO media_manager.app.persistence.planner phase=plan processed_count=50 total_count=100 progress_percent=50.0 throughput_fps=25.0 Progress: 50/100 files (50.0%) | 25.0 files/sec | elapsed 2.0s",
      ],
    } as Response);

    renderWithQuery(
      <>
        <LiveProgressPanel />
        <LiveProgressPanel />
      </>,
    );

    expect(await screen.findAllByText("[ PLAN RUNNING ]")).toHaveLength(2);
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
  });

  it("pauses polling while the tab is hidden and resumes when visible again", async () => {
    let visibilityState: DocumentVisibilityState = "visible";
    Object.defineProperty(document, "visibilityState", {
      configurable: true,
      get: () => visibilityState,
    });

    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue({
      ok: true,
      json: async () => [
        "2026-03-21 INFO media_manager.app.persistence.ingest phase=ingest action=PROGRESS processed_count=20 total_count=50 progress_percent=40.0 throughput_fps=10.0 Progress: 20/50 files (40.0%) | 10.0 files/sec | elapsed 2.0s",
      ],
    } as Response);

    renderWithQuery(<LiveProgressPanel />);

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));

    visibilityState = "hidden";
    await new Promise((resolve) => window.setTimeout(resolve, 1_200));
    expect(fetchMock).toHaveBeenCalledTimes(1);

    visibilityState = "visible";
    document.dispatchEvent(new Event("visibilitychange"));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
  }, 10_000);

  it("uses request-backed finalizing state when the latest KPI reaches 100%", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue({
      ok: true,
      json: async () => [
        "2026-03-21 INFO media_manager.app.persistence.ingest phase=ingest action=PROGRESS processed_count=2850 total_count=2850 progress_percent=100.0 throughput_fps=25.0 Progress: 2850/2850 files (100.0%) | 25.0 files/sec | elapsed 113.9s",
      ],
    } as Response);

    renderWithQuery(<LiveProgressPanel operationKind="ingest" operationStatus="running" />);

    expect(await screen.findByText("[ FINALIZING INGEST ]")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Show live progress" }));
    expect(await screen.findByText(/The latest progress checkpoint has been reached/)).toBeInTheDocument();
    expect(screen.getByText("100.0%")).toBeInTheDocument();
    expect(screen.getByText("2850 / 2850")).toBeInTheDocument();
  });

  it("shows explicit completion state even when logs are quiet", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue({
      ok: true,
      json: async () => [],
    } as Response);

    renderWithQuery(<LiveProgressPanel operationKind="apply" operationStatus="completed" />);

    expect(await screen.findByText("[ APPLY COMPLETE ]")).toBeInTheDocument();
  });

  it("uses generic processed and item speed labels for non-file phases", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue({
      ok: true,
      json: async () => [
        "2026-03-21 INFO media_manager.app.persistence.apply phase=apply stage=execute_actions processed_count=100 total_count=120 progress_percent=83.3 throughput_fps=40.0 Progress: 100/120 items (83.3%) | 40.0 items/sec | elapsed 2.5s",
      ],
    } as Response);

    renderWithQuery(<LiveProgressPanel operationKind="apply" operationStatus="running" />);

    expect(await screen.findByText("[ APPLY RUNNING ]")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Show live progress" }));
    expect(await screen.findByText("Processed")).toBeInTheDocument();
    expect(screen.getByText("100 / 120")).toBeInTheDocument();
    expect(screen.getByText("40.0 items/sec")).toBeInTheDocument();
  });
});
