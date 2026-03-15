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
      "Make the saved plan real so the changes prepared in Plan are actually carried out.",
    sections: [
      {
        title: "What this step does",
        content:
          "Apply is the first point where the wizard stops preparing and starts making real changes. The system uses the saved plan from the previous step to carry out the work that planning prepared.",
      },
      {
        title: "Before you run",
        content:
          "Confirm you are ready for the wizard to apply the saved plan it just created. In the guided flow, the wizard automatically uses the same plan reference from the previous step.",
      },
      {
        title: "What success looks like",
        content:
          "You receive a plain-English summary of how many planned actions were carried out, how many moves happened, and whether any errors were reported. After this step, the pipeline can safely recalculate canonical selections against the new state.",
      },
      {
        title: "Risk level",
        content:
          "This step makes real file and ledger changes. It is the first stage where the guided flow stops being preparatory and starts carrying out the saved plan.",
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
      "Choose which file becomes the main version after Apply so later steps know which version to keep referring to.",
    sections: [
      {
        title: "What this step does",
        content:
          "This step chooses which file the system will treat as the main version going forward. Later views and enrichment use that chosen version instead of treating all duplicates equally.",
      },
      {
        title: "Before you run",
        content:
          "The wizard uses its default guided choice here, so there is nothing extra to configure. Just confirm you are ready for the system to choose the main version for the files you just applied.",
      },
      {
        title: "What success looks like",
        content:
          "You receive a plain-English summary of how many chosen-version decisions changed, how many updates were applied, and whether any failed.",
      },
      {
        title: "Risk level",
        content:
          "This step changes which file the system treats as the chosen version. It does not move files, but it does change which version later steps and views will prefer.",
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
      "Optionally add searchable tags and metadata to the chosen media items now that the main organization work is complete.",
    sections: [
      {
        title: "What enrichment does",
        content:
          "Tag Enrichment adds or refreshes metadata for the chosen media items. This can make later browsing, search, and discovery easier without changing the organization decisions you already made.",
      },
      {
        title: "Why you might run it now",
        content:
          "Running it now gives you a more complete library right away. If you would rather finish the guided workflow first, you can skip this step and run enrichment later from Operations.",
      },
      {
        title: "If you skip it",
        content:
          "Skipping enrichment does not undo your ingest, planning, apply, or chosen-version work. It only means extra tags and metadata will not be refreshed in this wizard run.",
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
        const response = await runWizardApply({
          run_id: wizardState.steps.apply.input.run_id,
          collision_mode: "rename",
        });
        payload = response.data;
      } else if (stepId === "canonical") {
        const response = await runWizardCanonicalRecompute({
          policy_name: "FIRST_SEEN",
          dry_run: false,
          preferred_roots: [],
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

  const buildReviewDuplicatesSummary = () => {
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

    const whatPlanningFound = [
      groupCount === 0
        ? "Planning did not surface any duplicate groups for this batch."
        : `Planning found ${groupCount} duplicate group${groupCount === 1 ? "" : "s"} and prepared ${duplicateActions} duplicate action${duplicateActions === 1 ? "" : "s"}.`,
      largestGroup > 0
        ? `The largest group contains ${largestGroup} file${largestGroup === 1 ? "" : "s"}.`
        : "There is no duplicate group example to inspect on this run.",
      scaleSummary,
      "This is a short progress checkpoint so you can understand what planning found before the wizard moves on.",
    ];

    return {
      whatPlanningFound,
    };
  };

  const buildReviewApplySummary = () => {
    const appliedCount = asNumber(applySummary.applied_count) ?? 0;
    const movesCount = asNumber(applySummary.moves_count) ?? 0;
    const duplicateCount = asNumber(applySummary.duplicates_count) ?? 0;
    const errorsCount = asNumber(applySummary.errors_count) ?? 0;

    if (appliedCount === 0 && movesCount === 0 && errorsCount === 0) {
      return {
        lines: [
          "Apply completed, but it did not carry out any planned changes.",
          "This often means the same folder or a very similar plan was effectively processed again.",
          "If that was not your intention, pause and inspect before moving on to canonical recomputation.",
        ],
        caution: true,
      };
    }

    const lines = [
      "Apply completed successfully.",
      `${appliedCount} planned action${appliedCount === 1 ? "" : "s"} were carried out.`,
      `${movesCount} file move${movesCount === 1 ? "" : "s"} were completed.`,
      `${duplicateCount} duplicate-related action${duplicateCount === 1 ? "" : "s"} were handled.`,
      errorsCount === 0
        ? "No errors were reported."
        : `${errorsCount} error${errorsCount === 1 ? " was" : "s were"} reported.`,
    ];

    return {
      lines,
      caution: errorsCount > 0,
    };
  };

  const buildTagResultSummary = () => {
    const result = asRecord(tagResult);
    const status = asString(result.status);
    const processedCount = asNumber(result.number_of_items_processed) ?? 0;
    const failedItems = asNumber(result.failed_items) ?? 0;
    const averageConfidence = asNumber(result.average_confidence);

    if (status === "SKIPPED") {
      return {
        lines: [
          "Tag enrichment was skipped in this wizard run.",
          "Your main organization work is still complete.",
          "You can run enrichment later from Operations if you want to add searchable tags and metadata.",
        ],
        caution: false,
      };
    }

    if (processedCount === 0 && failedItems === 0) {
      return {
        lines: [
          "Tag enrichment finished, but it did not process any chosen media items.",
          "This often means there was nothing new to enrich, or the current chosen media set was already up to date.",
          "If you expected new tagging work here, pause before continuing.",
        ],
        caution: true,
      };
    }

    const lines = [
      "Tag enrichment refreshed searchable metadata for the chosen media items.",
      `${processedCount} chosen media item${processedCount === 1 ? "" : "s"} were processed.`,
      failedItems === 0
        ? "No enrichment failures were reported."
        : `${failedItems} item${failedItems === 1 ? "" : "s"} could not be enriched.`,
    ];

    if (averageConfidence !== null) {
      lines.push(`Average confidence was ${Math.round(averageConfidence * 100)}%.`);
    }

    return {
      lines,
      caution: failedItems > 0,
    };
  };

  const buildPipelineCompletionSummary = () => {
    const filesScanned = asNumber(ingestPayload.files_scanned);
    const appliedCount = asNumber(applySummary.applied_count) ?? 0;
    const duplicateActions = asNumber(planSummary.duplicate_actions) ?? 0;
    const canonicalChanges = asNumber(canonicalSummary.changed_count) ?? 0;
    const tagStatus = asString(tagResult?.status);
    const tagProcessed = asNumber(tagResult?.number_of_items_processed) ?? 0;
    const tagFailed = asNumber(tagResult?.failed_items) ?? 0;

    const lines: string[] = [];
    let caution = false;

    if (filesScanned !== null) {
      lines.push(`Your guided media run is complete. ${filesScanned} file${filesScanned === 1 ? "" : "s"} were scanned.`);
    } else {
      lines.push("Your guided media run is complete.");
    }

    if (appliedCount === 0) {
      lines.push("No saved file actions were carried out during Apply.");
      caution = true;
    } else {
      lines.push(`${appliedCount} planned action${appliedCount === 1 ? "" : "s"} were carried out during Apply.`);
    }

    if (duplicateActions === 0) {
      lines.push("No duplicate actions were needed for this run.");
    } else {
      lines.push(`${duplicateActions} duplicate action${duplicateActions === 1 ? "" : "s"} were prepared in the run.`);
    }

    if (canonicalChanges === 0) {
      lines.push("No chosen-version changes were needed.");
    } else {
      lines.push(`${canonicalChanges} chosen-version decision${canonicalChanges === 1 ? "" : "s"} changed.`);
    }

    if (tagStatus === "SKIPPED") {
      lines.push("Searchable tag enrichment was skipped for now and can be run later from Operations.");
    } else if (tagProcessed === 0 && tagFailed === 0) {
      lines.push("Tag enrichment ran, but it did not find anything new to process.");
      caution = true;
    } else if (tagProcessed > 0) {
      lines.push(`${tagProcessed} chosen media item${tagProcessed === 1 ? "" : "s"} were enriched with searchable tags.`);
      if (tagFailed > 0) {
        lines.push(`${tagFailed} enrichment item${tagFailed === 1 ? "" : "s"} failed and may need a closer look.`);
        caution = true;
      }
    }

    return { lines, caution };
  };

  const buildPipelineTimeline = () => {
    const ingestCount = asNumber(ingestPayload.files_scanned);
    const planMoves = asNumber(planSummary.move_actions);
    const planDuplicates = asNumber(planSummary.duplicate_actions);
    const applyActions = asNumber(applySummary.applied_count) ?? 0;
    const applyMoves = asNumber(applySummary.moves_count) ?? 0;
    const canonicalChanges = asNumber(canonicalSummary.changed_count) ?? 0;
    const tagStatus = asString(tagResult?.status);
    const tagProcessed = asNumber(tagResult?.number_of_items_processed) ?? 0;

    return [
      ingestCount !== null
        ? `Ingest checked ${ingestCount} file${ingestCount === 1 ? "" : "s"} in the selected folder.`
        : "Ingest checked the selected folder.",
      planMoves !== null || planDuplicates !== null
        ? `Plan prepared ${planMoves ?? 0} move action${planMoves === 1 ? "" : "s"} and ${planDuplicates ?? 0} duplicate action${planDuplicates === 1 ? "" : "s"}.`
        : "Plan prepared the next actions for the run.",
      applyActions === 0
        ? "Apply did not carry out any saved file actions in this run."
        : `Apply carried out ${applyActions} saved action${applyActions === 1 ? "" : "s"}, including ${applyMoves} file move${applyMoves === 1 ? "" : "s"}.`,
      canonicalChanges === 0
        ? "Canonical recompute kept the existing chosen versions."
        : `Canonical recompute changed ${canonicalChanges} chosen-version decision${canonicalChanges === 1 ? "" : "s"}.`,
      tagStatus === "SKIPPED"
        ? "Tag enrichment was skipped and can be run later from Operations."
        : tagProcessed === 0
          ? "Tag enrichment ran but did not process any new chosen media items."
          : `Tag enrichment added or refreshed searchable tags for ${tagProcessed} chosen media item${tagProcessed === 1 ? "" : "s"}.`,
    ];
  };

  const buildSummaryNextSteps = () => {
    const links: Array<{ label: string; to: string }> = [{ label: "Open Runs", to: "/runs" }];
    const duplicateActions = asNumber(planSummary.duplicate_actions) ?? 0;
    const duplicateGroups = duplicates.length;
    const tagStatus = asString(tagResult?.status);
    const tagProcessed = asNumber(tagResult?.number_of_items_processed) ?? 0;

    if (duplicateActions > 0 || duplicateGroups > 0) {
      links.push({ label: "Open Duplicates", to: "/duplicates" });
    }

    if (tagStatus !== "SKIPPED" && tagProcessed > 0) {
      links.push({ label: "Open Discover", to: "/discover" });
    }

    return links;
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
      const runId = asString(state.result.run_id);
      const appliedCount = asNumber(applySummary.applied_count) ?? 0;
      const movesCount = asNumber(applySummary.moves_count) ?? 0;
      const duplicateCount = asNumber(applySummary.duplicates_count) ?? 0;
      const errorsCount = asNumber(applySummary.errors_count) ?? 0;
      const zeroOutcome = appliedCount === 0 && movesCount === 0 && errorsCount === 0;
      return (
        <WizardResultConsole
          title="Apply Result"
          status="success"
          references={
            runId
              ? [
                  {
                    label: "Run ID",
                    value: runId,
                    helperText: "This is the saved plan that was just applied.",
                    copyable: true,
                  },
                ]
              : []
          }
          metrics={summarizeMetrics([
            { label: "Planned actions completed", value: appliedCount },
            { label: "File moves completed", value: movesCount },
            { label: "Duplicate actions handled", value: duplicateCount },
            { label: "Errors reported", value: errorsCount },
          ])}
          summaryLines={
            zeroOutcome
              ? [
                  "Apply finished, but it did not carry out any planned changes.",
                  "This often means the same folder or a very similar plan was processed again.",
                  "If that was not your intention, pause before continuing.",
                ]
              : [
                  "Apply completed the saved plan for the batch you just reviewed.",
                  `${appliedCount} planned action${appliedCount === 1 ? "" : "s"} were carried out.`,
                  `${movesCount} file move${movesCount === 1 ? "" : "s"} were completed.`,
                  `${duplicateCount} duplicate-related action${duplicateCount === 1 ? "" : "s"} were handled.`,
                  errorsCount === 0
                    ? "No errors were reported."
                    : `${errorsCount} error${errorsCount === 1 ? " was" : "s were"} reported.`,
                ]
          }
          summaryTone={zeroOutcome ? "caution" : "default"}
          nextStepHint={
            zeroOutcome
              ? "If this was unexpected, pause before continuing to Review Apply Results. If you intended to reprocess the same folder, you can continue."
              : "If this looks right, continue to Review Apply Results before moving on to canonical recomputation."
          }
          nextStepTone={zeroOutcome ? "caution" : "default"}
          payload={state.result}
          technicalDetailsMode="modal"
        />
      );
    }

    if (stepId === "canonical") {
      const policyName = asString(state.result.policy_name);
      const changedCount = asNumber(canonicalSummary.changed_count) ?? 0;
      const appliedCount = asNumber(canonicalSummary.applied_count) ?? 0;
      const failedCount = asNumber(canonicalSummary.failed_count) ?? 0;
      const zeroOutcome = changedCount === 0 && appliedCount === 0 && failedCount === 0;
      return (
        <WizardResultConsole
          title="Canonical Result"
          status="success"
          references={
            policyName
              ? [
                  {
                    label: "Selection policy",
                    value: policyName,
                    helperText: "This is the guided policy the wizard used to choose the main version.",
                  },
                ]
              : []
          }
          metrics={summarizeMetrics([
            { label: "Chosen versions changed", value: changedCount },
            { label: "Updates applied", value: appliedCount },
            { label: "Failures", value: failedCount },
          ])}
          summaryLines={
            zeroOutcome
              ? [
                  "Canonical recompute finished, but it did not change any chosen-version decisions.",
                  "This often means the current post-Apply state already matched the wizard's default chosen-version rules.",
                  "If you expected different chosen versions, pause before continuing.",
                ]
              : [
                  "The system chose which file should be treated as the main version for the current post-Apply state.",
                  `${changedCount} chosen-version decision${changedCount === 1 ? "" : "s"} changed.`,
                  `${appliedCount} update${appliedCount === 1 ? "" : "s"} were applied successfully.`,
                  failedCount === 0
                    ? "No failures were reported."
                    : `${failedCount} failure${failedCount === 1 ? " was" : "s were"} reported.`,
                ]
          }
          summaryTone={zeroOutcome ? "caution" : "default"}
          nextStepHint={
            zeroOutcome
              ? "If this was unexpected, pause before continuing to Review Canonical Results. If you expected no change here, you can continue."
              : "If this looks right, continue to Review Canonical Results before moving on to enrichment."
          }
          nextStepTone={zeroOutcome ? "caution" : "default"}
          payload={state.result}
          technicalDetailsMode="modal"
        />
      );
    }

    const result = asRecord(state.result);
    const status = asString(result.status);
    const processedCount = asNumber(result.number_of_items_processed) ?? 0;
    const failedItems = asNumber(result.failed_items) ?? 0;
    const averageConfidence = asNumber(result.average_confidence);
    const tagSummary = buildTagResultSummary();
    const operationRunId = asString(result.operation_run_id);
    return (
      <WizardResultConsole
        title="Tag Result"
        status="success"
        references={
          operationRunId && status !== "SKIPPED"
            ? [
                {
                  label: "Enrichment run",
                  value: operationRunId,
                  helperText: "This is the stored enrichment run reference for this optional step.",
                  copyable: true,
                },
              ]
            : []
        }
        metrics={summarizeMetrics([
          { label: "Items processed", value: status === "SKIPPED" ? null : processedCount },
          { label: "Failed items", value: status === "SKIPPED" ? null : failedItems },
          {
            label: "Average confidence",
            value: status === "SKIPPED" || averageConfidence === null ? null : `${Math.round(averageConfidence * 100)}%`,
          },
        ])}
        summaryLines={tagSummary.lines}
        summaryTone={tagSummary.caution ? "caution" : "default"}
        nextStepHint={
          status === "SKIPPED"
            ? "Continue to the final summary. You can always run enrichment later from Operations."
            : tagSummary.caution
              ? "If this was unexpected, pause before continuing to the final summary. Otherwise, you can continue."
              : "If this looks right, continue to the final summary to review the guided run."
        }
        nextStepTone={tagSummary.caution ? "caution" : "default"}
        payload={state.result}
        technicalDetailsMode="modal"
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
      const duplicateSummary = buildReviewDuplicatesSummary();
      const exampleGroup = duplicates
        .slice()
        .sort((left, right) => right.duplicates.length - left.duplicates.length)[0];
      return (
        <CheckpointStep
          title="Review Duplicate Groups"
          description="This is a short progress checkpoint that explains what planning found about duplicates before the wizard moves on."
          onContinue={goToNextStep}
          showRerun={false}
          showAbort={false}
        >
          {duplicatesQuery.error && <ErrorAlert message={parseError(duplicatesQuery.error)} />}
          <div className="space-y-4">
            <RestPointSummaryCard title="Duplicate Summary" lines={duplicateSummary.whatPlanningFound} />
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
                This is one example from the saved plan. It is illustrative only, not a full review surface.
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
          riskLabel="Makes real changes"
          strongRisk
          loading={state.status === "running"}
          error={state.error}
          onRun={() => setConfirmingStep("apply")}
          onContinue={goToNextStep}
          continueDisabled={state.status !== "completed"}
          guidance={<WizardGuidancePanel sections={guidance.sections} />}
          result={renderResultConsole("apply")}
        >
          <div className="rounded-xl border bg-muted/15 p-4">
            <p className="text-[11px] font-semibold uppercase tracking-[0.2em] text-muted-foreground">
              Applying This Plan
            </p>
            <p className="mt-3 break-all rounded-lg border bg-background px-3 py-2 font-mono text-sm">
              {state.input.run_id || "--"}
            </p>
            <p className="mt-3 text-sm text-muted-foreground">
              This saved plan reference was carried forward from the previous Plan step. In the wizard, Apply uses the default guided collision handling automatically.
            </p>
          </div>

          <div className="rounded-xl border border-primary/15 bg-primary/[0.04] p-4">
            <p className="text-[11px] font-semibold uppercase tracking-[0.2em] text-primary/80">
              What Will Happen Next
            </p>
            <p className="mt-3 text-sm leading-6 text-foreground/90">
              The system will now carry out the saved changes from Plan. This is the first stage where file operations and durable ledger updates become real outcomes instead of proposed ones.
            </p>
          </div>
        </ExecutionStep>
      );
    }

    if (currentStepId === "review-apply") {
      const applyReviewSummary = buildReviewApplySummary();
      return (
        <CheckpointStep
          title="Review Apply Results"
          description="This checkpoint explains what Apply just did before the wizard moves on to canonical recomputation."
          onContinue={goToNextStep}
          onRerun={() => goToStep("apply")}
          onAbort={abortWizard}
        >
          {applyResult ? (
            <div className="space-y-4">
              <RestPointSummaryCard
                title="Apply Outcome"
                lines={applyReviewSummary.lines}
                tone={applyReviewSummary.caution ? "caution" : "default"}
              />
              {asString(applyResult.run_id) && (
                <PlanReferenceStrip
                  label="Run ID"
                  value={asString(applyResult.run_id) ?? ""}
                  helperText="This is the saved plan reference that Apply just executed."
                />
              )}
              <MetricGrid
                items={summarizeMetrics([
                  { label: "Actions completed", value: asNumber(applySummary.applied_count) },
                  { label: "File moves completed", value: asNumber(applySummary.moves_count) },
                  { label: "Duplicate actions handled", value: asNumber(applySummary.duplicates_count) },
                  { label: "Errors reported", value: asNumber(applySummary.errors_count) },
                ])}
              />
              <WizardResultConsole
                title="Apply Review"
                status="success"
                nextStepHint="If this outcome looks right, continue to canonical recomputation so the wizard can recalculate canonical selections on top of the new state."
                payload={applyResult}
                technicalDetailsMode="modal"
              />
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
          riskLabel="Chooses the main version"
          strongRisk
          loading={state.status === "running"}
          error={state.error}
          onRun={() => setConfirmingStep("canonical")}
          onContinue={goToNextStep}
          continueDisabled={state.status !== "completed"}
          guidance={<WizardGuidancePanel sections={guidance.sections} />}
          result={renderResultConsole("canonical")}
        >
          <div className="rounded-xl border bg-muted/15 p-4">
            <p className="text-[11px] font-semibold uppercase tracking-[0.2em] text-muted-foreground">
              Using The Updated Post-Apply State
            </p>
            <p className="mt-3 text-sm leading-6 text-foreground/90">
              Apply has already finished. This step now chooses which file should be treated as the main version for each set of related files.
            </p>
            <p className="mt-3 text-sm text-muted-foreground">
              The wizard uses its default guided policy here and keeps the more advanced canonical options on the Operations page.
            </p>
          </div>

          <div className="rounded-xl border border-primary/15 bg-primary/[0.04] p-4">
            <p className="text-[11px] font-semibold uppercase tracking-[0.2em] text-primary/80">
              What This Means
            </p>
            <p className="mt-3 text-sm leading-6 text-foreground/90">
              After files have been applied, the system still needs to decide which version should be treated as the chosen one going forward. Later views and enrichment steps will use that chosen version.
            </p>
          </div>
        </ExecutionStep>
      );
    }

    if (currentStepId === "review-canonical") {
      const changedCount = asNumber(canonicalSummary.changed_count) ?? 0;
      const appliedCount = asNumber(canonicalSummary.applied_count) ?? 0;
      const failedCount = asNumber(canonicalSummary.failed_count) ?? 0;
      const zeroOutcome = changedCount === 0 && appliedCount === 0 && failedCount === 0;
      return (
        <CheckpointStep
          title="Review Canonical Results"
          description="This checkpoint explains what the system chose as the main version before the wizard moves into enrichment."
          onContinue={goToNextStep}
          onRerun={() => goToStep("canonical")}
          onAbort={abortWizard}
        >
          {canonicalReviewQuery.error && <ErrorAlert message={parseError(canonicalReviewQuery.error)} />}
          {canonicalResult ? (
            <div className="space-y-4">
              <RestPointSummaryCard
                title="Chosen Version Summary"
                lines={
                  zeroOutcome
                    ? [
                        "Canonical recompute finished, but it did not change any chosen-version decisions.",
                        "This often means the current post-Apply state already matched the wizard's default chosen-version rules.",
                        "If that was not your expectation, pause before continuing.",
                        "Enrichment will use the currently chosen versions next.",
                      ]
                    : [
                        "The system checked which file should be treated as the chosen version going forward.",
                        `${changedCount} chosen-version decision${changedCount === 1 ? "" : "s"} changed.`,
                        `${appliedCount} update${appliedCount === 1 ? "" : "s"} were applied successfully.`,
                        failedCount === 0
                          ? "No failures were reported."
                          : `${failedCount} failure${failedCount === 1 ? " was" : "s were"} reported.`,
                        "Enrichment will use these chosen versions next.",
                      ]
                }
                tone={zeroOutcome ? "caution" : "default"}
              />
              {asString(canonicalResult.policy_name) && (
                <PlanReferenceStrip
                  label="Selection policy"
                  value={asString(canonicalResult.policy_name) ?? ""}
                  helperText="This is the guided policy the wizard used to choose the main version."
                />
              )}
              <MetricGrid
                items={summarizeMetrics([
                  { label: "Chosen versions changed", value: changedCount },
                  { label: "Updates applied", value: appliedCount },
                  { label: "Failures", value: failedCount },
                  { label: "Visible chosen items", value: canonicalPage?.total },
                ])}
              />
              <WizardResultConsole
                title="Canonical Review"
                status="success"
                nextStepHint="If this looks right, continue to enrichment so the wizard can build on the chosen versions."
                nextStepTone={zeroOutcome ? "caution" : "default"}
                payload={canonicalResult}
                technicalDetailsMode="modal"
              />
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
      const chosenItems = asNumber(canonicalReviewQuery.data?.total);
      const continueLabel = state.status === "completed" ? "Continue" : "Skip for now";
      return (
        <ExecutionStep
          title="Add Searchable Tags"
          description={guidance.description}
          riskLabel="Writes tag results"
          loading={state.status === "running"}
          error={state.error}
          onRun={() => setConfirmingStep("tag")}
          onContinue={() => {
            if (state.status === "completed") {
              goToNextStep();
              return;
            }

            setWizardState((current) => ({
              ...current,
              currentStepId: "summary",
              steps: {
                ...current.steps,
                tag: {
                  ...current.steps.tag,
                  status: "completed",
                  result: {
                    status: "SKIPPED",
                    all: true,
                    batch_size: 100,
                    source: "system",
                    note: "Tag enrichment was skipped in the wizard. It can be run later from Operations.",
                  },
                  error: null,
                },
              },
            }));
          }}
          continueLabel={continueLabel}
          continueDisabled={false}
          guidance={
            <div className="space-y-4">
              <ReviewSupportNote
                title="Using the chosen media set"
                content={
                  chosenItems !== null
                    ? `Canonical selection has already finished. If you run enrichment now, the wizard will add or refresh searchable tags for ${chosenItems} chosen media item${chosenItems === 1 ? "" : "s"}.`
                    : "Canonical selection has already finished. If you run enrichment now, the wizard will add or refresh searchable tags for the chosen media items."
                }
              />
              <Card className="border-primary/20 bg-primary/[0.04]">
                <CardContent className="space-y-4 p-5">
                  <div>
                    <p className="text-xs font-semibold uppercase tracking-[0.22em] text-primary/80">
                      Optional Final Step
                    </p>
                    <h3 className="mt-2 text-lg font-semibold text-foreground">Add extra metadata now, or skip for later</h3>
                    <p className="mt-1 text-sm text-muted-foreground">
                      Your main organization work is already complete. This step is optional and only affects searchable tags and metadata.
                    </p>
                  </div>
                  <div className="grid gap-3 xl:grid-cols-3">
                    {guidance.sections.map((section) => (
                      <div key={section.title} className="rounded-xl border border-border/70 bg-background/80 p-4 shadow-sm">
                        <p className="text-[11px] font-semibold uppercase tracking-[0.2em] text-muted-foreground">
                          {section.title}
                        </p>
                        <p className="mt-3 text-sm leading-6 text-foreground/90">{section.content}</p>
                      </div>
                    ))}
                  </div>
                </CardContent>
              </Card>
              <ReviewSupportNote
                title="What will change"
                content="This step writes or refreshes stored tag and metadata results. It does not move files or change duplicate decisions or chosen-version decisions."
              />
            </div>
          }
          result={renderResultConsole("tag")}
        />
      );
    }

    const completionSummary = buildPipelineCompletionSummary();
    const timelineLines = buildPipelineTimeline();
    const nextStepLinks = buildSummaryNextSteps();
    const tagStatus = asString(tagResult?.status);
    const tagProcessed = asNumber(tagResult?.number_of_items_processed);
    return (
      <CheckpointStep
        title="Guided Run Complete"
        description="The guided run is finished. This page gives you a quick plain-English wrap-up of what happened and what you can do next."
        onContinue={() => {
          setWizardState(INITIAL_STATE);
          navigate("/pipeline-wizard");
        }}
        continueLabel="Start Another Guided Run"
        showRerun={false}
        showAbort={false}
      >
        <RestPointSummaryCard
          title="Run Outcome"
          lines={completionSummary.lines}
          tone={completionSummary.caution ? "caution" : "default"}
        />
        <MetricGrid
          items={summarizeMetrics([
            { label: "Files scanned", value: asNumber(ingestPayload.files_scanned) },
            { label: "Actions applied", value: asNumber(applySummary.applied_count) },
            { label: "Chosen-version changes", value: asNumber(canonicalSummary.changed_count) },
            {
              label: tagStatus === "SKIPPED" ? "Tag enrichment" : "Items enriched",
              value: tagStatus === "SKIPPED" ? "Skipped" : tagProcessed,
            },
          ])}
        />
        <Card className="border-border/70 bg-muted/[0.16]">
          <CardContent className="p-4">
            <p className="text-[11px] font-semibold uppercase tracking-[0.2em] text-muted-foreground">
              What Happened In This Run
            </p>
            <div className="mt-3 space-y-3">
              {timelineLines.map((line, index) => (
                <div key={`${index}-${line}`} className="flex items-start gap-3 rounded-lg border bg-background/80 p-3">
                  <div className="mt-0.5 h-2.5 w-2.5 rounded-full bg-primary/70" />
                  <p className="text-sm leading-6 text-foreground/90">{line}</p>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
        <Card className="border-success/20 bg-success/[0.05]">
          <CardContent className="space-y-4 p-5">
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.22em] text-success">
                What You Can Do Next
              </p>
              <h3 className="mt-2 text-lg font-semibold text-foreground">Optional follow-up views</h3>
              <p className="mt-1 text-sm text-muted-foreground">
                The guided run is complete. These views are optional follow-up tools if you want more detail.
              </p>
            </div>
            <div className="flex flex-wrap gap-3">
              {nextStepLinks.map((link) => (
                <Button key={link.to} variant="outline" onClick={() => navigate(link.to)}>
                  {link.label}
                </Button>
              ))}
            </div>
          </CardContent>
        </Card>
        <TechnicalResponseButton
          title="Pipeline Summary"
          payload={{
            ingest: ingestResult ?? {},
            plan: planResult ?? {},
            apply: applyResult ?? {},
            canonical: canonicalResult ?? {},
            tag: tagResult ?? {},
          }}
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
        description="This step starts making the saved plan real. Files and records may now be changed based on the plan you just reviewed."
        destructive
        onConfirm={() => runExecutionStep("apply")}
        loading={wizardState.steps.apply.status === "running"}
      />
      <ConfirmDialog
        open={confirmingStep === "canonical"}
        onOpenChange={(open) => setConfirmingStep(open ? "canonical" : null)}
        title="Execute Canonical Recompute?"
        description="This step chooses which file should be treated as the main version going forward. Later views and enrichment will use that chosen version."
        destructive
        onConfirm={() => runExecutionStep("canonical")}
        loading={wizardState.steps.canonical.status === "running"}
      />
      <ConfirmDialog
        open={confirmingStep === "tag"}
        onOpenChange={(open) => setConfirmingStep(open ? "tag" : null)}
        title="Execute Tag Enrichment?"
        description="This step adds or refreshes searchable tags and metadata for the chosen media items. It does not move files or change the chosen versions you already reviewed."
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

function RestPointSummaryCard({
  title,
  lines,
  tone = "default",
}: {
  title: string;
  lines: string[];
  tone?: "default" | "caution";
}) {
  const containerClass =
    tone === "caution"
      ? "border-caution/30 bg-caution/[0.08]"
      : "border-primary/20 bg-primary/[0.04]";
  const eyebrowClass = tone === "caution" ? "text-caution" : "text-primary/80";

  return (
    <Card className={containerClass}>
      <CardContent className="space-y-4 p-5">
        <div>
          <p className={`text-xs font-semibold uppercase tracking-[0.22em] ${eyebrowClass}`}>
            Progress Checkpoint
          </p>
          <h3 className="mt-2 text-lg font-semibold text-foreground">{title}</h3>
          <p className="mt-1 text-sm text-muted-foreground">
            This step is informational. It gives you a plain-English summary of the duplicate picture before the wizard continues.
          </p>
        </div>
        <div className="rounded-xl border border-border/70 bg-background/80 p-4 shadow-sm">
          <p className="text-[11px] font-semibold uppercase tracking-[0.2em] text-muted-foreground">
            What Planning Found
          </p>
          <div className="mt-3 space-y-2">
            {lines.map((line, index) => (
              <p key={`${index}-${line}`} className="text-sm leading-6 text-foreground/90">
                {line}
              </p>
            ))}
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
