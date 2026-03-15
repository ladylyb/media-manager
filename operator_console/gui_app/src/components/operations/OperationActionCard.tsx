import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Loader2 } from "lucide-react";

import { ConfirmDialog } from "@/components/ConfirmDialog";
import { ErrorAlert } from "@/components/ErrorAlert";
import { JsonViewer } from "@/components/JsonViewer";
import { OperationRiskLabel } from "@/components/OperationRiskLabel";
import { StatusBadge } from "@/components/StatusBadge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { invalidateReadsAfterOperation } from "@/lib/api/endpoints";
import type { OperationResult } from "@/types/api";

export interface OperationInputConfig {
  key: string;
  label: string;
  placeholder: string;
  type?: string;
}

export interface OperationActionConfig {
  id: string;
  title: string;
  description: string;
  mutating: boolean;
  icon: React.ReactNode;
  invalidationTarget:
    | "ingest"
    | "plan"
    | "apply"
    | "canonicalRecompute"
    | "tagEnrichment"
    | "operatorRun";
  section: "guided" | "high-impact";
  badgeLabel: string;
  inputs?: OperationInputConfig[];
  execute: (params: Record<string, string>) => Promise<{ data: OperationResult }>;
}

export function OperationActionCard({ operation }: { operation: OperationActionConfig }) {
  const queryClient = useQueryClient();
  const [inputs, setInputs] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<OperationResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [confirmOpen, setConfirmOpen] = useState(false);

  const execute = async () => {
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const response = await operation.execute(inputs);
      setResult(response.data);
      await invalidateReadsAfterOperation(queryClient, operation.invalidationTarget);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Operation failed");
    } finally {
      setLoading(false);
      setConfirmOpen(false);
    }
  };

  return (
    <Card className="h-full border-border/80 transition-colors hover:border-primary/30">
      <CardHeader className="space-y-4 pb-4">
        <div className="flex items-start justify-between gap-3">
          <div className="flex items-start gap-3">
            <div className="rounded-md bg-muted p-2 text-foreground">{operation.icon}</div>
            <div className="space-y-1">
              <CardTitle className="text-base">{operation.title}</CardTitle>
              <CardDescription className="text-sm">{operation.description}</CardDescription>
            </div>
          </div>
          <OperationRiskLabel mutating={operation.mutating} />
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <StatusBadge
            label={operation.badgeLabel}
            severity={operation.section === "guided" ? "info" : "caution"}
          />
          {operation.inputs?.length ? (
            <StatusBadge label={`${operation.inputs.length} input${operation.inputs.length > 1 ? "s" : ""}`} />
          ) : (
            <StatusBadge label="No extra input" />
          )}
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        {operation.inputs?.length ? (
          <div className="space-y-3">
            {operation.inputs.map((input) => (
              <div key={input.key} className="space-y-1.5">
                <label className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                  {input.label}
                </label>
                <Input
                  value={inputs[input.key] || ""}
                  onChange={(event) =>
                    setInputs((prev) => ({ ...prev, [input.key]: event.target.value }))
                  }
                  placeholder={input.placeholder}
                  type={input.type}
                  className="font-mono"
                />
              </div>
            ))}
          </div>
        ) : (
          <div className="rounded-lg border border-dashed bg-muted/20 p-3 text-sm text-muted-foreground">
            This action runs with the current default request payload and does not need additional input.
          </div>
        )}

        <div className="flex items-center justify-between gap-3">
          <p className="text-xs text-muted-foreground">
            {operation.mutating
              ? "Execution opens a confirmation dialog before sending the request."
              : "Execution runs immediately and refreshes dependent reads on success."}
          </p>
          <Button
            size="sm"
            variant={operation.mutating ? "destructive" : "default"}
            onClick={() => (operation.mutating ? setConfirmOpen(true) : execute())}
            disabled={loading}
          >
            {loading && <Loader2 className="mr-2 h-3.5 w-3.5 animate-spin" />}
            Execute
          </Button>
        </div>

        {error && <ErrorAlert message={error} severity="error" onDismiss={() => setError(null)} />}

        {result ? (
          <div className="space-y-3 rounded-lg border bg-muted/20 p-4">
            <div className="flex flex-wrap items-center gap-2">
              <StatusBadge
                label={result.success ? "Success" : "Failed"}
                severity={result.success ? "success" : "destructive"}
                dot
              />
              <span className="font-mono text-xs text-muted-foreground">{result.duration_ms}ms</span>
            </div>
            <p className="text-sm">{result.summary}</p>
            <JsonViewer data={result.details} title="Result Details" />
          </div>
        ) : (
          <div className="rounded-lg border border-dashed bg-background/50 p-3 text-sm text-muted-foreground">
            The latest execution result for this action will appear here.
          </div>
        )}
      </CardContent>

      <ConfirmDialog
        open={confirmOpen}
        onOpenChange={setConfirmOpen}
        title={`Execute ${operation.title}?`}
        description={`This operation will modify system state. ${operation.description}`}
        destructive
        onConfirm={execute}
        loading={loading}
      />
    </Card>
  );
}
