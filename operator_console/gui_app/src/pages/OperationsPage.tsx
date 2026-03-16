import { useEffect, useMemo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate } from "react-router-dom";
import {
  ArrowRight,
  ChevronDown,
  FolderSearch,
  GitBranchPlus,
  History,
  Loader2,
  RefreshCw,
  Route,
  Sparkles,
  Tag,
} from "lucide-react";

import { ConfirmDialog } from "@/components/ConfirmDialog";
import { DirectoryPickerDialog } from "@/components/wizard/DirectoryPickerDialog";
import { WizardGuidancePanel } from "@/components/wizard/WizardGuidancePanel";
import { ErrorAlert } from "@/components/ErrorAlert";
import { JsonViewer } from "@/components/JsonViewer";
import { StatusBadge } from "@/components/StatusBadge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  getDirectoryPickerCapability,
  getRuns,
  invalidateReadsAfterOperation,
  runApply,
  runCanonicalRecompute,
  runIngest,
  runPlan,
  runTagEnrichment,
} from "@/lib/api/endpoints";
import { queryKeys } from "@/lib/api/queryKeys";
import { queryOptions } from "@/lib/api/queryOptions";
import { executionStepGuidance } from "@/lib/workflow/executionStepGuidance";
import { cn } from "@/lib/utils";
import type { OperationResult, PaginatedResponse, Run } from "@/types";

type ExecuteState = {
  loading: boolean;
  error: string | null;
  result: OperationResult | null;
};

type ConfirmingAction = "recheck-ingest" | "recheck-plan" | "apply" | "canonical" | "tag";
type PanelId = "start" | "continue" | "recheck" | "canonical" | "tag";

const INITIAL_EXECUTE_STATE: ExecuteState = {
  loading: false,
  error: null,
  result: null,
};

function parseError(err: unknown): string {
  if (err instanceof Error) return err.message;
  return String(err);
}

function ResultPanel({ state, idleCopy }: { state: ExecuteState; idleCopy: string }) {
  if (state.error) {
    return <ErrorAlert message={state.error} severity="error" />;
  }

  if (!state.result) {
    return (
      <div className="rounded-2xl border border-dashed bg-background/70 p-4 text-sm text-muted-foreground">
        {idleCopy}
      </div>
    );
  }

  return (
    <div className="space-y-3 rounded-2xl border bg-muted/20 p-4">
      <div className="flex flex-wrap items-center gap-2">
        <StatusBadge
          label={state.result.success ? "Success" : "Needs review"}
          severity={state.result.success ? "success" : "destructive"}
          dot
        />
        <span className="font-mono text-xs text-muted-foreground">{state.result.duration_ms}ms</span>
      </div>
      <p className="text-sm text-foreground">{state.result.summary}</p>
      <JsonViewer data={state.result.details} title="Result Details" />
    </div>
  );
}

function ImpactBadge({
  label,
  tone,
}: {
  label: string;
  tone: "state" | "checks" | "follow-up";
}) {
  const toneClasses =
    tone === "state"
      ? "border-emerald-300/70 bg-emerald-50 text-emerald-800"
      : tone === "checks"
        ? "border-slate-300/80 bg-slate-100 text-slate-700"
        : "border-sky-300/70 bg-sky-50 text-sky-800";

  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full border px-3 py-1 text-xs font-semibold tracking-[0.08em]",
        toneClasses,
      )}
    >
      {label}
    </span>
  );
}

