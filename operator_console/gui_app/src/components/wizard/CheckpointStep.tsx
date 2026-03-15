import type { ReactNode } from "react";
import { ArrowRight, RotateCcw, XCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

interface CheckpointStepProps {
  title: string;
  description: string;
  onContinue: () => void;
  onRerun?: (() => void) | null;
  onAbort?: (() => void) | null;
  continueLabel?: string;
  guidance?: ReactNode;
  showRerun?: boolean;
  showAbort?: boolean;
  children: ReactNode;
}

export function CheckpointStep({
  title,
  description,
  onContinue,
  onRerun,
  onAbort,
  continueLabel = "Continue",
  guidance,
  showRerun = true,
  showAbort = true,
  children,
}: CheckpointStepProps) {
  return (
    <Card className="rounded-2xl">
      <CardHeader>
        <CardDescription>Review Checkpoint</CardDescription>
        <CardTitle className="text-2xl">{title}</CardTitle>
        <p className="max-w-3xl text-sm text-muted-foreground">{description}</p>
      </CardHeader>
      <CardContent className="space-y-5">
        {guidance}
        {children}
        <div className="flex flex-wrap items-center gap-3">
          <Button onClick={onContinue}>
            <ArrowRight className="mr-2 h-4 w-4" />
            {continueLabel}
          </Button>
          {showRerun && onRerun && (
            <Button variant="outline" onClick={onRerun}>
              <RotateCcw className="mr-2 h-4 w-4" />
              Re-run Previous Step
            </Button>
          )}
          {showAbort && onAbort && (
            <Button variant="ghost" onClick={onAbort}>
              <XCircle className="mr-2 h-4 w-4" />
              Abort Wizard
            </Button>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
