import { AlertCircle, ArrowLeft, ArrowRight, CheckCircle2, HelpCircle } from "lucide-react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

type ReviewMark = "looks_right" | "needs_review" | "not_sure";

interface DuplicateReviewActionBarProps {
  activeMark?: ReviewMark;
  hasNext: boolean;
  hasPrev: boolean;
  onMark: (mark: ReviewMark) => void;
  onNext: () => void;
  onPrev: () => void;
  sticky?: boolean;
  showShortcutHint?: boolean;
  showNavigation?: boolean;
  compact?: boolean;
  progressLabel?: string;
}

function ActionChoice({
  active,
  icon: Icon,
  label,
  onClick,
  tone,
}: {
  active: boolean;
  icon: typeof CheckCircle2;
  label: string;
  onClick: () => void;
  tone: "success" | "destructive" | "caution";
}) {
  return (
    <Button
      type="button"
      variant={active ? "default" : "outline"}
      onClick={onClick}
      aria-label={`Mark as ${label.toLowerCase()}`}
      className={cn(
        "justify-start rounded-full px-4",
        active && tone === "success" && "bg-success text-success-foreground hover:bg-success/90",
        active && tone === "destructive" && "bg-destructive text-destructive-foreground hover:bg-destructive/90",
        active && tone === "caution" && "bg-caution text-caution-foreground hover:bg-caution/90",
      )}
    >
      <Icon className="h-4 w-4" />
      {label}
    </Button>
  );
}

export function DuplicateReviewActionBar({
  activeMark,
  hasNext,
  hasPrev,
  onMark,
  onNext,
  onPrev,
  sticky = true,
  showShortcutHint = true,
  showNavigation = true,
  compact = false,
  progressLabel,
}: DuplicateReviewActionBarProps) {
  return (
    <div
      className={cn(
        "rounded-[22px] border border-border/70 bg-card/95 backdrop-blur",
        compact ? "p-3" : "p-4",
        sticky ? "sticky bottom-4 z-10 shadow-lg" : "shadow-sm",
      )}
    >
      <div className="flex flex-col gap-3 xl:flex-row xl:items-center xl:justify-between">
        <div className="flex flex-wrap items-center gap-2">
          {showNavigation ? (
            <>
              <Button type="button" variant="outline" size={compact ? "sm" : "default"} onClick={onPrev} disabled={!hasPrev}>
                <ArrowLeft className="h-4 w-4" />
                Back
              </Button>
              <Button type="button" variant="outline" size={compact ? "sm" : "default"} onClick={onNext} disabled={!hasNext}>
                Next
                <ArrowRight className="h-4 w-4" />
              </Button>
            </>
          ) : null}
          {progressLabel ? <span className="text-xs font-medium text-muted-foreground">{progressLabel}</span> : null}
          {showShortcutHint ? <span className="ml-1 text-xs text-muted-foreground">1 / 2 / 3 to mark</span> : null}
        </div>
        <div className="flex flex-wrap gap-2">
          <ActionChoice
            active={activeMark === "looks_right"}
            icon={CheckCircle2}
            label="Looks right"
            onClick={() => onMark("looks_right")}
            tone="success"
          />
          <ActionChoice
            active={activeMark === "needs_review"}
            icon={AlertCircle}
            label="Needs review"
            onClick={() => onMark("needs_review")}
            tone="destructive"
          />
          <ActionChoice
            active={activeMark === "not_sure"}
            icon={HelpCircle}
            label="Not sure"
            onClick={() => onMark("not_sure")}
            tone="caution"
          />
        </div>
      </div>
    </div>
  );
}
