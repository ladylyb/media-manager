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
}

export interface DuplicateFile {
  file_instance_id: string;
  path: string;
  media_type: string;
  is_image: boolean;
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
