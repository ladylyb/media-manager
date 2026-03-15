import type { ReactNode } from "react";
import { WizardSidebar, type WizardSidebarItem } from "./WizardSidebar";

interface WizardLayoutProps {
  sidebarItems: WizardSidebarItem[];
  children: ReactNode;
}

export function WizardLayout({ sidebarItems, children }: WizardLayoutProps) {
  return (
    <div className="mx-auto grid max-w-7xl gap-6 p-6 xl:grid-cols-[20rem_minmax(0,1fr)]">
      <div className="xl:sticky xl:top-6 xl:self-start">
        <WizardSidebar items={sidebarItems} />
      </div>
      <div className="min-w-0">{children}</div>
    </div>
  );
}
