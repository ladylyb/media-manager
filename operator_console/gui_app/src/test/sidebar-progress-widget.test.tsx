import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";

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
  it("does not render any live progress widget when the sidebar is expanded", () => {
    renderSidebar(true);

    expect(screen.queryByText("Live Progress")).not.toBeInTheDocument();
  });

  it("does not render any live progress widget when the sidebar is collapsed", () => {
    renderSidebar(false);

    expect(screen.queryByText("Live Progress")).not.toBeInTheDocument();
  });
});
