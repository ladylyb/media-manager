import { apiGet, apiPost } from "@/lib/api/client";
import type { Policy, PolicyUpdate } from "@/types";

function mapPolicy(payload: Record<string, unknown>): Policy {
  const canonicalPriority = (
    payload.canonical_priority ?? {
      selected_policy: payload.selected_policy,
      preferred_roots: payload.preferred_roots,
    }
  ) as Record<string, unknown>;
  const tieBreakerRules = (
    payload.tie_breaker_rules ?? {
      effective_order: [],
      policy_name: payload.selected_policy,
      policy_version: "v1",
    }
  ) as Record<string, unknown>;
  const recanonicalization = (
    payload.recanonicalization ?? {
      enabled: payload.recanonicalization_enabled,
    }
  ) as Record<string, unknown>;
  const metadata = (
    payload.metadata ?? {
      updated_at: null,
      version: payload.version,
    }
  ) as Record<string, unknown>;

  const naming = (
    payload.naming ?? {
      strategy: payload.naming_strategy,
    }
  ) as Record<string, unknown>;

  return {
    canonical_priority: {
      selected_policy: String(canonicalPriority.selected_policy ?? "FIRST_SEEN"),
      preferred_roots: Array.isArray(canonicalPriority.preferred_roots)
        ? canonicalPriority.preferred_roots.map(String)
        : [],
    },
    integrity: {
      default_scan_mode:
        String((payload.integrity as Record<string, unknown> | undefined)?.default_scan_mode ?? "FAST") === "DEEP"
          ? "DEEP"
          : "FAST",
      issue_min_confidence: Number(
        (payload.integrity as Record<string, unknown> | undefined)?.issue_min_confidence ?? 0.9,
      ),
      notify_on_high_confidence: Boolean(
        (payload.integrity as Record<string, unknown> | undefined)?.notify_on_high_confidence ?? true,
      ),
    },
    duplicate_reclaim: {
      archive_root: String(
        (payload.duplicate_reclaim as Record<string, unknown> | undefined)?.archive_root ??
          "/tmp/media-manager/reclaim",
      ),
      default_retention_days: Number(
        (payload.duplicate_reclaim as Record<string, unknown> | undefined)?.default_retention_days ?? 14,
      ),
      notify_on_reviewed_safe: Boolean(
        (payload.duplicate_reclaim as Record<string, unknown> | undefined)?.notify_on_reviewed_safe ?? true,
      ),
    },
    retention: {
      quarantine_root: String(
        (payload.retention as Record<string, unknown> | undefined)?.quarantine_root ??
          "/tmp/media-manager/quarantine",
      ),
      recycle_bin_root: String(
        (payload.retention as Record<string, unknown> | undefined)?.recycle_bin_root ??
          "/tmp/media-manager/recycle-bin",
      ),
      quarantine_retention_days: Number(
        (payload.retention as Record<string, unknown> | undefined)?.quarantine_retention_days ?? 14,
      ),
      recycle_purge_days: Number(
        (payload.retention as Record<string, unknown> | undefined)?.recycle_purge_days ?? 30,
      ),
    },
    automation: {
      mode: "NOTIFY_ONLY",
    },
    naming: {
      strategy: String(naming.strategy ?? "SHARED_CANONICAL_NAME"),
    },
    tie_breaker_rules: {
      effective_order: Array.isArray(tieBreakerRules.effective_order)
        ? tieBreakerRules.effective_order.map(String)
        : [],
      policy_name: String(tieBreakerRules.policy_name ?? "FIRST_SEEN"),
      policy_version: String(tieBreakerRules.policy_version ?? "v1"),
    },
    recanonicalization: {
      enabled: Boolean(recanonicalization.enabled),
    },
    metadata: {
      updated_at: metadata.updated_at ? String(metadata.updated_at) : null,
      version: Number(metadata.version ?? 0),
    },
  };
}

export const getPolicy = async () => {
  const envelope = await apiGet<Record<string, unknown>>("/policy");
  return {
    ...envelope,
    data: mapPolicy(envelope.data as Record<string, unknown>),
  };
};

export const updatePolicy = async (policy: Partial<PolicyUpdate>) => {
  const current = await getPolicy();
  const payload = {
    selected_policy: policy.selected_policy ?? current.data.canonical_priority.selected_policy,
    naming_strategy: policy.naming_strategy ?? current.data.naming.strategy,
    preferred_roots: policy.preferred_roots ?? current.data.canonical_priority.preferred_roots,
    integrity_scan_default_mode:
      policy.integrity_scan_default_mode ?? current.data.integrity.default_scan_mode,
    integrity_issue_min_confidence:
      policy.integrity_issue_min_confidence ?? current.data.integrity.issue_min_confidence,
    integrity_notify_on_high_confidence:
      policy.integrity_notify_on_high_confidence ?? current.data.integrity.notify_on_high_confidence,
    duplicate_reclaim_archive_root:
      policy.duplicate_reclaim_archive_root ?? current.data.duplicate_reclaim.archive_root,
    duplicate_reclaim_default_retention_days:
      policy.duplicate_reclaim_default_retention_days ?? current.data.duplicate_reclaim.default_retention_days,
    duplicate_reclaim_notify_on_reviewed_safe:
      policy.duplicate_reclaim_notify_on_reviewed_safe ?? current.data.duplicate_reclaim.notify_on_reviewed_safe,
    integrity_quarantine_root:
      policy.integrity_quarantine_root ?? current.data.retention.quarantine_root,
    integrity_quarantine_retention_days:
      policy.integrity_quarantine_retention_days ?? current.data.retention.quarantine_retention_days,
    recycle_bin_root: policy.recycle_bin_root ?? current.data.retention.recycle_bin_root,
    recycle_purge_days: policy.recycle_purge_days ?? current.data.retention.recycle_purge_days,
    automation_mode: policy.automation_mode ?? current.data.automation.mode,
    recanonicalization_enabled:
      policy.recanonicalization_enabled ?? current.data.recanonicalization.enabled,
    version: Number(policy.version ?? current.data.metadata.version),
  };
  const envelope = await apiPost<Record<string, unknown>>("/policy", payload);
  return {
    ...envelope,
    data: mapPolicy(envelope.data as Record<string, unknown>),
  };
};
