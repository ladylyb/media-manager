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
import { JsonViewer } from "@/components/JsonViewer";
import { StatusBadge } from "@/components/StatusBadge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { CheckpointStep } from "@/components/wizard/CheckpointStep";
import { DirectoryPickerDialog } from "@/components/wizard/DirectoryPickerDialog";
import { ExecutionStep } from "@/components/wizard/ExecutionStep";
import { WizardGuidancePanel } from "@/components/wizard/WizardGuidancePanel";
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
    ingest: StepState<{ folder_path: string }>;
    plan: StepState<{ folder_path: string; strict_metadata: boolean }>;
    apply: StepState<{ run_id: string; collision_mode: string }>;
    canonical: StepState<{ policy_name: string; dry_run: boolean; preferred_roots_csv: string }>;
    tag: StepState<{ all: boolean; canonical_id: string; batch_size: number; source: string }>;
  };
}

interface StepGuidanceSection {
  title: string;
  content: string;
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

const STEP_GUIDANCE: Record<
  StepId,
  {
    description: string;
    sections: StepGuidanceSection[];
  }
> = {
  ingest: {
    description:
      "Register the target folder in the system so the rest of the pipeline can reason about the files it contains.",
    sections: [
      {
        title: "What this step does",
        content:
          "Ingest scans the folder you choose and records what files are present. Earlier workflows may have felt like they started later, but this wizard makes ingest explicit because the system needs a current inventory before it can plan anything safely.",
      },
      {
        title: "Before you run",
        content:
          "Pick the folder you want the system to inspect. In the wizard, ingest assumes you are moving through the real guided workflow, so advanced validation-only modes are left to the Operations page.",
      },
      {
        title: "What success looks like",
        content:
          "You will see a plain-English summary of whether the folder introduced brand-new material, refreshed already known files, or surfaced duplicate matches the system already understands.",
      },
      {
        title: "Risk level",
        content:
          "This step updates the system record of what files exist in the selected folder. It does not move, rename, or reorganize files yet.",
      },
    ],
  },
  "review-ingest": {
    description:
      "Confirm that discovery results look correct before asking the system to generate a plan.",
    sections: [
      {
        title: "What this step does",
        content:
          "This checkpoint helps you confirm that ingest found the right files and that the discovery outcome looks credible before the wizard moves into planning.",
      },
      {
        title: "Before you continue",
        content:
          "Review the ingest counts and watch for unexpected gaps, very low scan counts, or obvious errors that suggest the wrong folder or mode was used.",
      },
      {
        title: "What success looks like",
        content:
          "You are satisfied that the discovery result matches expectations and you are ready for the system to generate duplicate and move decisions.",
      },
      {
        title: "Risk level",
        content:
          "This is a review checkpoint. It does not call a mutating API and exists to keep a human confirmation step between discovery and planning.",
      },
    ],
  },
  plan: {
    description:
      "Prepare the system's proposed decisions for the files you just ingested, without moving or renaming anything yet.",
    sections: [
      {
        title: "What this step does",
        content:
          "Plan looks at the folder you already ingested and works out what the system would do next, such as duplicate handling and file organization decisions.",
      },
      {
        title: "Before you run",
        content:
          "This step automatically uses the same folder from Ingest. In the wizard, there is nothing extra to configure here: just confirm you are ready for the system to prepare its proposed next actions.",
      },
      {
        title: "What success looks like",
        content:
          "You receive a saved plan with a run ID and a plain-English summary. The wizard carries that run ID forward automatically into Apply, which is the first stage that actually executes the work.",
      },
      {
        title: "Risk level",
        content:
          "This step saves planning state in the system so later stages know what to do, but it does not yet move files or change canonical selections.",
      },
    ],
  },
  "review-duplicates": {
    description:
      "Use this quick safety check to confirm the planned duplicate picture looks broadly sane before Apply.",
    sections: [
      {
        title: "What this step does",
        content:
          "This is a quick pre-apply check, not a full duplicate-audit workflow. Use it to spot obvious surprises before the wizard reaches the first file-changing stage.",
      },
      {
        title: "Before you continue",
        content:
          "Focus on whether the duplicate counts and one example group look broadly plausible for the folder you just planned. If anything feels clearly wrong, stop and investigate before Apply.",
      },
      {
        title: "What success looks like",
        content:
          "You can confidently answer a simple question: does this duplicate picture look roughly right for this batch, or should you investigate before continuing?",
      },
      {
        title: "Risk level",
        content:
          "This is a review checkpoint. It does not mutate state; it exists to catch obvious red flags before the more destructive stages begin.",
      },
    ],
  },
  apply: {
    description:
      "Execute the current plan using the run ID from Plan so the prepared actions become real system outcomes.",
    sections: [
      {
        title: "What this step does",
        content:
          "Apply is where planned actions stop being hypothetical. The system uses the selected run ID to execute the work that planning prepared.",
      },
      {
        title: "Before you run",
        content:
          "Confirm the run ID came from the plan you just reviewed and that the collision mode matches how you want conflicting file targets handled.",
      },
      {
        title: "What success looks like",
        content:
          "The result shows how many actions were applied and whether any errors occurred. After this step, the pipeline can safely recalculate canonical selections against the new state.",
      },
      {
        title: "Risk level",
        content:
          "This is a high-risk mutation step. It executes durable planning outcomes and is the stage where the pipeline begins carrying out real changes rather than preparing them.",
      },
    ],
  },
  "review-apply": {
    description:
      "Confirm that the planned work was actually applied before recalculating canonical selections.",
    sections: [
      {
        title: "What this step does",
        content:
          "This checkpoint exists because Apply is a major state-changing step. You should explicitly confirm the outcome before the wizard moves into canonical recomputation.",
      },
      {
        title: "Before you continue",
        content:
          "Review the applied counts, move counts, and any reported errors. If Apply did not behave as expected, this is the moment to stop and inspect before additional downstream changes happen.",
      },
      {
        title: "What success looks like",
        content:
          "You understand the Apply outcome well enough to let the system recompute canonical selections on top of the newly applied state.",
      },
      {
        title: "Risk level",
        content:
          "This is a review checkpoint. It does not mutate state; it protects the operator from cascading into later stages without confirming the Apply result first.",
      },
    ],
  },
  canonical: {
    description:
      "Recalculate canonical selections after Apply so the system knows which files should now be treated as canonical.",
    sections: [
      {
        title: "What this step does",
        content:
          "Canonical Recompute reassesses canonical assignments using the current post-Apply state. This stage decides which instances should be treated as the canonical versions going forward.",
      },
      {
        title: "Before you run",
        content:
          "Confirm the policy and any preferred roots match the selection behavior you want. Use Dry Run if you want to preview canonical changes before writing them.",
      },
      {
        title: "What success looks like",
        content:
          "You receive changed, applied, and failed counts that show whether canonical assignments would change or were updated successfully.",
      },
      {
        title: "Risk level",
        content:
          "This is a high-risk mutation step when Dry Run is off because it updates durable canonical selection state that later operator views and enrichment steps depend on.",
      },
    ],
  },
  "review-canonical": {
    description:
      "Confirm canonical results before the wizard moves into metadata enrichment.",
    sections: [
      {
        title: "What this step does",
        content:
          "This checkpoint lets you verify that the chosen policy and changed counts make sense before tag enrichment builds on the canonical set.",
      },
      {
        title: "Before you continue",
        content:
          "Check that the policy used is the one you intended and that the changed and applied counts are believable for the batch you processed.",
      },
      {
        title: "What success looks like",
        content:
          "You are satisfied that the canonical set now reflects the state you want and that enrichment can safely proceed against it.",
      },
      {
        title: "Risk level",
        content:
          "This is a review checkpoint. It does not call a mutating endpoint; it is here so the operator explicitly confirms canonical state before enrichment.",
      },
    ],
  },
  tag: {
    description:
      "Apply metadata and tagging enrichment to the canonical media set after the upstream organization decisions are settled.",
    sections: [
      {
        title: "What this step does",
        content:
          "Tag Enrichment adds or refreshes enrichment results for canonical media. It is intentionally last because it should operate on the final canonical set, not on files that may still be moving or changing roles.",
      },
      {
        title: "Before you run",
        content:
          "Choose whether enrichment should run across all canonical items or target one canonical ID. Confirm batch size and source values before starting.",
      },
      {
        title: "What success looks like",
        content:
          "You receive a final enrichment result showing how many items were processed, which becomes part of the final guided-run summary.",
      },
      {
        title: "Risk level",
        content:
          "This is a high-risk mutation step because it updates stored enrichment results that other operator views may surface later.",
      },
    ],
  },
  summary: {
    description:
      "Review the complete guided run and confirm how the pipeline moved from discovery through enrichment.",
    sections: [
      {
        title: "What this step does",
        content:
          "Summary is the final checkpoint in the guided flow. It is not another processing stage; it exists to help you review the combined outcome of the run.",
      },
      {
        title: "Before you continue",
        content:
          "Use this page to confirm the overall pipeline result and decide whether you need to inspect supporting console views such as Runs, Duplicates, or Discover.",
      },
      {
        title: "What success looks like",
        content:
          "You can explain what happened across ingest, planning, apply, canonical recompute, and enrichment without reopening each stage one by one.",
      },
      {
        title: "Risk level",
        content:
          "This is a review checkpoint. It does not mutate state; it is the operator-facing wrap-up for the guided workflow.",
      },
    ],
  },
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
        const response = await runWizardIngest({
          folder_path: wizardState.steps.ingest.input.folder_path,
          dry_run: false,
        });
        payload = response.data;
      } else if (stepId === "plan") {
        const response = await runWizardPlan({
          folder_path: wizardState.steps.plan.input.folder_path,
          strict_metadata: false,
        });
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

  const buildIngestSummary = (payload: Record<string, unknown>) => {
    const filesScanned = asNumber(payload.files_scanned);
    const newContents = asNumber(payload.new_contents);
    const newInstances = asNumber(payload.new_instances);
    const knownMatches = asNumber(payload.duplicates_detected);
    const lines: string[] = [];

    if (filesScanned !== null) {
      lines.push(`Ingest checked ${filesScanned} file${filesScanned === 1 ? "" : "s"}.`);
    }

    if (newContents === 0) {
      lines.push("No brand-new files were discovered in this run.");
    } else if (newContents !== null) {
      lines.push(`The system discovered ${newContents} brand-new file${newContents === 1 ? "" : "s"}.`);
    }

    if (knownMatches !== null && knownMatches > 0) {
      if (filesScanned !== null && knownMatches === filesScanned) {
        lines.push("All checked files appear to match content the system already knows about.");
      } else {
        lines.push(`${knownMatches} file${knownMatches === 1 ? "" : "s"} matched content already known to the system.`);
      }
    }

    if (newInstances !== null && newInstances > 0) {
      lines.push(`The run created ${newInstances} new file record${newInstances === 1 ? "" : "s"} in the system ledger.`);
    }

    if (!lines.length) {
      lines.push("Ingest completed, but the result did not include the usual summary counters.");
    }

    return lines;
  };

  const buildReviewIngestDecision = (payload: Record<string, unknown>) => {
    const filesScanned = asNumber(payload.files_scanned);
    const newContents = asNumber(payload.new_contents);
    const knownMatches = asNumber(payload.duplicates_detected);

    const whatHappened = buildIngestSummary(payload);
    let continueIf =
      "this matches what you expected to ingest and you are ready for the system to prepare a plan.";
    let rerunIf =
      "you expected a different folder, a different file count, or brand-new material that does not appear here.";

    if ((newContents ?? 0) > 0) {
      continueIf =
        "you expected new material to be discovered and the counts look plausible for this batch.";
      rerunIf =
        "the number of new files looks too high, too low, or points to the wrong folder being selected.";
    } else if ((knownMatches ?? 0) > 0 && filesScanned !== null && knownMatches === filesScanned) {
      continueIf =
        "you expected this run to refresh or confirm files the system already knows about.";
      rerunIf =
        "you expected this folder to contain new material or a significantly different set of files.";
    }

    return {
      whatHappened,
      continueIf,
      rerunIf,
    };
  };

  const buildPlanIngestSnapshot = (payload: Record<string, unknown>) => {
    const newContents = asNumber(payload.new_contents);
    const filesScanned = asNumber(payload.files_scanned);
    const newInstances = asNumber(payload.new_instances);
    const knownMatches = asNumber(payload.duplicates_detected);

    let planningMeaning =
      "Planning will use the files found in the previous Ingest step to prepare the system's proposed next actions for this batch.";

    if ((newContents ?? 0) > 0) {
      planningMeaning =
        "Planning will prepare proposed duplicate and move decisions for the newly discovered material from the previous Ingest step.";
    } else if ((knownMatches ?? 0) > 0 && filesScanned !== null && knownMatches === filesScanned) {
      planningMeaning =
        "Planning will prepare proposed decisions for files the system already knows about, using this ingest run as the confirmed input set.";
    }

    return {
      metrics: summarizeMetrics([
        { label: "Files checked", value: filesScanned },
        { label: "Brand-new files found", value: newContents },
        { label: "Known matches", value: knownMatches },
        { label: "New file records", value: newInstances },
      ]),
      planningMeaning,
    };
  };

  const buildReviewDuplicatesDecision = () => {
    const duplicateActions = asNumber(planSummary.duplicate_actions) ?? 0;
    const groupCount = duplicates.length;
    const largestGroup = largestDuplicateGroup;

    let scaleSummary = "This plan found a small number of duplicate groups.";
    if (groupCount === 0) {
      scaleSummary =
        "This plan did not find any duplicate groups, so Apply will mainly act on non-duplicate decisions.";
    } else if (groupCount >= 10 || duplicateActions >= 10 || largestGroup >= 5) {
      scaleSummary =
        "This duplicate picture is larger than a quick sanity check would usually expect, so it deserves a closer look before Apply.";
    } else if (groupCount >= 5 || duplicateActions >= 5 || largestGroup >= 3) {
      scaleSummary =
        "This plan found a moderate number of duplicate groups, so it is worth checking that the scale still feels right for this batch.";
    }

    const whatThisPlanFound = [
      groupCount === 0
        ? "Planning did not surface any duplicate groups for this batch."
        : `Planning found ${groupCount} duplicate group${groupCount === 1 ? "" : "s"} and prepared ${duplicateActions} duplicate action${duplicateActions === 1 ? "" : "s"}.`,
      largestGroup > 0
        ? `The largest group contains ${largestGroup} file${largestGroup === 1 ? "" : "s"}.`
        : "There is no duplicate group example to inspect on this run.",
      scaleSummary,
    ];

    let continueIf =
      "the duplicate counts and the example group feel broadly plausible for the folder you just planned.";
    let investigateIf =
      "you expected almost no duplicates, far more duplicates, or the example canonical path looks obviously wrong.";

    if (groupCount === 0) {
      continueIf =
        "you expected this batch to have little or no duplicate overlap and the rest of the plan looked reasonable.";
      investigateIf =
        "you expected duplicates to appear here and their absence suggests the wrong folder or an unexpected ingest result.";
    } else if (groupCount >= 10 || duplicateActions >= 10 || largestGroup >= 5) {
      continueIf =
        "you expected a duplicate-heavy batch and this scale does not surprise you.";
      investigateIf =
        "this feels too large for the batch you intended to process or the example group suggests the wrong files were matched.";
    }

    return {
      whatThisPlanFound,
      continueIf,
      investigateIf,
    };
  };

  const renderResultConsole = (stepId: ExecutionStepId) => {
    const state = wizardState.steps[stepId];
    if (!state.result) return null;

    if (stepId === "ingest") {
      return (
        <WizardResultConsole
          title="Ingest Result"
          status="success"
          metrics={summarizeMetrics([
            { label: "Files checked", value: asNumber(ingestPayload.files_scanned) },
            { label: "Brand-new files found", value: asNumber(ingestPayload.new_contents) },
            { label: "New file records", value: asNumber(ingestPayload.new_instances) },
            { label: "Known matches", value: asNumber(ingestPayload.duplicates_detected) },
          ])}
          summaryLines={buildIngestSummary(ingestPayload)}
          nextStepHint="If this matches your expectation, continue to Review Ingest Results and then move on to planning."
          payload={state.result}
          technicalDetailsMode="modal"
        />
      );
    }

    if (stepId === "plan") {
      const runId = asString(state.result.run_id);
      return (
        <WizardResultConsole
          title="Plan Result"
          status="success"
          references={
            runId
              ? [
                  {
                    label: "Run ID",
                    value: runId,
                    helperText: "Apply will use this automatically.",
                    copyable: true,
                  },
                ]
              : []
          }
          metrics={summarizeMetrics([
            { label: "Files reviewed", value: asNumber(planSummary.scanned_count) },
            { label: "Duplicate decisions prepared", value: asNumber(planSummary.duplicate_actions) },
            { label: "Move decisions prepared", value: asNumber(planSummary.move_actions) },
          ])}
          summaryLines={[
            "Plan prepared the system's proposed next actions for the folder you just ingested.",
            ...(runId ? ["The plan was saved and is ready for Apply."] : []),
            "No files were moved or renamed in this step.",
          ]}
          nextStepHint="If this looks right, continue to Review Duplicate Groups. Apply will use this run ID automatically."
          payload={state.result}
          technicalDetailsMode="modal"
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
      const guidance = STEP_GUIDANCE.ingest;
      return (
        <ExecutionStep
          title="Ingest"
          description={guidance.description}
          riskLabel="Updates system record"
          loading={state.status === "running"}
          error={state.error}
          onRun={() => runExecutionStep("ingest")}
          onContinue={goToNextStep}
          continueDisabled={state.status !== "completed"}
          guidance={<WizardGuidancePanel sections={guidance.sections} />}
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
          </div>
        </ExecutionStep>
      );
    }

    if (currentStepId === "review-ingest") {
      const decision = ingestResult ? buildReviewIngestDecision(ingestPayload) : null;
      return (
        <CheckpointStep
          title="Review Ingest Results"
          description="Decide whether this ingest run looks correct enough to continue into planning."
          onContinue={goToNextStep}
          onRerun={() => goToStep("ingest")}
          onAbort={abortWizard}
        >
          {ingestResult ? (
            <div className="space-y-4">
              <ReviewDecisionCard
                title="Ingest Checkpoint"
                whatHappened={decision?.whatHappened ?? []}
                continueIf={decision?.continueIf ?? ""}
                rerunIf={decision?.rerunIf ?? ""}
              />
              <MetricGrid
                items={summarizeMetrics([
                  { label: "Files checked", value: asNumber(ingestPayload.files_scanned) },
                  { label: "Brand-new files found", value: asNumber(ingestPayload.new_contents) },
                  { label: "New file records", value: asNumber(ingestPayload.new_instances) },
                  { label: "Known matches", value: asNumber(ingestPayload.duplicates_detected) },
                  { label: "Metadata captured", value: asNumber(ingestPayload.metadata_extracted) },
                ])}
              />
              <ReviewSupportNote
                title="How To Use This Checkpoint"
                content="Use these numbers as supporting evidence. If the file count and discovery outcome match what you expected from this folder, continue to Plan. If the result feels off, re-run ingest with a different path before moving forward."
              />
              <TechnicalResponseButton title="Ingest Review" payload={ingestResult} />
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
      const guidance = STEP_GUIDANCE.plan;
      const ingestSnapshot = buildPlanIngestSnapshot(ingestPayload);
      return (
        <ExecutionStep
          title="Plan"
          description={guidance.description}
          riskLabel="Saves planning state"
          loading={state.status === "running"}
          error={state.error}
          onRun={() => runExecutionStep("plan")}
          onContinue={goToNextStep}
          continueDisabled={state.status !== "completed"}
          guidance={<WizardGuidancePanel sections={guidance.sections} />}
          result={renderResultConsole("plan")}
        >
          <div className="rounded-xl border bg-muted/15 p-4">
            <p className="text-[11px] font-semibold uppercase tracking-[0.2em] text-muted-foreground">
              Planning This Folder
            </p>
            <p className="mt-3 break-all rounded-lg border bg-background px-3 py-2 font-mono text-sm">
              {state.input.folder_path || "--"}
            </p>
            <p className="mt-3 text-sm text-muted-foreground">
              This path was carried forward from the completed Ingest step so the wizard can prepare the next stage automatically.
            </p>
          </div>

          <div className="rounded-xl border border-primary/15 bg-primary/[0.04] p-4">
            <p className="text-[11px] font-semibold uppercase tracking-[0.2em] text-primary/80">
              What Ingest Found
            </p>
            <p className="mt-3 text-sm leading-6 text-foreground/90">{ingestSnapshot.planningMeaning}</p>
            <div className="mt-4">
              <MetricGrid items={ingestSnapshot.metrics} />
            </div>
          </div>
        </ExecutionStep>
      );
    }

    if (currentStepId === "review-duplicates") {
      const guidance = STEP_GUIDANCE["review-duplicates"];
      const duplicateDecision = buildReviewDuplicatesDecision();
      const exampleGroup = duplicates
        .slice()
        .sort((left, right) => right.duplicates.length - left.duplicates.length)[0];
      return (
        <CheckpointStep
          title="Review Duplicate Groups"
          description={guidance.description}
          onContinue={goToNextStep}
          onRerun={() => goToStep("plan")}
          onAbort={abortWizard}
        >
          {duplicatesQuery.error && <ErrorAlert message={parseError(duplicatesQuery.error)} />}
          <div className="space-y-4">
            <ReviewDecisionCard
              title="Quick Duplicate Sanity Check"
              whatHappened={duplicateDecision.whatThisPlanFound}
              continueIf={duplicateDecision.continueIf}
              rerunIf={duplicateDecision.investigateIf}
            />
            <MetricGrid
              items={summarizeMetrics([
                { label: "Duplicate groups", value: duplicates.length },
                { label: "Largest group size", value: largestDuplicateGroup },
                { label: "Duplicate actions prepared", value: asNumber(planSummary.duplicate_actions) },
              ])}
            />
            {asString(planResult?.run_id) && (
              <PlanReferenceStrip
                label="Plan Run ID"
                value={asString(planResult?.run_id) ?? ""}
                helperText="This is the saved plan reference for the batch you are about to apply."
              />
            )}
          </div>
          {exampleGroup && (
            <div className="rounded-xl border bg-card p-4">
              <p className="text-sm font-semibold">Example duplicate group</p>
              <p className="mt-1 text-sm text-muted-foreground">
                This is one example so you can spot obvious surprises before Apply.
              </p>
              <div className="mt-3 rounded-lg border bg-muted/20 p-3">
                <p className="text-xs font-mono text-muted-foreground">Group {exampleGroup.group_id}</p>
                <p className="mt-2 text-sm">Files in group: {exampleGroup.duplicates.length}</p>
                <p className="mt-1 break-all font-mono text-xs text-muted-foreground">
                  Canonical path: {exampleGroup.canonical_path || "--"}
                </p>
              </div>
            </div>
          )}
          <ReviewSupportNote
            title="Need A Closer Look?"
            content="Use the detailed Duplicates or Gallery views only if this quick sanity check raises questions. They are optional follow-up tools, not the main task of this checkpoint."
          />
          <InlineLinks links={[{ label: "Open Duplicates", to: "/duplicates" }, { label: "Open Gallery", to: "/gallery" }]} />
        </CheckpointStep>
      );
    }

    if (currentStepId === "apply") {
      const state = wizardState.steps.apply;
      const guidance = STEP_GUIDANCE.apply;
      return (
        <ExecutionStep
          title="Apply"
          description={guidance.description}
          riskLabel="High Risk Mutation"
          strongRisk
          loading={state.status === "running"}
          error={state.error}
          onRun={() => setConfirmingStep("apply")}
          onContinue={goToNextStep}
          continueDisabled={state.status !== "completed"}
          guidance={<WizardGuidancePanel sections={guidance.sections} />}
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
      const guidance = STEP_GUIDANCE["review-apply"];
      return (
        <CheckpointStep
          title="Review Apply Results"
          description={guidance.description}
          onContinue={goToNextStep}
          onRerun={() => goToStep("apply")}
          onAbort={abortWizard}
          guidance={<WizardGuidancePanel sections={guidance.sections} />}
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
      const guidance = STEP_GUIDANCE.canonical;
      return (
        <ExecutionStep
          title="Canonical Recompute"
          description={guidance.description}
          riskLabel="High Risk Mutation"
          strongRisk
          loading={state.status === "running"}
          error={state.error}
          onRun={() => setConfirmingStep("canonical")}
          onContinue={goToNextStep}
          continueDisabled={state.status !== "completed"}
          guidance={<WizardGuidancePanel sections={guidance.sections} />}
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
      const guidance = STEP_GUIDANCE["review-canonical"];
      return (
        <CheckpointStep
          title="Review Canonical Results"
          description={guidance.description}
          onContinue={goToNextStep}
          onRerun={() => goToStep("canonical")}
          onAbort={abortWizard}
          guidance={<WizardGuidancePanel sections={guidance.sections} />}
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
      const guidance = STEP_GUIDANCE.tag;
      return (
        <ExecutionStep
          title="Tag Enrichment"
          description={guidance.description}
          riskLabel="High Risk Mutation"
          strongRisk
          loading={state.status === "running"}
          error={state.error}
          onRun={() => setConfirmingStep("tag")}
          onContinue={goToNextStep}
          continueDisabled={state.status !== "completed"}
          guidance={<WizardGuidancePanel sections={guidance.sections} />}
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

    const guidance = STEP_GUIDANCE.summary;
    return (
      <CheckpointStep
        title="Pipeline Summary"
        description={guidance.description}
        onContinue={() => {
          setWizardState(INITIAL_STATE);
          navigate("/pipeline-wizard");
        }}
        continueLabel="Start Over"
        onRerun={() => goToStep("tag")}
        onAbort={abortWizard}
        guidance={<WizardGuidancePanel sections={guidance.sections} />}
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
                Guided execution through ingest, planning, apply, canonical recompute, and enrichment, with checkpoints that explain what each stage does before you move forward.
              </p>
              <p className="mt-2 max-w-3xl text-sm text-muted-foreground">
                This wizard is designed to help operators understand the purpose of each stage, not just run the APIs in order. Execution steps perform work; review checkpoints exist so you can confirm results before the next stage begins.
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

function ReviewDecisionCard({
  title,
  whatHappened,
  continueIf,
  rerunIf,
}: {
  title: string;
  whatHappened: string[];
  continueIf: string;
  rerunIf: string;
}) {
  return (
    <Card className="border-primary/20 bg-primary/[0.04]">
      <CardContent className="space-y-4 p-5">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.22em] text-primary/80">
            Decision Checkpoint
          </p>
          <h3 className="mt-2 text-lg font-semibold text-foreground">{title}</h3>
          <p className="mt-1 text-sm text-muted-foreground">
            Use the result below to decide whether this ingest run looks correct enough to move into planning.
          </p>
        </div>

        <div className="grid gap-3 xl:grid-cols-3">
          <div className="rounded-xl border border-border/70 bg-background/80 p-4 shadow-sm xl:col-span-1">
            <p className="text-[11px] font-semibold uppercase tracking-[0.2em] text-muted-foreground">
              What Happened
            </p>
            <div className="mt-3 space-y-2">
              {whatHappened.map((line, index) => (
                <p key={`${index}-${line}`} className="text-sm leading-6 text-foreground/90">
                  {line}
                </p>
              ))}
            </div>
          </div>

          <div className="rounded-xl border border-success/20 bg-success/[0.05] p-4 shadow-sm">
            <p className="text-[11px] font-semibold uppercase tracking-[0.2em] text-success">
              Continue If
            </p>
            <p className="mt-3 text-sm leading-6 text-foreground/90">{continueIf}</p>
          </div>

          <div className="rounded-xl border border-caution/25 bg-caution/[0.08] p-4 shadow-sm">
            <p className="text-[11px] font-semibold uppercase tracking-[0.2em] text-caution">
              Re-run If
            </p>
            <p className="mt-3 text-sm leading-6 text-foreground/90">{rerunIf}</p>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

function ReviewSupportNote({ title, content }: { title: string; content: string }) {
  return (
    <Card className="border-border/70 bg-muted/[0.16]">
      <CardContent className="p-4">
        <p className="text-[11px] font-semibold uppercase tracking-[0.2em] text-muted-foreground">
          {title}
        </p>
        <p className="mt-3 text-sm leading-6 text-foreground/90">{content}</p>
      </CardContent>
    </Card>
  );
}

function TechnicalResponseButton({ title, payload }: { title: string; payload: unknown }) {
  const [open, setOpen] = useState(false);

  return (
    <>
      <div className="flex justify-start">
        <Button type="button" variant="outline" size="sm" onClick={() => setOpen(true)}>
          View technical response
        </Button>
      </div>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="max-w-3xl">
          <DialogHeader>
            <DialogTitle>{title} Technical Response</DialogTitle>
            <DialogDescription>
              Raw API details remain available for debugging, but they are optional for the guided workflow.
            </DialogDescription>
          </DialogHeader>
          <JsonViewer data={payload} title="Response Payload" collapsible={false} maxHeight="60vh" />
        </DialogContent>
      </Dialog>
    </>
  );
}

function PlanReferenceStrip({
  label,
  value,
  helperText,
}: {
  label: string;
  value: string;
  helperText: string;
}) {
  return (
    <div className="rounded-xl border border-border/70 bg-muted/15 p-4">
      <p className="text-[11px] font-semibold uppercase tracking-[0.2em] text-muted-foreground">
        Saved Plan
      </p>
      <div className="mt-3 rounded-lg border bg-background p-3">
        <p className="text-[11px] font-semibold uppercase tracking-[0.2em] text-muted-foreground">{label}</p>
        <p className="mt-2 break-all font-mono text-sm text-foreground/90">{value}</p>
        <p className="mt-2 text-sm text-muted-foreground">{helperText}</p>
      </div>
    </div>
  );
}
