import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { OperationRiskLabel } from "@/components/OperationRiskLabel";
import { JsonViewer } from "@/components/JsonViewer";
import { StatusBadge } from "@/components/StatusBadge";
import { ErrorAlert } from "@/components/ErrorAlert";
import { ConfirmDialog } from "@/components/ConfirmDialog";
import { Button } from "@/components/ui/button";
import { Loader2, Upload, Map, CheckSquare, RefreshCw, Tag, PlayCircle } from "lucide-react";
import {
  invalidateReadsAfterOperation,
  runIngest,
  runPlan,
  runApply,
  runCanonicalRecompute,
  runTagEnrichment,
  runOperatorRun,
} from "@/lib/api/endpoints";
import type { OperationResult } from "@/types/api";

interface OpConfig {
  id: string;
  title: string;
  description: string;
  mutating: boolean;
  icon: React.ReactNode;
  invalidationTarget: "ingest" | "plan" | "apply" | "canonicalRecompute" | "tagEnrichment" | "operatorRun";
  inputs?: { key: string; label: string; placeholder: string; type?: string }[];
  execute: (params: Record<string, string>) => Promise<{ data: OperationResult }>;
}

const operations: OpConfig[] = [
  {
    id: "ingest", title: "Ingest", description: "Scan filesystem for new/changed media files and register them in the ledger.", mutating: true,
    icon: <Upload className="h-5 w-5" />,
    invalidationTarget: "ingest",
    inputs: [{ key: "folder_path", label: "Folder Path", placeholder: "/media/incoming" }],
    execute: (p) => runIngest({ folder_path: p.folder_path || undefined, dry_run: true }),
  },
  {
    id: "plan", title: "Plan", description: "Generate a deduplication and canonicalization plan based on current ledger state. Does not modify data.",
    mutating: true, icon: <Map className="h-5 w-5" />,
    invalidationTarget: "plan",
    inputs: [{ key: "folder_path", label: "Folder Path", placeholder: "/media/incoming" }],
    execute: (p) => runPlan({ folder_path: p.folder_path || undefined, strict_metadata: false }),
  },
  {
    id: "apply", title: "Apply", description: "Apply the most recent plan, executing file moves and ledger updates. Irreversible.",
    mutating: true, icon: <CheckSquare className="h-5 w-5" />,
    invalidationTarget: "apply",
    inputs: [{ key: "run_id", label: "Run ID", placeholder: "00000000-0000-0000-0000-000000000000" }],
    execute: (p) => runApply({ run_id: p.run_id || "", collision_mode: "rename" }),
  },
  {
    id: "canonical-recompute", title: "Canonical Recompute", description: "Recalculate canonical file selections for all duplicate groups based on current policy.",
    mutating: true, icon: <RefreshCw className="h-5 w-5" />,
    invalidationTarget: "canonicalRecompute",
    inputs: [{ key: "policy_name", label: "Policy", placeholder: "FIRST_SEEN" }],
    execute: (p) => runCanonicalRecompute({ policy_name: p.policy_name || "FIRST_SEEN", dry_run: true }),
  },
  {
    id: "tag-enrichment", title: "Tag Enrichment", description: "Run AI-based tag enrichment on untagged canonical files.",
    mutating: true,
    icon: <Tag className="h-5 w-5" />,
    invalidationTarget: "tagEnrichment",
    execute: () => runTagEnrichment({ all: true, batch_size: 100, source: "system" }),
  },
  {
    id: "composite-run", title: "Composite Run", description: "Full ingest → plan → apply pipeline in a single operation. Legacy interface.",
    mutating: true, icon: <PlayCircle className="h-5 w-5" />,
    invalidationTarget: "operatorRun",
    inputs: [{ key: "folder_path", label: "Folder Path", placeholder: "/media/incoming" }],
    execute: (p) => runOperatorRun({ folder_path: p.folder_path || undefined, policy_name: "FIRST_SEEN", dry_run: true }),
  },
];

function OperationCard({ op }: { op: OpConfig }) {
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
      const res = await op.execute(inputs);
      setResult(res.data);
      await invalidateReadsAfterOperation(queryClient, op.invalidationTarget);
    } catch (err: any) {
      setError(err.message);
    } finally {
      setLoading(false);
      setConfirmOpen(false);
    }
  };

  return (
    <div className="rounded-lg border bg-card p-5 space-y-4">
      <div className="flex items-start justify-between">
        <div className="flex items-center gap-3">
          <div className="p-2 rounded-md bg-muted">{op.icon}</div>
          <div>
            <h3 className="font-semibold text-sm">{op.title}</h3>
            <p className="text-xs text-muted-foreground mt-0.5">{op.description}</p>
          </div>
        </div>
        <OperationRiskLabel mutating={op.mutating} />
      </div>

      {op.inputs && (
        <div className="space-y-2">
          {op.inputs.map(inp => (
            <div key={inp.key}>
              <label className="text-xs font-medium text-muted-foreground">{inp.label}</label>
              <input
                value={inputs[inp.key] || ""}
                onChange={e => setInputs(prev => ({ ...prev, [inp.key]: e.target.value }))}
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
          variant={op.mutating ? "destructive" : "default"}
          onClick={() => op.mutating ? setConfirmOpen(true) : execute()}
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
            <StatusBadge label={result.success ? "Success" : "Failed"} severity={result.success ? "success" : "destructive"} dot />
            <span className="text-xs font-mono text-muted-foreground">{result.duration_ms}ms</span>
          </div>
          <p className="text-sm">{result.summary}</p>
          <JsonViewer data={result.details} title="Result Details" />
        </div>
      )}

      <ConfirmDialog
        open={confirmOpen}
        onOpenChange={setConfirmOpen}
        title={`Execute ${op.title}?`}
        description={`This operation will modify system state. ${op.description}`}
        destructive
        onConfirm={execute}
        loading={loading}
      />
    </div>
  );
}

export default function OperationsPage() {
  return (
    <div className="p-6 space-y-6 max-w-5xl">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Operations</h1>
        <p className="text-sm text-muted-foreground mt-1">Execute pipeline operations with explicit state control</p>
      </div>
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {operations.map(op => <OperationCard key={op.id} op={op} />)}
      </div>
    </div>
  );
}
