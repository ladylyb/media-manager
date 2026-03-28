export interface CanonicalFile {
  id: string;
  filename: string;
  file_type: "image" | "video";
  media_url: string;
  poster_url?: string | null;
  matched_tags: string[];
  top_confidence_score: number | null;
  sort_tag_name?: string | null;
}

export interface CanonicalFileDetail {
  id: string;
  filename: string;
  file_type: "image" | "video";
  media_url: string;
  absolute_path: string;
}

export interface Tag {
  name: string;
  confidence: number;
  source: string;
}

export interface DuplicateGroup {
  group_id: string;
  hash: string;
  canonical_path: string;
  duplicates: DuplicateFile[];
  review_status?: "looks_right" | "needs_review" | "not_sure" | null;
  reviewed_at?: string | null;
  reviewed_canonical_instance_id?: string | null;
  is_stale?: boolean;
  stale_reason?: "canonical_changed" | "group_membership_changed" | null;
  estimated_reclaim_bytes?: number;
  reclaim_status?: "UNREVIEWED" | "REVIEWED_SAFE_TO_RECLAIM" | "ARCHIVED" | "SCHEDULED_FOR_DELETE" | "RESTORED" | null;
  reclaimable_file_count?: number;
  retention_expires_at?: string | null;
  integrity_issue_count?: number;
  integrity_broken_count?: number;
  integrity_suspect_count?: number;
}

export interface DuplicateFile {
  file_instance_id: string;
  path: string;
  media_type: string;
  is_image: boolean;
  media_url?: string | null;
  preview_url?: string | null;
  thumbnail_url?: string | null;
  is_canonical: boolean;
}

export interface MediaFileRecord {
  id: string;
  current_path: string;
  discovered_path: string;
  status: string;
  hash_sha256: string;
  discovered_at: string | null;
  ingested_at: string | null;
  deleted_at: string | null;
  size_bytes: number;
}

export interface AnalyticsSummary {
  total_records: number;
  by_status: Record<string, number>;
  avg_file_size: number;
  trend_data?: TrendPoint[];
}

export interface TrendPoint {
  date: string;
  count: number;
}

export interface HashAuditResult {
  hash: string;
  path: string;
  status: string;
  audit_note: string;
}

export interface IntegrityDashboard {
  total_files_scanned: number;
  playback_issues: number;
  quarantined: number;
  last_scan_at: string | null;
  broken_count: number;
  suspect_count: number;
  ignored_count: number;
  marked_ok_count: number;
  high_confidence_unresolved_count: number;
}

export interface IntegrityIssue {
  check_id: string;
  file_instance_id: string;
  absolute_path: string;
  status: "OK" | "SUSPECT" | "BROKEN";
  confidence: number;
  probe_status?: string | null;
  decode_status?: string | null;
  reviewed_decision?: "MARK_OK" | "IGNORE" | null;
  reviewed_at?: string | null;
  signal_types: string[];
}

export interface IntegrityFileDetail extends IntegrityIssue {
  last_checked_at: string;
  signals: Array<{
    signal_type: string;
    severity: string;
    details: Record<string, unknown>;
    created_at: string;
  }>;
}

export interface IntegrityQuarantineItem {
  file_instance_id: string;
  check_id: string;
  original_path: string;
  quarantine_path: string;
  quarantine_status: "PENDING" | "QUARANTINED" | "RESTORED";
  quarantined_at?: string | null;
  restored_at?: string | null;
}

export interface DuplicateReclaimItem {
  file_instance_id: string;
  content_id: string;
  original_path: string;
  archive_path: string;
  item_status: "PENDING" | "ARCHIVED" | "RESTORED";
  reclaimed_at?: string | null;
  expires_at?: string | null;
  restored_at?: string | null;
}

export interface RetentionRecycleItem {
  workflow: "duplicate_reclaim" | "integrity_quarantine";
  file_instance_id: string;
  source_path: string;
  recycle_path?: string | null;
  current_status: string;
  retention_expires_at?: string | null;
  recycled_at?: string | null;
  purge_after_at?: string | null;
  purged_at?: string | null;
  ready_for_recycle: boolean;
  ready_for_purge: boolean;
  days_remaining?: number | null;
}
