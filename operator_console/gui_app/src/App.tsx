import { Toaster } from "@/components/ui/toaster";
import { Toaster as Sonner } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Navigate, Route, Routes, useLocation } from "react-router-dom";
import { AppLayout } from "@/components/AppLayout";
import DashboardPage from "@/pages/DashboardPage";
import OperationsPage from "@/pages/OperationsPage";
import PipelineWizard from "@/pages/PipelineWizard";
import DuplicatesPage from "@/pages/DuplicatesPage";
import PolicyPage from "@/pages/PolicyPage";
import AdminPage from "@/pages/AdminPage";
import DiagnosticsPage from "@/pages/DiagnosticsPage";
import GalleryPage from "@/pages/GalleryPage";
import MediaDetailPage from "@/pages/MediaDetailPage";
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

const appRoutes = [
  { path: "/", element: <DashboardPage /> },
  { path: "/operations", element: <OperationsPage /> },
  { path: "/pipeline-wizard", element: <PipelineWizard /> },
  { path: "/admin/diagnostics", element: <DiagnosticsPage /> },
  { path: "/duplicates", element: <DuplicatesPage /> },
  { path: "/policy", element: <PolicyPage /> },
  { path: "/admin", element: <AdminPage /> },
  { path: "/gallery", element: <GalleryPage /> },
  { path: "/gallery/:fileId", element: <MediaDetailPage /> },
] as const;

function DiscoverRedirect() {
  const location = useLocation();
  return <Navigate replace to={`/gallery${location.search}`} />;
}

function RunsRedirect() {
  return <Navigate replace to="/admin?tab=activity" />;
}

function LedgerRedirect() {
  return <Navigate replace to="/admin?tab=file-history" />;
}

const App = () => (
  <QueryClientProvider client={queryClient}>
    <TooltipProvider>
      <Toaster />
      <Sonner />
      <BrowserRouter>
        <AppLayout>
          <Routes>
            {appRoutes.map((route) => (
              <Route key={route.path} path={route.path} element={route.element} />
            ))}
            <Route path="/runs" element={<RunsRedirect />} />
            <Route path="/ledger" element={<LedgerRedirect />} />
            <Route path="/discover" element={<DiscoverRedirect />} />
            <Route path="*" element={<NotFound />} />
          </Routes>
        </AppLayout>
      </BrowserRouter>
    </TooltipProvider>
  </QueryClientProvider>
);

export default App;
