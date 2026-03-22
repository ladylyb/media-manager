import { useState, type ReactNode } from "react";
import { ChevronDown } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { cn } from "@/lib/utils";

interface ExpandableSummaryPanelProps {
  title: string;
  description?: string;
  summary?: ReactNode;
  headerMeta?: ReactNode;
  children: ReactNode;
  defaultOpen?: boolean;
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
  className?: string;
  openClassName?: string;
  closedClassName?: string;
  contentClassName?: string;
}

export function ExpandableSummaryPanel({
  title,
  description,
  summary,
  headerMeta,
  children,
  defaultOpen = false,
  open,
  onOpenChange,
  className,
  openClassName,
  closedClassName,
  contentClassName,
}: ExpandableSummaryPanelProps) {
  const [internalOpen, setInternalOpen] = useState(defaultOpen);
  const controlled = open !== undefined;
  const resolvedOpen = controlled ? open : internalOpen;

  const handleOpenChange = (nextOpen: boolean) => {
    if (!controlled) {
      setInternalOpen(nextOpen);
    }
    onOpenChange?.(nextOpen);
  };

  return (
    <Collapsible open={resolvedOpen} onOpenChange={handleOpenChange}>
      <Card
        data-panel-state={resolvedOpen ? "open" : "closed"}
        className={cn(
          "overflow-hidden rounded-2xl shadow-sm transition-colors duration-200",
          resolvedOpen ? "border-border/80 bg-background" : "border-border/60 bg-muted/[0.06]",
          resolvedOpen && openClassName,
          !resolvedOpen && closedClassName,
          className,
        )}
      >
        <CollapsibleTrigger asChild>
          <button
            type="button"
            className={cn(
              "flex w-full items-start justify-between gap-4 px-5 py-4 text-left transition-colors",
              resolvedOpen ? "hover:bg-muted/20" : "hover:bg-muted/15",
            )}
          >
            <div className="min-w-0 space-y-3">
              {headerMeta ? <div className="flex flex-wrap items-center gap-2">{headerMeta}</div> : null}
              <div>
                <h3 className="text-base font-semibold tracking-tight text-foreground">{title}</h3>
                {description ? (
                  <p className="mt-2 max-w-4xl text-sm leading-6 text-muted-foreground">{description}</p>
                ) : null}
              </div>
              {summary ? <div className="text-sm text-foreground/90">{summary}</div> : null}
            </div>
            <div className="flex shrink-0 items-center gap-2 text-sm text-muted-foreground">
              <span>{resolvedOpen ? "Collapse" : "Expand"}</span>
              <ChevronDown className={cn("h-4 w-4 transition-transform", resolvedOpen && "rotate-180")} />
            </div>
          </button>
        </CollapsibleTrigger>
        <CollapsibleContent>
          <CardContent className={cn("border-t border-border/50 px-5 py-5", contentClassName)}>
            {children}
          </CardContent>
        </CollapsibleContent>
      </Card>
    </Collapsible>
  );
}
