import { TopBar } from "@/components/layout/TopBar";

export function AppLayout({ children }: { children: React.ReactNode }) {
  return <TopBar>{children}</TopBar>;
}
