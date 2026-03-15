import type { ReactNode } from "react";
import { AlertTriangle, Loader2 } from "lucide-react";
import { ErrorAlert } from "@/components/ErrorAlert";
import { OperationRiskLabel } from "@/components/OperationRiskLabel";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

interface ExecutionStepProps {
  title: string;
  description: string;
  riskLabel: string;
  strongRisk?: boolean;
  loading: boolean;
  error?: string | null;
  onRun: () => void;
  onContinue: () => void;
  continueDisabled: boolean;
  guidance?: ReactNode;
  children?: ReactNode;
  result?: ReactNode;
  footer?: ReactNode;
}

export function ExecutionStep({
  title,
  description,
  riskLabel,
  strongRisk = false,
  loading,
  error,
  onRun,
  onContinue,
  continueDisabled,
  guidance,
  children,
  result,
  footer,
}: ExecutionStepProps) {
  return (
    <Card className="rounded-2xl">
      <CardHeader className="space-y-4">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="space-y-2">
            <CardDescription>Execution Step</CardDescription>
            <CardTitle className="text-2xl">{title}</CardTitle>
            <p className="max-w-3xl text-sm text-muted-foreground">{description}</p>
          </div>
          <OperationRiskLabel mutating label={riskLabel} className={strongRisk ? "" : "bg-caution/10 text-caution border-caution/30"} />
        </div>
      </CardHeader>
      <CardContent className="space-y-5">
        {strongRisk && (
          <div className="rounded-xl border border-destructive/30 bg-destructive/5 p-4 text-sm text-muted-foreground">
            <div className="flex items-start gap-2">
              <AlertTriangle className="mt-0.5 h-4 w-4 text-destructive" />
              <p>This step mutates durable system state. Review inputs carefully before running it.</p>
            </div>
          </div>
        )}

        {children}
        {guidance}

        <div className="flex flex-wrap items-center gap-3">
          <Button onClick={onRun} disabled={loading}>
            {loading && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
            Run Step
          </Button>
          <Button variant="outline" onClick={onContinue} disabled={continueDisabled || loading}>
            Continue
          </Button>
        </div>

        {error && <ErrorAlert message={error} />}
        {result}
        {footer}
      </CardContent>
    </Card>
  );
}
