import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { MetricCard } from "@/components/MetricCard";
import { OperationActionCard, type OperationActionConfig } from "@/components/operations/OperationActionCard";
import { CheckSquare, Map, PlayCircle, RefreshCw, ShieldAlert, Tag, Upload, WandSparkles } from "lucide-react";
import {
  runIngest,
  runPlan,
  runApply,
  runCanonicalRecompute,
  runTagEnrichment,
  runOperatorRun,
} from "@/lib/api/endpoints";

const operations: OperationActionConfig[] = [
  {
    id: "ingest", title: "Ingest", description: "Scan filesystem for new/changed media files and register them in the ledger.", mutating: true,
    icon: <Upload className="h-5 w-5" />,
    invalidationTarget: "ingest",
    section: "guided",
    badgeLabel: "Recommended first step",
    inputs: [{ key: "folder_path", label: "Folder Path", placeholder: "/media/incoming" }],
    execute: (p) => runIngest({ folder_path: p.folder_path || undefined, dry_run: true }),
  },
  {
    id: "plan", title: "Plan", description: "Generate a deduplication and canonicalization plan based on current ledger state. Does not modify data.",
    mutating: true, icon: <Map className="h-5 w-5" />,
    invalidationTarget: "plan",
    section: "guided",
    badgeLabel: "Validation-oriented",
    inputs: [{ key: "folder_path", label: "Folder Path", placeholder: "/media/incoming" }],
    execute: (p) => runPlan({ folder_path: p.folder_path || undefined, strict_metadata: false }),
  },
  {
    id: "apply", title: "Apply", description: "Apply the most recent plan, executing file moves and ledger updates. Irreversible.",
    mutating: true, icon: <CheckSquare className="h-5 w-5" />,
    invalidationTarget: "apply",
    section: "high-impact",
    badgeLabel: "Highest impact",
    inputs: [{ key: "run_id", label: "Run ID", placeholder: "00000000-0000-0000-0000-000000000000" }],
    execute: (p) => runApply({ run_id: p.run_id || "", collision_mode: "rename" }),
  },
  {
    id: "canonical-recompute", title: "Canonical Recompute", description: "Recalculate canonical file selections for all duplicate groups based on current policy.",
    mutating: true, icon: <RefreshCw className="h-5 w-5" />,
    invalidationTarget: "canonicalRecompute",
    section: "guided",
    badgeLabel: "Dry-run by default",
    inputs: [{ key: "policy_name", label: "Policy", placeholder: "FIRST_SEEN" }],
    execute: (p) => runCanonicalRecompute({ policy_name: p.policy_name || "FIRST_SEEN", dry_run: true }),
  },
  {
    id: "tag-enrichment", title: "Tag Enrichment", description: "Run AI-based tag enrichment on untagged canonical files.",
    mutating: true,
    icon: <Tag className="h-5 w-5" />,
    invalidationTarget: "tagEnrichment",
    section: "high-impact",
    badgeLabel: "Background enrichment",
    execute: () => runTagEnrichment({ all: true, batch_size: 100, source: "system" }),
  },
  {
    id: "composite-run", title: "Composite Run", description: "Full ingest → plan → apply pipeline in a single operation. Legacy interface.",
    mutating: true, icon: <PlayCircle className="h-5 w-5" />,
    invalidationTarget: "operatorRun",
    section: "guided",
    badgeLabel: "Compatibility path",
    inputs: [{ key: "folder_path", label: "Folder Path", placeholder: "/media/incoming" }],
    execute: (p) => runOperatorRun({ folder_path: p.folder_path || undefined, policy_name: "FIRST_SEEN", dry_run: true }),
  },
];

const guidedOperations = operations.filter((operation) => operation.section === "guided");
const highImpactOperations = operations.filter((operation) => operation.section === "high-impact");

export default function OperationsPage() {
  return (
    <div className="max-w-6xl space-y-6 p-6">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Operations</h1>
          <p className="mt-1 max-w-3xl text-sm text-muted-foreground">
            Execute pipeline operations with explicit state control. Start with guided dry-run and planning paths, then move to the higher-impact actions only when the result signals look healthy.
          </p>
        </div>
      </div>

      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
        <MetricCard
          title="Available Actions"
          value={operations.length}
          subtitle="Current local operations set"
          icon={<WandSparkles className="h-4 w-4" />}
        />
        <MetricCard
          title="Guided Paths"
          value={guidedOperations.length}
          subtitle="Dry-run or staged workflows"
          icon={<Map className="h-4 w-4" />}
        />
        <MetricCard
          title="High-Impact"
          value={highImpactOperations.length}
          subtitle="Actions to treat with extra care"
          icon={<ShieldAlert className="h-4 w-4" />}
        />
        <MetricCard
          title="Requires Input"
          value={operations.filter((operation) => operation.inputs?.length).length}
          subtitle="Actions with request parameters"
          icon={<Upload className="h-4 w-4" />}
        />
      </div>

      <div className="grid gap-4 xl:grid-cols-[1.15fr_0.85fr]">
        <Card className="border-primary/15 bg-gradient-to-br from-card via-card to-primary/5">
          <CardHeader className="pb-3">
            <CardDescription>Suggested operator flow</CardDescription>
            <CardTitle className="text-xl">Stage changes before applying them</CardTitle>
          </CardHeader>
          <CardContent className="grid gap-3 md:grid-cols-3">
            <div className="rounded-lg border bg-background/70 p-4">
              <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">1. Scan</p>
              <p className="mt-2 text-sm">Use Ingest to validate the current folder path and refresh the visible state.</p>
            </div>
            <div className="rounded-lg border bg-background/70 p-4">
              <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">2. Stage</p>
              <p className="mt-2 text-sm">Use Plan or Canonical Recompute to inspect what the system is about to do before any durable change.</p>
            </div>
            <div className="rounded-lg border bg-background/70 p-4">
              <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">3. Execute</p>
              <p className="mt-2 text-sm">Move to Apply or enrichment only when the upstream checks and page results match your intent.</p>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-3">
            <CardDescription>Risk framing</CardDescription>
            <CardTitle className="text-xl">What stays intentionally unchanged</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3 text-sm text-muted-foreground">
            <p>The local operation list, field names, confirmation flow, and invalidation targets remain canonical in this slice.</p>
            <p>No backend catalog-driven rendering is introduced here, and all operational requests continue to flow through the existing shared API endpoints.</p>
          </CardContent>
        </Card>
      </div>

      <section className="space-y-4">
        <div>
          <h2 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">Guided actions</h2>
          <p className="mt-1 text-sm text-muted-foreground">Best starting points when you want validation, planning, or a staged compatibility flow.</p>
        </div>
        <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
          {guidedOperations.map((operation) => (
            <OperationActionCard key={operation.id} operation={operation} />
          ))}
        </div>
      </section>

      <section className="space-y-4">
        <div>
          <h2 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">High-impact actions</h2>
          <p className="mt-1 text-sm text-muted-foreground">Use these once the guided paths and surrounding review pages indicate you are ready to commit changes.</p>
        </div>
        <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
          {highImpactOperations.map((operation) => (
            <OperationActionCard key={operation.id} operation={operation} />
          ))}
        </div>
      </section>
    </div>
  );
}
