import { Toaster } from "@/components/ui/toaster";
import { Toaster as Sonner } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
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

const appRoutes = [
  { path: "/", element: <DashboardPage /> },
  { path: "/operations", element: <OperationsPage /> },
  { path: "/runs", element: <RunsPage /> },
  { path: "/ledger", element: <LedgerPage /> },
  { path: "/discover", element: <DiscoverPage /> },
  { path: "/duplicates", element: <DuplicatesPage /> },
  { path: "/policy", element: <PolicyPage /> },
  { path: "/admin", element: <AdminPage /> },
  { path: "/gallery", element: <GalleryPage /> },
] as const;

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
            <Route path="/console-v2" element={<Navigate to="/" replace />} />
            <Route path="*" element={<NotFound />} />
          </Routes>
        </AppLayout>
      </BrowserRouter>
    </TooltipProvider>
  </QueryClientProvider>
);

export default App;
