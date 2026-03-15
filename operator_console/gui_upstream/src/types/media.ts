export interface CanonicalFile {
  hash: string;
  path: string;
  mime_type: string;
  size_bytes: number;
  created_at: string;
  tags?: Tag[];
  thumbnail_url?: string;
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
  path: string;
  size_bytes: number;
  created_at: string;
  is_canonical: boolean;
}

export interface MediaFileRecord {
  hash: string;
  path: string;
  status: string;
  first_seen: string;
  last_seen: string;
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
