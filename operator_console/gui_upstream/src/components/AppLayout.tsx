import { SidebarProvider, SidebarTrigger } from "@/components/ui/sidebar";
import { AppSidebar } from "@/components/AppSidebar";
import { StatusBar } from "@/components/StatusBar";

export function AppLayout({ children }: { children: React.ReactNode }) {
  return (
    <SidebarProvider>
      <div className="min-h-screen flex w-full">
        <AppSidebar />
        <div className="flex-1 flex flex-col min-w-0">
          <StatusBar />
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
