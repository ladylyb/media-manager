import { apiPost } from "@/lib/api/client";
import { apiGet } from "@/lib/api/client";
import { withData } from "@/lib/api/envelope";
import { mapOperationResult } from "@/lib/api/mappers/admin";
import type { DirectoryPickerCapability, DirectoryPickerListing } from "@/types";

export const runIngest = async (params: { folder_path?: string; dry_run?: boolean }) => {
  const envelope = await apiPost<Record<string, unknown>>("/ingest", {
    folder_path: params.folder_path ?? "",
    dry_run: Boolean(params.dry_run),
  });
  return withData(envelope, mapOperationResult(envelope.data, { fallbackOperation: "INGEST" }));
};

export const runWizardIngest = async (params: { folder_path?: string; dry_run?: boolean }) =>
  apiPost<Record<string, unknown>>("/ingest", {
    folder_path: params.folder_path ?? "",
    dry_run: Boolean(params.dry_run),
  });

export const runPlan = async (params?: {
  folder_path?: string;
  strict_metadata?: boolean;
  owner?: string;
  context?: string;
  naming_strategy?: string;
  owner_context_override_confirmed?: boolean;
}) => {
  const envelope = await apiPost<Record<string, unknown>>("/plan", {
    folder_path: params?.folder_path ?? "",
    strict_metadata: Boolean(params?.strict_metadata),
    owner: params?.owner ?? "LL",
    context: params?.context ?? "General",
    naming_strategy: params?.naming_strategy ?? "SHARED_CANONICAL_NAME",
    owner_context_override_confirmed: Boolean(params?.owner_context_override_confirmed),
  });
  return withData(envelope, mapOperationResult(envelope.data, { fallbackOperation: "PLAN" }));
};

export const runWizardPlan = async (params?: {
  folder_path?: string;
  strict_metadata?: boolean;
  owner?: string;
  context?: string;
  naming_strategy?: string;
  owner_context_override_confirmed?: boolean;
}) =>
  apiPost<Record<string, unknown>>("/plan", {
    folder_path: params?.folder_path ?? "",
    strict_metadata: Boolean(params?.strict_metadata),
    owner: params?.owner ?? "LL",
    context: params?.context ?? "General",
    naming_strategy: params?.naming_strategy ?? "SHARED_CANONICAL_NAME",
    owner_context_override_confirmed: Boolean(params?.owner_context_override_confirmed),
  });

export const runApply = async (params?: { run_id?: string; collision_mode?: string }) => {
  const envelope = await apiPost<Record<string, unknown>>("/apply", {
    run_id: params?.run_id ?? "",
    collision_mode: params?.collision_mode ?? "rename",
  });
  return withData(envelope, mapOperationResult(envelope.data, { fallbackOperation: "APPLY" }));
};

export const runWizardApply = async (params?: { run_id?: string; collision_mode?: string }) =>
  apiPost<Record<string, unknown>>("/apply", {
    run_id: params?.run_id ?? "",
    collision_mode: params?.collision_mode ?? "rename",
  });

export const runCanonicalRecompute = async (params?: {
  policy_name?: string;
  dry_run?: boolean;
  preferred_roots?: string[];
}) => {
  const envelope = await apiPost<Record<string, unknown>>("/canonical/recompute", {
    policy_name: params?.policy_name ?? "FIRST_SEEN",
    dry_run: params?.dry_run ?? true,
    preferred_roots: params?.preferred_roots ?? [],
  });
  return withData(envelope, mapOperationResult(envelope.data, { fallbackOperation: "CANONICAL_RECOMPUTE" }));
};

export const runWizardCanonicalRecompute = async (params?: {
  policy_name?: string;
  dry_run?: boolean;
  preferred_roots?: string[];
}) =>
  apiPost<Record<string, unknown>>("/canonical/recompute", {
    policy_name: params?.policy_name ?? "FIRST_SEEN",
    dry_run: params?.dry_run ?? true,
    preferred_roots: params?.preferred_roots ?? [],
  });

export const runTagEnrichment = async (params?: {
  all?: boolean;
  canonical_id?: string | null;
  batch_size?: number;
  source?: string;
}) => {
  const envelope = await apiPost<Record<string, unknown>>("/tag-enrichment", {
    all: params?.all ?? true,
    canonical_id: params?.canonical_id ?? null,
    batch_size: params?.batch_size ?? 100,
    source: params?.source ?? "system",
  });
  return withData(envelope, mapOperationResult(envelope.data, { fallbackOperation: "TAG_ENRICHMENT" }));
};

export const runWizardTagEnrichment = async (params?: {
  all?: boolean;
  canonical_id?: string | null;
  batch_size?: number;
  source?: string;
}) =>
  apiPost<Record<string, unknown>>("/tag-enrichment", {
    all: params?.all ?? true,
    canonical_id: params?.canonical_id ?? null,
    batch_size: params?.batch_size ?? 100,
    source: params?.source ?? "system",
  });

export const getDirectoryPickerCapability = async () =>
  apiGet<DirectoryPickerCapability>("/directory-picker/capability");

export const getDirectoryPickerListing = async (path: string) =>
  apiGet<DirectoryPickerListing>("/directory-picker/list", { path });
