import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { Sidebar } from "@/components/layout/Sidebar";
import { SidebarProvider } from "@/components/ui/sidebar";

function renderSidebar(open = true) {
  return render(
    <MemoryRouter>
      <SidebarProvider open={open}>
        <Sidebar />
      </SidebarProvider>
    </MemoryRouter>,
  );
}

describe("Sidebar progress widget", () => {
  beforeEach(() => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue({
      ok: true,
      json: async () => [
        "2026-03-21 INFO media_manager.app.persistence.ingest phase=ingest action=PROGRESS processed_count=20 total_count=50 progress_percent=40.0 throughput_fps=10.0 Progress: 20/50 files (40.0%) | 10.0 files/sec | elapsed 2.0s",
      ],
    } as Response);
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it("shows the compact widget collapsed by default and expands on demand", async () => {
    renderSidebar(true);

    expect(await screen.findByText("Live Progress")).toBeInTheDocument();
    expect(screen.getAllByText("20 / 50 files").length).toBe(1);
    fireEvent.click(screen.getByRole("button", { name: /Show/ }));
    expect(screen.getAllByText("20 / 50 files").length).toBe(2);
    fireEvent.click(screen.getByRole("button", { name: /Hide/ }));
    expect(screen.getAllByText("20 / 50 files").length).toBe(1);
  });

  it("hides the compact widget when the sidebar is collapsed", () => {
    renderSidebar(false);

    expect(screen.queryByText("Live Progress")).not.toBeInTheDocument();
  });
});
