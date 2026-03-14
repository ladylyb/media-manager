import { useState } from "react";
import { OperationRiskLabel } from "@/components/OperationRiskLabel";
import { JsonViewer } from "@/components/JsonViewer";
import { StatusBadge } from "@/components/StatusBadge";
import { ErrorAlert } from "@/components/ErrorAlert";
import { ConfirmDialog } from "@/components/ConfirmDialog";
import { Button } from "@/components/ui/button";
import { Loader2 } from "lucide-react";
import type { OperationResult } from "@/types/api";

interface OperationInput {
  key: string;
  label: string;
  placeholder: string;
  type?: string;
}

interface OperationCardProps {
  id: string;
  title: string;
  description: string;
  mutating: boolean;
  icon: React.ReactNode;
  inputs?: OperationInput[];
  execute: (params: Record<string, string>) => Promise<OperationResult>;
}

export function OperationCard({ title, description, mutating, icon, inputs, execute }: OperationCardProps) {
  const [inputValues, setInputValues] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<OperationResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [confirmOpen, setConfirmOpen] = useState(false);

  const handleExecute = async () => {
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const res = await execute(inputValues);
      setResult(res);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Unknown error");
    } finally {
      setLoading(false);
      setConfirmOpen(false);
    }
  };

  return (
    <div className="rounded-lg border bg-card p-5 space-y-4">
      <div className="flex items-start justify-between">
        <div className="flex items-center gap-3">
          <div className="p-2 rounded-md bg-muted">{icon}</div>
          <div>
            <h3 className="font-semibold text-sm">{title}</h3>
            <p className="text-xs text-muted-foreground mt-0.5">{description}</p>
          </div>
        </div>
        <OperationRiskLabel mutating={mutating} />
      </div>

      {inputs && (
        <div className="space-y-2">
          {inputs.map((inp) => (
            <div key={inp.key}>
              <label className="text-xs font-medium text-muted-foreground">{inp.label}</label>
              <input
                value={inputValues[inp.key] || ""}
                onChange={(e) => setInputValues((prev) => ({ ...prev, [inp.key]: e.target.value }))}
                placeholder={inp.placeholder}
                className="mt-1 w-full rounded-md border bg-background px-3 py-2 text-sm font-mono"
              />
            </div>
          ))}
        </div>
      )}

      <div className="flex items-center gap-2">
        <Button
          size="sm"
          variant={mutating ? "destructive" : "default"}
          onClick={() => (mutating ? setConfirmOpen(true) : handleExecute())}
          disabled={loading}
        >
          {loading && <Loader2 className="mr-2 h-3.5 w-3.5 animate-spin" />}
          Execute
        </Button>
      </div>

      {error && <ErrorAlert message={error} severity="error" onDismiss={() => setError(null)} />}

      {result && (
        <div className="space-y-2 pt-1">
          <div className="flex items-center gap-2">
            <StatusBadge
              label={result.success ? "Success" : "Failed"}
              severity={result.success ? "success" : "destructive"}
              dot
            />
            <span className="text-xs font-mono text-muted-foreground">{result.duration_ms}ms</span>
          </div>
          <p className="text-sm">{result.summary}</p>
          <JsonViewer data={result.details} title="Result Details" />
        </div>
      )}

      <ConfirmDialog
        open={confirmOpen}
        onOpenChange={setConfirmOpen}
        title={`Execute ${title}?`}
        description={`This operation will modify system state. ${description}`}
        destructive
        onConfirm={handleExecute}
        loading={loading}
      />
    </div>
  );
}
