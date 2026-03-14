import { Toaster } from "@/components/ui/toaster";
import { Toaster as Sonner } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import { TopBar } from "@/components/layout/TopBar";
import Dashboard from "@/pages/Dashboard";
import Operations from "@/pages/Operations";
import Runs from "@/pages/Runs";
import Ledger from "@/pages/Ledger";
import Duplicates from "@/pages/Duplicates";
import Policy from "@/pages/Policy";
import Admin from "@/pages/Admin";
import Gallery from "@/pages/Gallery";
import MediaDetail from "@/pages/MediaDetail";
import NotFound from "@/pages/NotFound";

const queryClient = new QueryClient();

const App = () => (
  <QueryClientProvider client={queryClient}>
    <TooltipProvider>
      <Toaster />
      <Sonner />
      <BrowserRouter>
        <TopBar>
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/operations" element={<Operations />} />
            <Route path="/runs" element={<Runs />} />
            <Route path="/ledger" element={<Ledger />} />
            <Route path="/duplicates" element={<Duplicates />} />
            <Route path="/policy" element={<Policy />} />
            <Route path="/admin" element={<Admin />} />
            <Route path="/gallery" element={<Gallery />} />
            <Route path="/media" element={<MediaDetail />} />
            <Route path="*" element={<NotFound />} />
          </Routes>
        </TopBar>
      </BrowserRouter>
    </TooltipProvider>
  </QueryClientProvider>
);

export default App;
