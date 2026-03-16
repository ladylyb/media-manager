export interface Policy {
  canonical_priority: {
    selected_policy: string;
    preferred_roots: string[];
  };
  tie_breaker_rules: {
    effective_order: string[];
    policy_name: string;
    policy_version: string;
  };
  recanonicalization: {
    enabled: boolean;
  };
  metadata: {
    updated_at: string | null;
    version: number;
  };
}

export interface PolicyUpdate {
  selected_policy: string;
  preferred_roots: string[];
  recanonicalization_enabled: boolean;
  version: number;
}
