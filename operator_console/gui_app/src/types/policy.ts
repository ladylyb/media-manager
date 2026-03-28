export interface Policy {
  canonical_priority: {
    selected_policy: string;
    preferred_roots: string[];
  };
  integrity: {
    default_scan_mode: "FAST" | "DEEP";
    issue_min_confidence: number;
    notify_on_high_confidence: boolean;
  };
  duplicate_reclaim: {
    archive_root: string;
    default_retention_days: number;
    notify_on_reviewed_safe: boolean;
  };
  retention: {
    quarantine_root: string;
    recycle_bin_root: string;
    quarantine_retention_days: number;
    recycle_purge_days: number;
  };
  automation: {
    mode: "NOTIFY_ONLY";
  };
  naming: {
    strategy: string;
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
  naming_strategy: string;
  preferred_roots: string[];
  integrity_default_scan_mode: "FAST" | "DEEP";
  integrity_issue_min_confidence: number;
  integrity_notify_on_high_confidence: boolean;
  duplicate_reclaim_archive_root: string;
  duplicate_reclaim_default_retention_days: number;
  duplicate_reclaim_notify_on_reviewed_safe: boolean;
  integrity_quarantine_root: string;
  integrity_quarantine_retention_days: number;
  recycle_bin_root: string;
  recycle_purge_days: number;
  automation_mode: "NOTIFY_ONLY";
  recanonicalization_enabled: boolean;
  version: number;
}
