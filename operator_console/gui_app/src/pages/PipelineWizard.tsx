import { useMemo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import {
  CheckSquare,
  Copy,
  FolderOpen,
  GitBranchPlus,
  ListChecks,
  RefreshCw,
  ScanSearch,
  Sparkles,
  Tag,
  Upload,
} from "lucide-react";
import { ConfirmDialog } from "@/components/ConfirmDialog";
import { ErrorAlert } from "@/components/ErrorAlert";
import { StatusBadge } from "@/components/StatusBadge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { CheckpointStep } from "@/components/wizard/CheckpointStep";
import { DirectoryPickerDialog } from "@/components/wizard/DirectoryPickerDialog";
import { ExecutionStep } from "@/components/wizard/ExecutionStep";
import { WizardLayout } from "@/components/wizard/WizardLayout";
import { WizardResultConsole } from "@/components/wizard/WizardResultConsole";
import type { WizardSidebarItem, WizardSidebarStatus } from "@/components/wizard/WizardSidebar";
import {
  getCanonical,
  getDirectoryPickerCapability,
  getDuplicates,
  invalidateReadsAfterOperation,
  runWizardApply,
  runWizardCanonicalRecompute,
  runWizardIngest,
  runWizardPlan,
  runWizardTagEnrichment,
  type OperationInvalidationTarget,
} from "@/lib/api/endpoints";
import { queryKeys } from "@/lib/api/queryKeys";
import { queryOptions } from "@/lib/api/queryOptions";
import type {
  CanonicalFile,
  DirectoryPickerCapability,
  DuplicateGroup,
  PaginatedResponse,
} from "@/types";

type StepId =
  | "ingest"
  | "review-ingest"
  | "plan"
  | "review-duplicates"
  | "apply"
  | "review-apply"
  | "canonical"
  | "review-canonical"
  | "tag"
  | "summary";

type ExecutionStepId = "ingest" | "plan" | "apply" | "canonical" | "tag";
type StepStatus = "idle" | "running" | "completed" | "failed";

interface StepState<TInput extends Record<string, unknown>> {
  status: StepStatus;
  input: TInput;
  result: Record<string, unknown> | null;
  error: string | null;
}

interface WizardState {
  currentStepId: StepId;
  steps: {
    ingest: StepState<{ folder_path: string; dry_run: boolean }>;
    plan: StepState<{ folder_path: string; strict_metadata: boolean }>;
    apply: StepState<{ run_id: string; collision_mode: string }>;
    canonical: StepState<{ policy_name: string; dry_run: boolean; preferred_roots_csv: string }>;
    tag: StepState<{ all: boolean; canonical_id: string; batch_size: number; source: string }>;
  };
}

const STEP_ORDER: StepId[] = [
  "ingest",
  "review-ingest",
  "plan",
  "review-duplicates",
  "apply",
  "review-apply",
  "canonical",
  "review-canonical",
  "tag",
  "summary",
];

const EXECUTION_TO_INVALIDATION: Record<ExecutionStepId, OperationInvalidationTarget> = {
  ingest: "ingest",
  plan: "plan",
  apply: "apply",
  canonical: "canonicalRecompute",
  tag: "tagEnrichment",
};

const INITIAL_STATE: WizardState = {
  currentStepId: "ingest",
  steps: {
    ingest: {
      status: "idle",
      input: {
        folder_path: "",
        dry_run: false,
      },
      result: null,
      error: null,
    },
    plan: {
      status: "idle",
      input: {
        folder_path: "",
        strict_metadata: false,
      },
      result: null,
      error: null,
    },
    apply: {
      status: "idle",
      input: {
        run_id: "",
        collision_mode: "rename",
      },
      result: null,
      error: null,
    },
    canonical: {
      status: "idle",
      input: {
        policy_name: "FIRST_SEEN",
        dry_run: false,
        preferred_roots_csv: "",
      },
      result: null,
      error: null,
    },
    tag: {
      status: "idle",
      input: {
        all: true,
        canonical_id: "",
        batch_size: 100,
        source: "system",
      },
      result: null,
      error: null,
    },
  },
};

const STEP_META: Record<
  StepId,
  { title: string; kind: "execution" | "checkpoint"; icon: WizardSidebarItem["icon"] }
> = {
  ingest: { title: "Ingest", kind: "execution", icon: Upload },
  "review-ingest": { title: "Review Ingest", kind: "checkpoint", icon: ScanSearch },
  plan: { title: "Plan", kind: "execution", icon: GitBranchPlus },
  "review-duplicates": { title: "Review Duplicates", kind: "checkpoint", icon: Copy },
  apply: { title: "Apply", kind: "execution", icon: CheckSquare },
  "review-apply": { title: "Review Apply", kind: "checkpoint", icon: ListChecks },
  canonical: { title: "Canonical Recompute", kind: "execution", icon: RefreshCw },
  "review-canonical": { title: "Review Canonical", kind: "checkpoint", icon: Sparkles },
  tag: { title: "Tag Enrichment", kind: "execution", icon: Tag },
  summary: { title: "Summary", kind: "checkpoint", icon: ListChecks },
};

function parseError(err: unknown): string {
  if (err instanceof Error) return err.message;
  return String(err);
}

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" ? (value as Record<string, unknown>) : {};
}

