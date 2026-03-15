import { apiGet, apiPost } from "@/lib/api/client";
import type { Policy } from "@/types";

export const getPolicy = async () => apiGet<Policy>("/policy");

export const updatePolicy = async (policy: Partial<Policy>) => {
  const current = await getPolicy();
  const payload = {
    selected_policy: policy.selected_policy ?? current.data.selected_policy,
    preferred_roots: policy.preferred_roots ?? current.data.preferred_roots,
    recanonicalization_enabled:
      policy.recanonicalization_enabled ?? current.data.recanonicalization_enabled,
    version: Number(policy.version ?? current.data.version),
  };
  return apiPost<Policy>("/policy", payload);
};
