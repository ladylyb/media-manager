import { Info } from "lucide-react";

interface WizardGuidanceSection {
  title: string;
  content: string;
}

interface WizardGuidancePanelProps {
  sections: WizardGuidanceSection[];
}

export function WizardGuidancePanel({ sections }: WizardGuidancePanelProps) {
  return (
    <div className="rounded-2xl border border-primary/15 bg-primary/[0.04] p-4 sm:p-5">
      <div className="flex items-center gap-2">
        <Info className="h-4 w-4 text-primary" />
        <p className="text-xs font-semibold uppercase tracking-[0.22em] text-primary/80">
          Step Guidance
        </p>
      </div>

      <div className="mt-4 grid gap-3 xl:grid-cols-2">
        {sections.map((section) => (
          <div key={section.title} className="rounded-xl border border-border/70 bg-background/80 p-4 shadow-sm">
            <p className="text-[11px] font-semibold uppercase tracking-[0.2em] text-muted-foreground">
              {section.title}
            </p>
            <p className="mt-2 text-sm leading-6 text-foreground/90">{section.content}</p>
          </div>
        ))}
      </div>
    </div>
  );
}