function asNumber(value: unknown): number | null {
  return typeof value === "number" ? value : null;
}

function asString(value: unknown): string | null {
  return typeof value === "string" ? value : null;
}

function summarizeMetrics(items: Array<{ label: string; value: unknown }>) {
  return items
    .filter((item) => item.value !== null && item.value !== undefined && item.value !== "")
    .map((item) => ({
      label: item.label,
      value: typeof item.value === "number" ? item.value : String(item.value),
    }));
}

function previousStepId(stepId: StepId): StepId | null {
  const index = STEP_ORDER.indexOf(stepId);
  return index > 0 ? STEP_ORDER[index - 1] : null;
}

function nextStepId(stepId: StepId): StepId | null {
  const index = STEP_ORDER.indexOf(stepId);
  return index >= 0 && index < STEP_ORDER.length - 1 ? STEP_ORDER[index + 1] : null;
}

function canVisitStep(state: WizardState, stepId: StepId) {
  switch (stepId) {
    case "ingest":
      return true;
    case "review-ingest":
      return state.steps.ingest.status === "completed";
    case "plan":
      return state.steps.ingest.status === "completed";
    case "review-duplicates":
      return state.steps.plan.status === "completed";
    case "apply":
      return state.steps.plan.status === "completed";
    case "review-apply":
      return state.steps.apply.status === "completed";
    case "canonical":
      return state.steps.apply.status === "completed";
    case "review-canonical":
      return state.steps.canonical.status === "completed";
    case "tag":
      return state.steps.canonical.status === "completed";
    case "summary":
      return state.steps.tag.status === "completed";
    default:
      return false;
  }
}

function deriveSidebarStatus(state: WizardState, stepId: StepId): WizardSidebarStatus {
  const currentIndex = STEP_ORDER.indexOf(state.currentStepId);
  const stepIndex = STEP_ORDER.indexOf(stepId);
  const meta = STEP_META[stepId];

  if (meta.kind === "execution") {
    const execState = state.steps[stepId as ExecutionStepId];
    if (execState.status === "failed") return "failed";
    if (execState.status === "completed") return "completed";
    if (stepId === state.currentStepId) return "current";
    return canVisitStep(state, stepId) ? "pending" : "blocked";
  }

  if (stepId === state.currentStepId) return "current";
  if (stepIndex < currentIndex) return "completed";
  return canVisitStep(state, stepId) ? "pending" : "blocked";
}

