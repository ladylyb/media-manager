import { SidebarProvider, SidebarTrigger } from "@/components/ui/sidebar";
import { Sidebar } from "@/components/layout/Sidebar";
import { StatusStrip } from "@/components/layout/StatusStrip";

export function TopBar({ children }: { children: React.ReactNode }) {
  return (
    <SidebarProvider>
      <div className="min-h-screen flex w-full">
        <Sidebar />
        <div className="flex-1 flex flex-col min-w-0">
          <StatusStrip />
          <header className="h-11 flex items-center border-b bg-card px-2 shrink-0">
            <SidebarTrigger className="ml-1" />
          </header>
          <main className="flex-1 overflow-auto scrollbar-thin">
            {children}
          </main>
        </div>
      </div>
    </SidebarProvider>
  );
}
