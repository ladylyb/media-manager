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
