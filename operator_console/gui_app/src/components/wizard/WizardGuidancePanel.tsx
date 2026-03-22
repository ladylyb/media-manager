import { Info } from "lucide-react";
import { ExpandableSummaryPanel } from "@/components/ExpandableSummaryPanel";
import { cn } from "@/lib/utils";

export interface WizardGuidanceSection {
  title: string;
  content: string;
}

interface WizardGuidancePanelProps {
  sections: WizardGuidanceSection[];
  title?: string;
  subtitle?: string;
  showLabel?: string;
  hideLabel?: string;
  defaultOpen?: boolean;
  gridClassName?: string;
  className?: string;
  panelClassName?: string;
}

export function WizardGuidancePanel({
  sections,
  title = "Step Guidance",
  subtitle = "Optional help for understanding this step.",
  defaultOpen = false,
  gridClassName,
  className,
  panelClassName,
}: WizardGuidancePanelProps) {
  const summary = `Includes ${sections.map((section) => section.title).join(", ")}.`;

  return (
    <ExpandableSummaryPanel
      title={title}
      description={subtitle}
      summary={summary}
      defaultOpen={defaultOpen}
      className={cn("border-primary/15 bg-primary/[0.04]", className)}
      openClassName="border-primary/20 bg-primary/[0.05]"
      closedClassName="border-primary/15 bg-primary/[0.04]"
      contentClassName="space-y-4"
      headerMeta={
        <div className="flex items-center gap-2">
          <Info className="h-4 w-4 text-primary" />
          <span className="text-xs font-semibold uppercase tracking-[0.22em] text-primary/80">Step Guidance</span>
        </div>
      }
    >
      <div className={cn("grid gap-3 xl:grid-cols-2", gridClassName)}>
          {sections.map((section) => (
            <div
              key={section.title}
              className={cn("rounded-xl border border-border/70 bg-background/80 p-4 shadow-sm", panelClassName)}
            >
              <p className="text-[11px] font-semibold uppercase tracking-[0.2em] text-muted-foreground">
                {section.title}
              </p>
              <p className="mt-2 text-sm leading-6 text-foreground/90">{section.content}</p>
            </div>
          ))}
      </div>
    </ExpandableSummaryPanel>
  );
}