export default function PipelineWizard() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [wizardState, setWizardState] = useState<WizardState>(INITIAL_STATE);
  const [confirmingStep, setConfirmingStep] = useState<ExecutionStepId | null>(null);
  const [pickerTarget, setPickerTarget] = useState<"ingest" | "plan" | null>(null);

  const currentStepId = wizardState.currentStepId;
  const currentMeta = STEP_META[currentStepId];

  const duplicatesQuery = useQuery({
    queryKey: queryKeys.duplicates,
    queryFn: async () => (await getDuplicates()).data,
    staleTime: queryOptions.duplicates.staleTime,
    enabled: currentStepId === "review-duplicates" && wizardState.steps.plan.status === "completed",
  });

  const canonicalReviewQuery = useQuery({
    queryKey: queryKeys.canonical({ page: 1, limit: 1 }),
    queryFn: async () => (await getCanonical({ page: 1, limit: 1 })).data,
    staleTime: queryOptions.canonical.staleTime,
    enabled: currentStepId === "review-canonical" && wizardState.steps.canonical.status === "completed",
  });

  const directoryPickerCapabilityQuery = useQuery({
    queryKey: queryKeys.directoryPickerCapability,
    queryFn: async () => (await getDirectoryPickerCapability()).data,
    staleTime: queryOptions.directoryPicker.staleTime,
  });

  const sidebarItems = useMemo<WizardSidebarItem[]>(
    () =>
      STEP_ORDER.map((stepId) => ({
        id: stepId,
        title: STEP_META[stepId].title,
        kind: STEP_META[stepId].kind,
        icon: STEP_META[stepId].icon,
        status: deriveSidebarStatus(wizardState, stepId),
      })),
    [wizardState],
  );

  const goToStep = (stepId: StepId) => {
    if (canVisitStep(wizardState, stepId)) {
      setWizardState((current) => ({ ...current, currentStepId: stepId }));
    }
  };

  const goToNextStep = () => {
    const next = nextStepId(wizardState.currentStepId);
    if (next && canVisitStep(wizardState, next)) {
      setWizardState((current) => ({ ...current, currentStepId: next }));
    }
  };

  const abortWizard = () => {
    setWizardState(INITIAL_STATE);
    navigate("/operations");
  };

  const updateStepInput = <T extends ExecutionStepId>(
    stepId: T,
    patch: Partial<WizardState["steps"][T]["input"]>,
  ) => {
    setWizardState((current) => ({
      ...current,
      steps: {
        ...current.steps,
        [stepId]: {
          ...current.steps[stepId],
          input: {
            ...current.steps[stepId].input,
            ...patch,
          },
        },
      },
    }));
  };

  const runExecutionStep = async (stepId: ExecutionStepId) => {
    setWizardState((current) => ({
      ...current,
      steps: {
        ...current.steps,
        [stepId]: {
          ...current.steps[stepId],
          status: "running",
          error: null,
        },
      },
    }));

    try {
      let payload: Record<string, unknown>;

      if (stepId === "ingest") {
        const response = await runWizardIngest(wizardState.steps.ingest.input);
        payload = response.data;
      } else if (stepId === "plan") {
        const response = await runWizardPlan(wizardState.steps.plan.input);
        payload = response.data;
      } else if (stepId === "apply") {
        const response = await runWizardApply(wizardState.steps.apply.input);
        payload = response.data;
      } else if (stepId === "canonical") {
        const response = await runWizardCanonicalRecompute({
          policy_name: wizardState.steps.canonical.input.policy_name,
          dry_run: wizardState.steps.canonical.input.dry_run,
          preferred_roots: wizardState.steps.canonical.input.preferred_roots_csv
            .split(",")
            .map((item) => item.trim())
            .filter(Boolean),
        });
        payload = response.data;
      } else {
        const response = await runWizardTagEnrichment({
          all: wizardState.steps.tag.input.all,
          canonical_id: wizardState.steps.tag.input.all ? null : wizardState.steps.tag.input.canonical_id || null,
          batch_size: wizardState.steps.tag.input.batch_size,
          source: wizardState.steps.tag.input.source,
        });
        payload = response.data;
      }

      await invalidateReadsAfterOperation(queryClient, EXECUTION_TO_INVALIDATION[stepId]);

      setWizardState((current) => {
        const nextState: WizardState = {
          ...current,
          steps: {
            ...current.steps,
            [stepId]: {
              ...current.steps[stepId],
              status: "completed",
              result: payload,
              error: null,
            },
          },
        };

        if (stepId === "ingest") {
          nextState.steps.plan.input.folder_path = current.steps.ingest.input.folder_path;
        }

        if (stepId === "plan") {
          nextState.steps.apply.input.run_id = asString(payload.run_id) ?? "";
        }

        return nextState;
      });
    } catch (err) {
      setWizardState((current) => ({
        ...current,
        steps: {
          ...current.steps,
          [stepId]: {
            ...current.steps[stepId],
            status: "failed",
            error: parseError(err),
          },
        },
      }));
    } finally {
      setConfirmingStep(null);
    }
  };

  const ingestResult = wizardState.steps.ingest.result;
  const ingestPayload = ingestResult ? asRecord(ingestResult.summary ?? ingestResult.report ?? ingestResult) : {};
  const planResult = wizardState.steps.plan.result;
  const planSummary = planResult ? asRecord(planResult.summary) : {};
  const applyResult = wizardState.steps.apply.result;
  const applySummary = applyResult ? asRecord(applyResult.summary) : {};
  const canonicalResult = wizardState.steps.canonical.result;
  const canonicalSummary = canonicalResult ? asRecord(canonicalResult.summary) : {};
  const tagResult = wizardState.steps.tag.result;
  const duplicates = (duplicatesQuery.data as DuplicateGroup[] | undefined) ?? [];
  const largestDuplicateGroup = duplicates.reduce<number>((largest, group) => Math.max(largest, group.duplicates.length), 0);
  const canonicalPage = canonicalReviewQuery.data as PaginatedResponse<CanonicalFile> | undefined;
  const directoryPickerCapability =
    (directoryPickerCapabilityQuery.data as DirectoryPickerCapability | undefined) ?? null;
  const directoryPickerEnabled = Boolean(
    directoryPickerCapability?.enabled && directoryPickerCapability.roots.length > 0,
  );

  const renderResultConsole = (stepId: ExecutionStepId) => {
    const state = wizardState.steps[stepId];
    if (!state.result) return null;

    if (stepId === "ingest") {
      return (
        <WizardResultConsole
          title="Ingest Result"
          status="success"
          metrics={summarizeMetrics([
            { label: "Mode", value: asString(state.result.mode) ?? "UNKNOWN" },
            { label: "Files", value: asNumber(ingestPayload.files_scanned) },
            { label: "New Contents", value: asNumber(ingestPayload.new_contents) },
            { label: "New Instances", value: asNumber(ingestPayload.new_instances) },
          ])}
          payload={state.result}
        />
      );
    }

    if (stepId === "plan") {
      return (
        <WizardResultConsole
          title="Plan Result"
          status="success"
          metrics={summarizeMetrics([
            { label: "Run ID", value: asString(state.result.run_id) },
            { label: "Scanned", value: asNumber(planSummary.scanned_count) },
            { label: "Duplicate Actions", value: asNumber(planSummary.duplicate_actions) },
            { label: "Move Actions", value: asNumber(planSummary.move_actions) },
          ])}
          payload={state.result}
        />
      );
    }

    if (stepId === "apply") {
      return (
        <WizardResultConsole
          title="Apply Result"
          status="success"
          metrics={summarizeMetrics([
            { label: "Applied", value: asNumber(applySummary.applied_count) },
            { label: "Moves", value: asNumber(applySummary.moves_count) },
            { label: "Duplicates", value: asNumber(applySummary.duplicates_count) },
            { label: "Errors", value: asNumber(applySummary.errors_count) },
          ])}
          payload={state.result}
        />
      );
    }

    if (stepId === "canonical") {
      return (
        <WizardResultConsole
          title="Canonical Result"
          status="success"
          metrics={summarizeMetrics([
            { label: "Policy", value: asString(state.result.policy_name) },
            { label: "Changed", value: asNumber(canonicalSummary.changed_count) },
            { label: "Applied", value: asNumber(canonicalSummary.applied_count) },
            { label: "Failed", value: asNumber(canonicalSummary.failed_count) },
          ])}
          payload={state.result}
        />
      );
    }

    return (
      <WizardResultConsole
        title="Tag Result"
        status="success"
        metrics={summarizeMetrics([
          { label: "Scope", value: asString(state.result.scope) },
          { label: "Items Processed", value: asNumber(state.result.number_of_items_processed) },
          { label: "Operation Run", value: asString(state.result.operation_run_id) },
        ])}
        payload={state.result}
      />
    );
  };

  const renderCurrentStep = () => {
    if (currentStepId === "ingest") {
      const state = wizardState.steps.ingest;
      return (
        <ExecutionStep
          title="Ingest"
          description="Scan a target folder and register files in the ledger before planning."
          riskLabel="Moderate Mutation"
          loading={state.status === "running"}
          error={state.error}
          onRun={() => runExecutionStep("ingest")}
          onContinue={goToNextStep}
          continueDisabled={state.status !== "completed"}
          result={renderResultConsole("ingest")}
        >
          <div className="grid gap-4 lg:grid-cols-2">
            <div className="space-y-2 lg:col-span-2">
              <Label htmlFor="ingest-folder">Folder Path</Label>
              <div className="flex gap-2">
                <Input
                  id="ingest-folder"
                  value={state.input.folder_path}
                  onChange={(event) => updateStepInput("ingest", { folder_path: event.target.value })}
                  placeholder="/media/incoming"
                />
                {directoryPickerEnabled && (
                  <Button type="button" variant="outline" onClick={() => setPickerTarget("ingest")}>
                    <FolderOpen className="mr-2 h-4 w-4" />
                    Browse
                  </Button>
                )}
              </div>
              {directoryPickerCapabilityQuery.error && (
                <p className="text-xs text-muted-foreground">
                  Directory picker unavailable: {parseError(directoryPickerCapabilityQuery.error)}
                </p>
              )}
            </div>
            <div className="flex items-center justify-between rounded-xl border p-4">
              <div>
                <p className="text-sm font-medium">Dry Run</p>
                <p className="text-xs text-muted-foreground">Validate ingest without durable writes.</p>
              </div>
              <Switch checked={state.input.dry_run} onCheckedChange={(checked) => updateStepInput("ingest", { dry_run: checked })} />
            </div>
          </div>
        </ExecutionStep>
      );
    }

    if (currentStepId === "review-ingest") {
      return (
        <CheckpointStep
          title="Review Ingest Results"
          description="Confirm the ingest outcome before generating the pipeline plan."
          onContinue={goToNextStep}
          onRerun={() => goToStep("ingest")}
          onAbort={abortWizard}
        >
          {ingestResult ? (
            <div className="space-y-4">
              <MetricGrid
                items={summarizeMetrics([
                  { label: "Mode", value: asString(ingestResult.mode) ?? "UNKNOWN" },
                  { label: "Files Scanned", value: asNumber(ingestPayload.files_scanned) },
                  { label: "New Contents", value: asNumber(ingestPayload.new_contents) },
                  { label: "New Instances", value: asNumber(ingestPayload.new_instances) },
                  { label: "Duplicates", value: asNumber(ingestPayload.duplicates_detected) },
                  { label: "Metadata", value: asNumber(ingestPayload.metadata_extracted) },
                ])}
              />
              <WizardResultConsole title="Ingest Review" status="success" payload={ingestResult} />
              <InlineLinks links={[{ label: "Open Gallery", to: "/gallery" }]} />
            </div>
          ) : (
            <ErrorAlert message="No ingest result is available yet. Re-run ingest to continue." severity="warning" />
          )}
        </CheckpointStep>
      );
    }

    if (currentStepId === "plan") {
      const state = wizardState.steps.plan;
      return (
        <ExecutionStep
          title="Plan"
          description="Generate duplicate and move actions using the folder path carried forward from Ingest."
          riskLabel="Moderate Mutation"
          loading={state.status === "running"}
          error={state.error}
          onRun={() => runExecutionStep("plan")}
          onContinue={goToNextStep}
          continueDisabled={state.status !== "completed"}
          result={renderResultConsole("plan")}
        >
          <div className="grid gap-4 lg:grid-cols-2">
            <div className="space-y-2 lg:col-span-2">
              <Label htmlFor="plan-folder">Folder Path</Label>
              <div className="flex gap-2">
                <Input
                  id="plan-folder"
                  value={state.input.folder_path}
                  onChange={(event) => updateStepInput("plan", { folder_path: event.target.value })}
                  placeholder="/media/incoming"
                />
                {directoryPickerEnabled && (
                  <Button type="button" variant="outline" onClick={() => setPickerTarget("plan")}>
                    <FolderOpen className="mr-2 h-4 w-4" />
                    Browse
                  </Button>
                )}
              </div>
            </div>
            <div className="flex items-center justify-between rounded-xl border p-4">
              <div>
                <p className="text-sm font-medium">Strict Metadata</p>
                <p className="text-xs text-muted-foreground">Use stricter planning validation rules.</p>
              </div>
              <Switch checked={state.input.strict_metadata} onCheckedChange={(checked) => updateStepInput("plan", { strict_metadata: checked })} />
            </div>
          </div>
        </ExecutionStep>
      );
    }

    if (currentStepId === "review-duplicates") {
      return (
        <CheckpointStep
          title="Review Duplicate Groups"
          description="Inspect duplicate-group visibility before Apply mutates downstream state."
          onContinue={goToNextStep}
          onRerun={() => goToStep("plan")}
          onAbort={abortWizard}
        >
          {duplicatesQuery.error && <ErrorAlert message={parseError(duplicatesQuery.error)} />}
          <MetricGrid
            items={summarizeMetrics([
              { label: "Duplicate Groups", value: duplicates.length },
              { label: "Largest Group", value: largestDuplicateGroup },
              { label: "Plan Run ID", value: asString(planResult?.run_id) },
              { label: "Duplicate Actions", value: asNumber(planSummary.duplicate_actions) },
            ])}
          />
          {duplicates.length > 0 && (
            <div className="rounded-xl border bg-card p-4">
              <p className="text-sm font-semibold">Largest current duplicate group</p>
              {duplicates
                .sort((left, right) => right.duplicates.length - left.duplicates.length)
                .slice(0, 1)
                .map((group) => (
                  <div key={group.group_id} className="mt-3 rounded-lg border bg-muted/20 p-3">
                    <p className="text-xs font-mono text-muted-foreground">Group {group.group_id}</p>
                    <p className="mt-2 text-sm">Files in group: {group.duplicates.length}</p>
                    <p className="mt-1 break-all font-mono text-xs text-muted-foreground">
                      Canonical path: {group.canonical_path || "--"}
                    </p>
                  </div>
                ))}
            </div>
          )}
          <InlineLinks links={[{ label: "Open Duplicates", to: "/duplicates" }, { label: "Open Gallery", to: "/gallery" }]} />
        </CheckpointStep>
      );
    }

    if (currentStepId === "apply") {
      const state = wizardState.steps.apply;
      return (
        <ExecutionStep
          title="Apply"
          description="Execute the current plan using the run ID captured from Plan."
          riskLabel="High Risk Mutation"
          strongRisk
          loading={state.status === "running"}
          error={state.error}
          onRun={() => setConfirmingStep("apply")}
          onContinue={goToNextStep}
          continueDisabled={state.status !== "completed"}
          result={renderResultConsole("apply")}
        >
          <div className="grid gap-4 lg:grid-cols-2">
            <div className="space-y-2 lg:col-span-2">
              <Label htmlFor="apply-run-id">Run ID</Label>
              <Input
                id="apply-run-id"
                value={state.input.run_id}
                onChange={(event) => updateStepInput("apply", { run_id: event.target.value })}
                placeholder="00000000-0000-0000-0000-000000000000"
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="apply-collision">Collision Mode</Label>
              <Input
                id="apply-collision"
                value={state.input.collision_mode}
                onChange={(event) => updateStepInput("apply", { collision_mode: event.target.value })}
                placeholder="rename"
              />
            </div>
          </div>
        </ExecutionStep>
      );
    }

    if (currentStepId === "review-apply") {
      return (
        <CheckpointStep
          title="Review Apply Results"
          description="Confirm the apply stage before recalculating canonical assignments."
          onContinue={goToNextStep}
          onRerun={() => goToStep("apply")}
          onAbort={abortWizard}
        >
          {applyResult ? (
            <div className="space-y-4">
              <MetricGrid
                items={summarizeMetrics([
                  { label: "Run ID", value: asString(applyResult.run_id) },
                  { label: "Applied", value: asNumber(applySummary.applied_count) },
                  { label: "Moves", value: asNumber(applySummary.moves_count) },
                  { label: "Errors", value: asNumber(applySummary.errors_count) },
                ])}
              />
              <WizardResultConsole title="Apply Review" status="success" payload={applyResult} />
            </div>
          ) : (
            <ErrorAlert message="No apply result is available yet. Re-run Apply to continue." severity="warning" />
          )}
        </CheckpointStep>
      );
    }

    if (currentStepId === "canonical") {
      const state = wizardState.steps.canonical;
      return (
        <ExecutionStep
          title="Canonical Recompute"
          description="Recalculate canonical selections before tag enrichment."
          riskLabel="High Risk Mutation"
          strongRisk
          loading={state.status === "running"}
          error={state.error}
          onRun={() => setConfirmingStep("canonical")}
          onContinue={goToNextStep}
          continueDisabled={state.status !== "completed"}
          result={renderResultConsole("canonical")}
        >
          <div className="grid gap-4 lg:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="canonical-policy">Policy Name</Label>
              <Input
                id="canonical-policy"
                value={state.input.policy_name}
                onChange={(event) => updateStepInput("canonical", { policy_name: event.target.value })}
                placeholder="FIRST_SEEN"
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="canonical-roots">Preferred Roots</Label>
              <Textarea
                id="canonical-roots"
                value={state.input.preferred_roots_csv}
                onChange={(event) => updateStepInput("canonical", { preferred_roots_csv: event.target.value })}
                placeholder="/mnt/media/a, /mnt/media/b"
                rows={4}
              />
            </div>
            <div className="flex items-center justify-between rounded-xl border p-4">
              <div>
                <p className="text-sm font-medium">Dry Run</p>
                <p className="text-xs text-muted-foreground">Preview canonical changes without durable writes.</p>
              </div>
              <Switch checked={state.input.dry_run} onCheckedChange={(checked) => updateStepInput("canonical", { dry_run: checked })} />
            </div>
          </div>
        </ExecutionStep>
      );
    }

    if (currentStepId === "review-canonical") {
      return (
        <CheckpointStep
          title="Review Canonical Results"
          description="Inspect policy usage and changed counts before moving on to tag enrichment."
          onContinue={goToNextStep}
          onRerun={() => goToStep("canonical")}
          onAbort={abortWizard}
        >
          {canonicalReviewQuery.error && <ErrorAlert message={parseError(canonicalReviewQuery.error)} />}
          {canonicalResult ? (
            <div className="space-y-4">
              <MetricGrid
                items={summarizeMetrics([
                  { label: "Policy", value: asString(canonicalResult.policy_name) },
                  { label: "Changed", value: asNumber(canonicalSummary.changed_count) },
                  { label: "Applied", value: asNumber(canonicalSummary.applied_count) },
                  { label: "Visible Canonical", value: canonicalPage?.total },
                ])}
              />
              <WizardResultConsole title="Canonical Review" status="success" payload={canonicalResult} />
              <InlineLinks links={[{ label: "Open Gallery", to: "/gallery" }]} />
            </div>
          ) : (
            <ErrorAlert message="No canonical recompute result is available yet. Re-run the step to continue." severity="warning" />
          )}
        </CheckpointStep>
      );
    }

    if (currentStepId === "tag") {
      const state = wizardState.steps.tag;
      return (
        <ExecutionStep
          title="Tag Enrichment"
          description="Run tag enrichment on canonical media. The final summary will capture the result."
          riskLabel="High Risk Mutation"
          strongRisk
          loading={state.status === "running"}
          error={state.error}
          onRun={() => setConfirmingStep("tag")}
          onContinue={goToNextStep}
          continueDisabled={state.status !== "completed"}
          result={renderResultConsole("tag")}
        >
          <div className="grid gap-4 lg:grid-cols-2">
            <div className="flex items-center justify-between rounded-xl border p-4 lg:col-span-2">
              <div>
                <p className="text-sm font-medium">Run Across All Canonical Items</p>
                <p className="text-xs text-muted-foreground">Disable this to target a single canonical ID.</p>
              </div>
              <Switch checked={state.input.all} onCheckedChange={(checked) => updateStepInput("tag", { all: checked })} />
            </div>
            {!state.input.all && (
              <div className="space-y-2 lg:col-span-2">
                <Label htmlFor="tag-canonical-id">Canonical ID</Label>
                <Input
                  id="tag-canonical-id"
                  value={state.input.canonical_id}
                  onChange={(event) => updateStepInput("tag", { canonical_id: event.target.value })}
                  placeholder="00000000-0000-0000-0000-000000000000"
                />
              </div>
            )}
            <div className="space-y-2">
              <Label htmlFor="tag-batch-size">Batch Size</Label>
              <Input
                id="tag-batch-size"
                type="number"
                value={String(state.input.batch_size)}
                min={1}
                onChange={(event) => updateStepInput("tag", { batch_size: Number(event.target.value || 0) })}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="tag-source">Source</Label>
              <Input
                id="tag-source"
                value={state.input.source}
                onChange={(event) => updateStepInput("tag", { source: event.target.value })}
                placeholder="system"
              />
            </div>
          </div>
        </ExecutionStep>
      );
    }

    return (
      <CheckpointStep
        title="Pipeline Summary"
        description="Review the full guided run and jump to the most relevant console pages for deeper inspection."
        onContinue={() => {
          setWizardState(INITIAL_STATE);
          navigate("/pipeline-wizard");
        }}
        continueLabel="Start Over"
        onRerun={() => goToStep("tag")}
        onAbort={abortWizard}
      >
        <MetricGrid
          items={summarizeMetrics([
            { label: "Files Scanned", value: asNumber(ingestPayload.files_scanned) },
            { label: "Duplicate Actions", value: asNumber(planSummary.duplicate_actions) },
            { label: "Canonical Changes", value: asNumber(canonicalSummary.changed_count) },
            { label: "Tags Processed", value: asNumber(tagResult?.number_of_items_processed) },
          ])}
        />
        <div className="grid gap-4 xl:grid-cols-2">
          <WizardResultConsole title="Plan Snapshot" status="success" payload={planResult ?? {}} />
          <WizardResultConsole title="Tag Snapshot" status="success" payload={tagResult ?? {}} />
        </div>
        <InlineLinks
          links={[
            { label: "Open Runs", to: "/runs" },
            { label: "Open Duplicates", to: "/duplicates" },
            { label: "Open Discover", to: "/discover" },
          ]}
        />
      </CheckpointStep>
    );
  };

  return (
    <div className="space-y-6">
      <div className="border-b bg-card/70 px-6 py-5">
        <div className="mx-auto max-w-7xl space-y-2">
          <p className="text-xs font-semibold uppercase tracking-[0.3em] text-muted-foreground">Operator Console</p>
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <h1 className="text-3xl font-semibold tracking-tight">Pipeline Wizard</h1>
              <p className="mt-1 text-sm text-muted-foreground">
                Guided execution for the media pipeline with explicit checkpoints between critical stages.
              </p>
            </div>
            <StatusBadge
              label={currentMeta.kind === "execution" ? "Operation Step" : "Review Checkpoint"}
              severity={currentMeta.kind === "execution" ? "info" : "neutral"}
            />
          </div>
        </div>
      </div>

      <WizardLayout sidebarItems={sidebarItems}>{renderCurrentStep()}</WizardLayout>

      <ConfirmDialog
        open={confirmingStep === "apply"}
        onOpenChange={(open) => setConfirmingStep(open ? "apply" : null)}
        title="Execute Apply?"
        description="Apply mutates durable state and filesystem-backed planning outcomes."
        destructive
        onConfirm={() => runExecutionStep("apply")}
        loading={wizardState.steps.apply.status === "running"}
      />
      <ConfirmDialog
        open={confirmingStep === "canonical"}
        onOpenChange={(open) => setConfirmingStep(open ? "canonical" : null)}
        title="Execute Canonical Recompute?"
        description="Canonical recompute will update durable canonical selection state."
        destructive
        onConfirm={() => runExecutionStep("canonical")}
        loading={wizardState.steps.canonical.status === "running"}
      />
      <ConfirmDialog
        open={confirmingStep === "tag"}
        onOpenChange={(open) => setConfirmingStep(open ? "tag" : null)}
        title="Execute Tag Enrichment?"
        description="Tag enrichment mutates stored enrichment results for canonical media."
        destructive
        onConfirm={() => runExecutionStep("tag")}
        loading={wizardState.steps.tag.status === "running"}
      />
      <DirectoryPickerDialog
        open={pickerTarget !== null}
        onOpenChange={(open) => {
          if (!open) setPickerTarget(null);
        }}
        capability={directoryPickerCapability}
        initialPath={pickerTarget ? wizardState.steps[pickerTarget].input.folder_path : ""}
        onSelect={(path) => {
          if (!pickerTarget) return;
          updateStepInput(pickerTarget, { folder_path: path });
        }}
      />
    </div>
  );
}

function MetricGrid({ items }: { items: Array<{ label: string; value: string | number }> }) {
  return (
    <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
      {items.map((metric) => (
        <Card key={metric.label}>
          <CardContent className="p-4">
            <p className="text-[11px] font-semibold uppercase tracking-[0.2em] text-muted-foreground">{metric.label}</p>
            <p className="mt-2 break-all text-xl font-semibold">{metric.value}</p>
          </CardContent>
        </Card>
      ))}
    </div>
  );
}

function InlineLinks({ links }: { links: Array<{ label: string; to: string }> }) {
  const navigate = useNavigate();

  return (
    <div className="flex flex-wrap gap-3">
      {links.map((link) => (
        <Button key={link.to} variant="outline" onClick={() => navigate(link.to)}>
          {link.label}
        </Button>
      ))}
    </div>
  );
}
