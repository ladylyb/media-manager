import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { LiveProgressPanel } from "@/components/progress/LiveProgressPanel";
import { fireEvent } from "@testing-library/react";

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
          "2026-03-21 INFO media_manager.app.persistence.planner phase=plan processed_count=50 total_count=100 progress_percent=50.0 throughput_fps=25.0 Progress: 50/100 files (50.0%) | 25.0 files/sec | elapsed 2.0s",
        ],
      } as Response)
      .mockResolvedValueOnce({
        ok: true,
        json: async () => [
          "2026-03-21 INFO media_manager.app.persistence.planner phase=plan processed_count=50 total_count=100 progress_percent=50.0 throughput_fps=25.0 Progress: 50/100 files (50.0%) | 25.0 files/sec | elapsed 2.0s",
          "2026-03-21 WARNING media_manager.app.persistence.planner slow batch",
          "2026-03-21 ERROR media_manager.app.persistence.planner failed item",
        ],
      } as Response);

    render(<LiveProgressPanel />);

    expect(await screen.findByText("[ PLAN RUNNING ]")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Show live progress" })).toBeInTheDocument();
    expect(screen.queryByText("50.0%")).not.toBeInTheDocument();

    await waitFor(
      () => expect(fetchMock).toHaveBeenCalledTimes(2),
      { timeout: 2_500 },
    );
    fireEvent.click(screen.getByRole("button", { name: "Show live progress" }));

    expect(await screen.findByText("50.0%")).toBeInTheDocument();
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

    render(<LiveProgressPanel />);

    expect(screen.getByText("[ WAITING FOR LOGS ]")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Show live progress" }));
    await waitFor(() =>
      expect(screen.getByText(/Live log polling is temporarily unavailable/)).toBeInTheDocument(),
    );
  });
});
