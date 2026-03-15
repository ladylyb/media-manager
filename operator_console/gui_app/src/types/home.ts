import type { CanonicalFile } from "@/types/media";
import type { Run } from "@/types/runs";

export interface HomeLibrarySummary {
  total_assets: number;
  images: number;
  videos: number;
  duplicate_groups: number;
  canonical_assets: number;
  recent_import_count: number;
}

export interface HomeAttentionSummary {
  duplicate_groups: number;
  failed_runs: number;
  active_runs: number;
  untagged_assets: number;
  unresolved_items: number;
}

export interface HomeCollection {
  label: string;
  kind: "tag";
  asset_count: number;
}

export interface HomeStatusStrip {
  workflow_label: string;
  active_phase: string;
  last_run_status: string;
  last_run_type?: string | null;
  regression_status: "PASS" | "FAIL" | "UNKNOWN";
}

export interface HomeGuidedEntry {
  label: string;
  route: string;
  helper: string;
}

export interface HomePageData {
  library_summary: HomeLibrarySummary;
  recent_media: CanonicalFile[];
  recent_images?: CanonicalFile[];
  recent_videos?: CanonicalFile[];
  attention_summary: HomeAttentionSummary;
  recent_activity: Run[];
  collections: HomeCollection[];
  status_strip: HomeStatusStrip;
  guided_entry?: HomeGuidedEntry | null;
}