function ActionPanel({
  panelId,
  openPanel,
  onToggle,
  title,
  description,
  summary,
  badge,
  impactLabel,
  impactTone,
  children,
}: {
  panelId: PanelId;
  openPanel: PanelId | null;
  onToggle: (panelId: PanelId) => void;
  title: string;
  description: string;
  summary: string;
  badge: string;
  impactLabel: string;
  impactTone: "state" | "checks" | "follow-up";
  children: React.ReactNode;
}) {
  const open = openPanel === panelId;

  return (
    <Collapsible open={open} onOpenChange={() => onToggle(panelId)}>
      <Card
        data-panel-state={open ? "open" : "closed"}
        className={cn(
          "overflow-hidden rounded-[28px] shadow-sm transition-colors duration-200",
          open
            ? "border-emerald-200 bg-[linear-gradient(180deg,#f4fbf4_0%,#e8f4ea_100%)]"
            : "border-[#cfcfcf] bg-[linear-gradient(180deg,#f3f3f3_0%,#e3e3e3_100%)]",
        )}
      >
        <CollapsibleTrigger asChild>
          <button
            type="button"
            className={cn(
              "flex w-full items-start justify-between gap-4 px-6 py-5 text-left transition-colors",
              open ? "hover:bg-emerald-100/35" : "hover:bg-black/5",
            )}
          >
            <div className="space-y-3">
              <div className="flex flex-wrap items-center gap-2">
                <StatusBadge label={badge} severity="info" />
                <ImpactBadge label={impactLabel} tone={impactTone} />
              </div>
              <div>
                <h2 className="text-xl font-semibold tracking-tight text-foreground">{title}</h2>
                <p className="mt-2 max-w-4xl text-sm leading-6 text-muted-foreground">{description}</p>
              </div>
              <p className="text-sm text-foreground/90">{summary}</p>
            </div>
            <div className="flex shrink-0 items-center gap-2 text-sm text-muted-foreground">
              <span>{open ? "Collapse" : "Expand"}</span>
              <ChevronDown className={cn("h-4 w-4 transition-transform", open && "rotate-180")} />
            </div>
          </button>
        </CollapsibleTrigger>
        <CollapsibleContent>
          <CardContent className="space-y-5 border-t border-emerald-100/70 bg-background/55 px-6 py-6">
            {children}
          </CardContent>
        </CollapsibleContent>
      </Card>
    </Collapsible>
  );
}

