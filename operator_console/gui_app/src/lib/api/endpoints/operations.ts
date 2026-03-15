import { apiPost } from "@/lib/api/client";
import { withData } from "@/lib/api/envelope";
import { mapOperationResult } from "@/lib/api/mappers/admin";

export const runIngest = async (params: { folder_path?: string; dry_run?: boolean }) => {
  const envelope = await apiPost<Record<string, unknown>>("/ingest", {
    folder_path: params.folder_path ?? "",
    dry_run: Boolean(params.dry_run),
  });
  return withData(envelope, mapOperationResult(envelope.data));
};

export const runPlan = async (params?: { folder_path?: string; strict_metadata?: boolean }) => {
  const envelope = await apiPost<Record<string, unknown>>("/plan", {
    folder_path: params?.folder_path ?? "",
    strict_metadata: Boolean(params?.strict_metadata),
  });
  return withData(envelope, mapOperationResult(envelope.data));
};

export const runApply = async (params?: { run_id?: string; collision_mode?: string }) => {
  const envelope = await apiPost<Record<string, unknown>>("/apply", {
    run_id: params?.run_id ?? "",
    collision_mode: params?.collision_mode ?? "rename",
  });
  return withData(envelope, mapOperationResult(envelope.data));
};

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
  return withData(envelope, mapOperationResult(envelope.data));
};

export const runOperatorRun = async (params?: {
  folder_path?: string;
  policy_name?: string;
  dry_run?: boolean;
}) => {
  const envelope = await apiPost<Record<string, unknown>>("/run", {
    folder_path: params?.folder_path ?? "",
    policy_name: params?.policy_name ?? "FIRST_SEEN",
    dry_run: params?.dry_run ?? true,
  });
  return withData(envelope, mapOperationResult(envelope.data));
};

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
  return withData(envelope, mapOperationResult(envelope.data));
};
