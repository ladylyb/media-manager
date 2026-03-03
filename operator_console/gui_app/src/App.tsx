import { Toaster } from "@/components/ui/toaster";
import { Toaster as Sonner } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import { AppLayout } from "@/components/AppLayout";
import DashboardPage from "@/pages/DashboardPage";
import OperationsPage from "@/pages/OperationsPage";
import RunsPage from "@/pages/RunsPage";
import LedgerPage from "@/pages/LedgerPage";
import DiscoverPage from "@/pages/DiscoverPage";
import DuplicatesPage from "@/pages/DuplicatesPage";
import PolicyPage from "@/pages/PolicyPage";
import AdminPage from "@/pages/AdminPage";
import GalleryPage from "@/pages/GalleryPage";
import NotFound from "./pages/NotFound";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      refetchOnWindowFocus: false,
      refetchOnReconnect: true,
      staleTime: 30_000,
      gcTime: 5 * 60_000,
    },
  },
});

const App = () => (
  <QueryClientProvider client={queryClient}>
    <TooltipProvider>
      <Toaster />
      <Sonner />
      <BrowserRouter>
        <AppLayout>
          <Routes>
            <Route path="/" element={<DashboardPage />} />
            <Route path="/console-v2" element={<DashboardPage />} />
            <Route path="/operations" element={<OperationsPage />} />
            <Route path="/runs" element={<RunsPage />} />
            <Route path="/ledger" element={<LedgerPage />} />
            <Route path="/discover" element={<DiscoverPage />} />
            <Route path="/duplicates" element={<DuplicatesPage />} />
            <Route path="/policy" element={<PolicyPage />} />
            <Route path="/admin" element={<AdminPage />} />
            <Route path="/gallery" element={<GalleryPage />} />
            <Route path="*" element={<NotFound />} />
          </Routes>
        </AppLayout>
      </BrowserRouter>
    </TooltipProvider>
  </QueryClientProvider>
);

export default App;