export default function OperationsPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [openPanel, setOpenPanel] = useState<PanelId | null>("start");
  const [pickerTarget, setPickerTarget] = useState<"start" | "recheck" | null>(null);
  const [confirmingAction, setConfirmingAction] = useState<ConfirmingAction | null>(null);
  const [startFolderPath, setStartFolderPath] = useState("");
  const [recheckFolderPath, setRecheckFolderPath] = useState("");
  const [selectedPlanRunId, setSelectedPlanRunId] = useState("");
  const [manualRunId, setManualRunId] = useState("");
  const [showManualRunId, setShowManualRunId] = useState(false);
  const [recheckState, setRecheckState] = useState<{ ingest: ExecuteState; plan: ExecuteState }>({
    ingest: INITIAL_EXECUTE_STATE,
    plan: INITIAL_EXECUTE_STATE,
  });
  const [applyState, setApplyState] = useState<ExecuteState>(INITIAL_EXECUTE_STATE);
  const [canonicalState, setCanonicalState] = useState<ExecuteState>(INITIAL_EXECUTE_STATE);
  const [tagState, setTagState] = useState<ExecuteState>(INITIAL_EXECUTE_STATE);

  const directoryPickerCapabilityQuery = useQuery({
    queryKey: queryKeys.directoryPickerCapability,
    queryFn: async () => (await getDirectoryPickerCapability()).data,
    staleTime: queryOptions.directoryPicker.staleTime,
  });

  const runsQuery = useQuery({
    queryKey: queryKeys.runs(100),
    queryFn: async () => (await getRuns({ limit: 100 })).data,
    staleTime: queryOptions.runs.staleTime,
  });

  const runs = ((runsQuery.data as PaginatedResponse<Run> | undefined)?.items ?? []).filter(
    (run) => run.status === "COMPLETED",
  );

  const recentPlanRuns = useMemo(
    () => runs.filter((run) => run.operation_type === "PLAN").slice(0, 12),
    [runs],
  );

  useEffect(() => {
    if (showManualRunId || selectedPlanRunId || recentPlanRuns.length === 0) return;
    setSelectedPlanRunId(recentPlanRuns[0].operation_run_id);
  }, [recentPlanRuns, selectedPlanRunId, showManualRunId]);

  const activeApplyRunId = showManualRunId ? manualRunId.trim() : selectedPlanRunId.trim();
  const selectedPlan = recentPlanRuns.find((run) => run.operation_run_id === selectedPlanRunId) ?? null;

  const startSections = executionStepGuidance.ingest.sections.map((section) =>
    section.title === "Before you run"
      ? {
          ...section,
          content:
            "Choose the folder you want the system to inspect, then move into Organize Media with that same starting point already in place. The folder picker here exists so you do not have to retype paths before starting the guided flow.",
        }
      : section,
  );
  const applySections = executionStepGuidance.apply.sections.map((section) =>
    section.title === "Before you run"
      ? {
          ...section,
          content:
            "Confirm you have selected the saved plan you actually want to execute. On this page you can choose a recent completed plan or fall back to a manual run ID when you already know the exact saved run you need.",
        }
      : section,
  );
  const canonicalSections = executionStepGuidance.canonical.sections.map((section) =>
    section.title === "Before you run"
      ? {
          ...section,
          content:
            "Run this after the main organize work already looks settled. In Library Actions, this panel gives you room to preview the follow-up decision picture before moving on.",
        }
      : section,
  );
  const tagSections = executionStepGuidance.tag.sections.map((section) =>
    section.title === "Before you run"
      ? {
          ...section,
          content:
            "Use this after the main organize work already looks right. If you would rather inspect gallery or duplicate outcomes first, you can leave enrichment for later without undoing earlier steps.",
        }
      : section,
  );

  const togglePanel = (panelId: PanelId) => {
    setOpenPanel((current) => (current === panelId ? null : panelId));
  };

  const executeRecheck = async (mode: "ingest" | "plan") => {
    const folderPath = recheckFolderPath.trim();
    if (!folderPath) {
      setRecheckState((current) => ({
        ...current,
        [mode]: {
          ...INITIAL_EXECUTE_STATE,
          error: "Choose a folder before running this step.",
        },
      }));
      return;
    }

    setRecheckState((current) => ({
      ...current,
      [mode]: { loading: true, error: null, result: null },
    }));

    try {
      const response =
        mode === "ingest"
          ? await runIngest({ folder_path: folderPath, dry_run: true })
          : await runPlan({ folder_path: folderPath, strict_metadata: false });
      setRecheckState((current) => ({
        ...current,
        [mode]: { loading: false, error: null, result: response.data },
      }));
      await invalidateReadsAfterOperation(queryClient, mode === "ingest" ? "ingest" : "plan");
    } catch (err) {
      setRecheckState((current) => ({
        ...current,
        [mode]: { loading: false, error: parseError(err), result: null },
      }));
    } finally {
      setConfirmingAction(null);
    }
  };

  const executeApply = async () => {
    if (!activeApplyRunId) {
      setApplyState({
        loading: false,
        error: "Choose a saved plan or enter a run ID before applying saved work.",
        result: null,
      });
      setConfirmingAction(null);
      return;
    }

    setApplyState({ loading: true, error: null, result: null });
    try {
      const response = await runApply({ run_id: activeApplyRunId, collision_mode: "rename" });
      setApplyState({ loading: false, error: null, result: response.data });
      await invalidateReadsAfterOperation(queryClient, "apply");
    } catch (err) {
      setApplyState({ loading: false, error: parseError(err), result: null });
    } finally {
      setConfirmingAction(null);
    }
  };

  const executeCanonicalRefresh = async () => {
    setCanonicalState({ loading: true, error: null, result: null });
    try {
      const response = await runCanonicalRecompute({
        policy_name: "FIRST_SEEN",
        dry_run: true,
        preferred_roots: [],
      });
      setCanonicalState({ loading: false, error: null, result: response.data });
      await invalidateReadsAfterOperation(queryClient, "canonicalRecompute");
    } catch (err) {
      setCanonicalState({ loading: false, error: parseError(err), result: null });
    } finally {
      setConfirmingAction(null);
    }
  };

  const executeTagEnrichment = async () => {
    setTagState({ loading: true, error: null, result: null });
    try {
      const response = await runTagEnrichment({ all: true, batch_size: 100, source: "system" });
      setTagState({ loading: false, error: null, result: response.data });
      await invalidateReadsAfterOperation(queryClient, "tagEnrichment");
    } catch (err) {
      setTagState({ loading: false, error: parseError(err), result: null });
    } finally {
      setConfirmingAction(null);
    }
  };

  return (
    <div className="max-w-6xl space-y-6 p-6">
      <section className="overflow-hidden rounded-[32px] border border-border/70 bg-[radial-gradient(circle_at_top_left,hsl(var(--primary)/0.18),transparent_35%),linear-gradient(135deg,hsl(var(--card))_0%,hsl(var(--secondary)/0.22)_100%)] p-6 lg:p-8">
        <div className="space-y-4">
          <div className="inline-flex items-center gap-2 rounded-full border border-primary/20 bg-background/70 px-3 py-1 text-xs font-semibold uppercase tracking-[0.24em] text-muted-foreground">
            <Sparkles className="h-3.5 w-3.5" />
            Library Actions
          </div>
          <div className="space-y-3">
            <h1 className="max-w-3xl text-3xl font-semibold tracking-tight text-foreground">
              Continue the pipeline with more room to think and review.
            </h1>
            <p className="max-w-3xl text-sm leading-6 text-muted-foreground">
              Each action below opens into its own full-width workspace so you can review guidance,
              inputs, and results without squeezing the important parts into side-by-side cards.
            </p>
          </div>
          <div className="flex flex-wrap gap-3">
            <Button asChild size="sm">
              <Link to="/pipeline-wizard">
                Open Organize Media
                <ArrowRight className="ml-2 h-4 w-4" />
              </Link>
            </Button>
            <Button asChild variant="outline" size="sm">
              <Link to="/runs">Review Progress</Link>
            </Button>
          </div>
        </div>
      </section>

      <div className="space-y-4">
        <ActionPanel
          panelId="start"
          openPanel={openPanel}
          onToggle={togglePanel}
          title="Start from Folder"
          description="Choose a folder once, then move into Organize Media with that same starting point already in place."
          summary="Best when you are beginning a new organizing pass and want the wizard to carry the sequence."
          badge="Recommended first step"
          impactLabel="Checks before changing anything"
          impactTone="checks"
        >
          <WizardGuidancePanel
            sections={startSections}
            title="Step Guidance"
            subtitle="Optional help for understanding this step."
            showLabel="Show step guidance"
            hideLabel="Hide step guidance"
            defaultOpen={false}
            gridClassName="grid-cols-1"
            className="border-emerald-100 bg-emerald-50/55"
            panelClassName="bg-background/90 shadow-none"
          />
          <div className="rounded-2xl border bg-background/75 p-4">
            <p className="text-xs font-semibold uppercase tracking-[0.2em] text-muted-foreground">
              Selected Folder
            </p>
            <p className="mt-3 break-all rounded-xl border border-dashed bg-muted/25 px-3 py-3 font-mono text-sm">
              {startFolderPath || "Choose a server folder to begin."}
            </p>
            <div className="mt-4 flex flex-wrap gap-3">
              <Button
                type="button"
                variant="outline"
                onClick={() => setPickerTarget("start")}
                disabled={!directoryPickerCapabilityQuery.data?.enabled}
              >
                <FolderSearch className="mr-2 h-4 w-4" />
                Browse Folders
              </Button>
              <Button
                type="button"
                onClick={() =>
                  navigate(
                    startFolderPath
                      ? `/pipeline-wizard?folder_path=${encodeURIComponent(startFolderPath)}`
                      : "/pipeline-wizard",
                  )
                }
              >
                Open Organize Media
                <ArrowRight className="ml-2 h-4 w-4" />
              </Button>
            </div>
          </div>
          {directoryPickerCapabilityQuery.error ? (
            <ErrorAlert message={parseError(directoryPickerCapabilityQuery.error)} />
          ) : null}
        </ActionPanel>

        <ActionPanel
          panelId="continue"
          openPanel={openPanel}
          onToggle={togglePanel}
          title="Continue a Saved Plan"
          description="Pick up planning work that already exists, then apply it when you are ready to make the saved changes real."
          summary="Best when planning is already complete and you want a calmer apply surface with room for run details and results."
          badge="Saved-run aware"
          impactLabel="Updates library state"
          impactTone="state"
        >
          <WizardGuidancePanel
            sections={applySections}
            title="Step Guidance"
            subtitle="Optional help for understanding this step."
            showLabel="Show step guidance"
            hideLabel="Hide step guidance"
            defaultOpen={false}
            gridClassName="grid-cols-1"
            className="border-emerald-100 bg-emerald-50/55"
            panelClassName="bg-background/90 shadow-none"
          />
          <div className="space-y-4 rounded-2xl border bg-background/75 p-4">
            <div className="space-y-2">
              <label className="text-xs font-semibold uppercase tracking-[0.2em] text-muted-foreground">
                Recent Saved Plans
              </label>
              <Select
                value={selectedPlanRunId}
                onValueChange={(value) => {
                  setSelectedPlanRunId(value);
                  setShowManualRunId(false);
                  setManualRunId("");
                  setApplyState(INITIAL_EXECUTE_STATE);
                }}
              >
                <SelectTrigger>
                  <SelectValue placeholder="Choose a completed plan run" />
                </SelectTrigger>
                <SelectContent>
                  {recentPlanRuns.map((run) => (
                    <SelectItem key={run.operation_run_id} value={run.operation_run_id}>
                      {`${run.operation_run_id.slice(0, 12)} - ${new Date(run.started_at).toLocaleString()}`}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <p className="text-xs text-muted-foreground">
                {recentPlanRuns.length > 0
                  ? "The most recent completed plan is selected by default."
                  : "No completed plan runs were loaded. Use manual run ID entry if you already know the saved run you need."}
              </p>
            </div>

            <div className="rounded-2xl border bg-muted/15 p-4">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <p className="text-xs font-semibold uppercase tracking-[0.2em] text-muted-foreground">
                  Manual Fallback
                </p>
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  onClick={() => setShowManualRunId((current) => !current)}
                >
                  {showManualRunId ? "Hide Manual Entry" : "Enter Run ID Instead"}
                </Button>
              </div>
              {showManualRunId ? (
                <div className="mt-3 space-y-2">
                  <Input
                    value={manualRunId}
                    onChange={(event) => setManualRunId(event.target.value)}
                    placeholder="00000000-0000-0000-0000-000000000000"
                    className="font-mono"
                  />
                  <p className="text-xs text-muted-foreground">
                    Use this only when you already know the exact saved plan run you want to apply.
                  </p>
                </div>
              ) : null}
            </div>

            {selectedPlan ? (
              <div className="rounded-2xl border bg-muted/15 p-4">
                <p className="text-xs font-semibold uppercase tracking-[0.2em] text-muted-foreground">
                  Selected Plan
                </p>
                <p className="mt-2 break-all font-mono text-xs text-foreground">
                  {selectedPlan.operation_run_id}
                </p>
                <p className="mt-2 text-sm text-muted-foreground">
                  Completed {new Date(selectedPlan.completed_at ?? selectedPlan.started_at).toLocaleString()}
                </p>
              </div>
            ) : null}

            <div className="flex flex-wrap gap-3">
              <Button
                type="button"
                variant="destructive"
                onClick={() => setConfirmingAction("apply")}
                disabled={applyState.loading}
              >
                {applyState.loading && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                Apply Saved Work
              </Button>
              <Button asChild type="button" variant="outline">
                <Link to="/runs">Review Your Latest Run</Link>
              </Button>
            </div>
          </div>
          <ResultPanel
            state={applyState}
            idleCopy="The saved-plan result will appear here after you choose a run and apply it."
          />
        </ActionPanel>

        <ActionPanel
          panelId="recheck"
          openPanel={openPanel}
          onToggle={togglePanel}
          title="Recheck a Folder"
          description="Refresh discovery or prepare a fresh plan when a folder has changed and you want to restage work carefully."
          summary="Best when you need a validation-oriented pass without stepping through the entire wizard again."
          badge="Validation-oriented"
          impactLabel="Checks before changing anything"
          impactTone="checks"
        >
          <div className="space-y-3">
            <WizardGuidancePanel
              sections={executionStepGuidance.ingest.sections}
              title="Refresh Discovery Guidance"
              subtitle="Optional help for the validation side of this panel."
              showLabel="Show refresh guidance"
              hideLabel="Hide refresh guidance"
              defaultOpen={false}
              gridClassName="grid-cols-1"
              className="border-slate-200 bg-slate-50/70"
              panelClassName="bg-background/90 shadow-none"
            />
            <WizardGuidancePanel
              sections={executionStepGuidance.plan.sections}
              title="Prepare Plan Guidance"
              subtitle="Optional help for the planning side of this panel."
              showLabel="Show planning guidance"
              hideLabel="Hide planning guidance"
              defaultOpen={false}
              gridClassName="grid-cols-1"
              className="border-slate-200 bg-slate-50/70"
              panelClassName="bg-background/90 shadow-none"
            />
          </div>
          <div className="space-y-4 rounded-2xl border bg-background/75 p-4">
            <p className="text-xs font-semibold uppercase tracking-[0.2em] text-muted-foreground">
              Folder to Recheck
            </p>
            <p className="break-all rounded-xl border border-dashed bg-muted/25 px-3 py-3 font-mono text-sm">
              {recheckFolderPath || "Choose a server folder to validate or plan again."}
            </p>
            <div className="flex flex-wrap gap-3">
              <Button
                type="button"
                variant="outline"
                onClick={() => setPickerTarget("recheck")}
                disabled={!directoryPickerCapabilityQuery.data?.enabled}
              >
                <FolderSearch className="mr-2 h-4 w-4" />
                Browse Folders
              </Button>
              <Button
                type="button"
                variant="outline"
                onClick={() => setConfirmingAction("recheck-ingest")}
                disabled={recheckState.ingest.loading}
              >
                {recheckState.ingest.loading && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                Refresh Discovery
              </Button>
              <Button
                type="button"
                onClick={() => setConfirmingAction("recheck-plan")}
                disabled={recheckState.plan.loading}
              >
                {recheckState.plan.loading && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                Prepare Plan
              </Button>
            </div>
          </div>
          <ResultPanel
            state={recheckState.ingest}
            idleCopy="The discovery refresh result will appear here after you run Refresh Discovery."
          />
          <ResultPanel
            state={recheckState.plan}
            idleCopy="The fresh planning result will appear here after you run Prepare Plan."
          />
        </ActionPanel>

        <ActionPanel
          panelId="canonical"
          openPanel={openPanel}
          onToggle={togglePanel}
          title="Refresh Library Decisions"
          description="Preview how canonical selections would be recalculated against the current policy once the organizing work has settled."
          summary="Best after apply, when you want room to review the downstream canonical picture without crowding the result."
          badge="Post-apply follow-up"
          impactLabel="Checks before changing anything"
          impactTone="checks"
        >
          <WizardGuidancePanel
            sections={canonicalSections}
            title="Step Guidance"
            subtitle="Optional help for understanding this step."
            showLabel="Show step guidance"
            hideLabel="Hide step guidance"
            defaultOpen={false}
            gridClassName="grid-cols-1"
            className="border-emerald-100 bg-emerald-50/55"
            panelClassName="bg-background/90 shadow-none"
          />
          <div className="flex flex-wrap gap-3 rounded-2xl border bg-background/75 p-4">
            <Button
              type="button"
              onClick={() => setConfirmingAction("canonical")}
              disabled={canonicalState.loading}
            >
              {canonicalState.loading && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
              Preview Refresh
            </Button>
            <Button asChild type="button" variant="outline">
              <Link to="/duplicates">Review Duplicates</Link>
            </Button>
          </div>
          <ResultPanel
            state={canonicalState}
            idleCopy="The canonical refresh preview will appear here after you run it."
          />
        </ActionPanel>

        <ActionPanel
          panelId="tag"
          openPanel={openPanel}
          onToggle={togglePanel}
          title="Add Searchable Details"
          description="Run background enrichment after the library structure looks right, so browsing and search have richer metadata to work with."
          summary="Best as optional downstream work, once the main organize decisions already feel settled."
          badge="Optional enrichment"
          impactLabel="Runs follow-up work"
          impactTone="follow-up"
        >
          <WizardGuidancePanel
            sections={tagSections}
            title="Step Guidance"
            subtitle="Optional help for understanding this step."
            showLabel="Show step guidance"
            hideLabel="Hide step guidance"
            defaultOpen={false}
            gridClassName="grid-cols-1"
            className="border-emerald-100 bg-emerald-50/55"
            panelClassName="bg-background/90 shadow-none"
          />
          <div className="flex flex-wrap gap-3 rounded-2xl border bg-background/75 p-4">
            <Button
              type="button"
              onClick={() => setConfirmingAction("tag")}
              disabled={tagState.loading}
            >
              {tagState.loading && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
              Add Searchable Details
            </Button>
            <Button asChild type="button" variant="outline">
              <Link to="/gallery">Open Gallery</Link>
            </Button>
          </div>
          <ResultPanel
            state={tagState}
            idleCopy="The enrichment result will appear here after you start it."
          />
        </ActionPanel>
      </div>

      <ConfirmDialog
        open={confirmingAction === "recheck-ingest"}
        onOpenChange={(open) => setConfirmingAction(open ? "recheck-ingest" : null)}
        title="Refresh Discovery?"
        description="This rechecks the chosen folder and refreshes the system's visible discovery state for it."
        destructive
        onConfirm={() => executeRecheck("ingest")}
        loading={recheckState.ingest.loading}
      />
      <ConfirmDialog
        open={confirmingAction === "recheck-plan"}
        onOpenChange={(open) => setConfirmingAction(open ? "recheck-plan" : null)}
        title="Prepare Plan?"
        description="This creates a fresh planning result for the chosen folder so you can review or apply it later."
        destructive
        onConfirm={() => executeRecheck("plan")}
        loading={recheckState.plan.loading}
      />
      <ConfirmDialog
        open={confirmingAction === "apply"}
        onOpenChange={(open) => setConfirmingAction(open ? "apply" : null)}
        title="Apply Saved Work?"
        description="This uses the selected saved plan run and is the first step here that can carry out real file and ledger changes."
        destructive
        onConfirm={executeApply}
        loading={applyState.loading}
      />
      <ConfirmDialog
        open={confirmingAction === "canonical"}
        onOpenChange={(open) => setConfirmingAction(open ? "canonical" : null)}
        title="Preview Library Decision Refresh?"
        description="This runs the existing canonical refresh preview so you can inspect how current policy choices would look."
        onConfirm={executeCanonicalRefresh}
        loading={canonicalState.loading}
      />
      <ConfirmDialog
        open={confirmingAction === "tag"}
        onOpenChange={(open) => setConfirmingAction(open ? "tag" : null)}
        title="Add Searchable Details?"
        description="This starts background enrichment on the current canonical set using the existing tag enrichment endpoint."
        destructive
        onConfirm={executeTagEnrichment}
        loading={tagState.loading}
      />

      <DirectoryPickerDialog
        open={pickerTarget !== null}
        onOpenChange={(open) => {
          if (!open) setPickerTarget(null);
        }}
        capability={directoryPickerCapabilityQuery.data ?? null}
        initialPath={pickerTarget === "start" ? startFolderPath : recheckFolderPath}
        onSelect={(path) => {
          if (pickerTarget === "start") {
            setStartFolderPath(path);
            return;
          }
          setRecheckFolderPath(path);
        }}
      />
    </div>
  );
}
