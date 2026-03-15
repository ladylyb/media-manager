import { SidebarProvider, SidebarTrigger } from "@/components/ui/sidebar";
import { Sidebar } from "@/components/layout/Sidebar";
import { StatusStrip } from "@/components/layout/StatusStrip";

export function TopBar({ children }: { children: React.ReactNode }) {
  return (
    <SidebarProvider>
      <div className="flex min-h-screen w-full">
        <Sidebar />
        <div className="flex min-w-0 flex-1 flex-col">
          <StatusStrip />
          <header className="flex h-11 shrink-0 items-center border-b bg-card px-2">
            <SidebarTrigger className="ml-1" />
          </header>
          <main className="flex-1 overflow-auto scrollbar-thin">{children}</main>
        </div>
      </div>
    </SidebarProvider>
  );
}
