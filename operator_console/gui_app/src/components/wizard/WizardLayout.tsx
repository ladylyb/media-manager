import type { ReactNode } from "react";

interface WizardLayoutProps {
  header?: ReactNode;
  children: ReactNode;
}

export function WizardLayout({ header, children }: WizardLayoutProps) {
  return (
    <div className="mx-auto max-w-7xl space-y-6 p-6">
      {header}
      <div className="min-w-0">{children}</div>
    </div>
  );
}
