import { OperationCard } from "@/components/ui/OperationCard";
import { Upload, Map, CheckSquare, RefreshCw, Tag, PlayCircle } from "lucide-react";
import { runIngest, runPlan, runApply, runCanonicalRecompute, runTagEnrichment, runOperatorComposite } from "@/lib/api/endpoints";

const operations = [
  {
    id: "ingest",
    title: "Ingest",
    description: "Scan filesystem for new/changed media files and register them in the ledger.",
    mutating: true,
    icon: <Upload className="h-5 w-5" />,
    inputs: [{ key: "root_path", label: "Root Path", placeholder: "/media/incoming" }],
    execute: (p: Record<string, string>) => runIngest({ root_path: p.root_path || undefined }),
  },
  {
    id: "plan",
    title: "Plan",
    description: "Generate a deduplication and canonicalization plan based on current ledger state. Does not modify data.",
    mutating: false,
    icon: <Map className="h-5 w-5" />,
    execute: () => runPlan(),
  },
  {
    id: "apply",
    title: "Apply",
    description: "Apply the most recent plan, executing file moves and ledger updates. Irreversible.",
    mutating: true,
    icon: <CheckSquare className="h-5 w-5" />,
    execute: () => runApply(),
  },
  {
    id: "canonical-recompute",
    title: "Canonical Recompute",
    description: "Recalculate canonical file selections for all duplicate groups based on current policy.",
    mutating: true,
    icon: <RefreshCw className="h-5 w-5" />,
    execute: () => runCanonicalRecompute(),
  },
  {
    id: "tag-enrichment",
    title: "Tag Enrichment",
    description: "Run AI-based tag enrichment on untagged canonical files.",
    mutating: true,
    icon: <Tag className="h-5 w-5" />,
    execute: () => runTagEnrichment(),
  },
  {
    id: "composite-run",
    title: "Composite Run",
    description: "Full ingest → plan → apply pipeline in a single operation. Legacy interface.",
    mutating: true,
    icon: <PlayCircle className="h-5 w-5" />,
    inputs: [{ key: "root_path", label: "Root Path", placeholder: "/media/incoming" }],
    execute: (p: Record<string, string>) => runOperatorComposite({ root_path: p.root_path || undefined }),
  },
];

export default function Operations() {
  return (
    <div className="p-6 space-y-6 max-w-5xl">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Operations</h1>
        <p className="text-sm text-muted-foreground mt-1">Execute pipeline operations with explicit state control</p>
      </div>
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {operations.map((op) => (
          <OperationCard key={op.id} {...op} />
        ))}
      </div>
    </div>
  );
}
