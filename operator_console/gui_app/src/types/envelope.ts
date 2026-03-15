export interface ApiEnvelope<T = unknown> {
  ok: boolean;
  workflow_version: string;
  schema_version: string;
  generated_at: string;
  data: T;
  errors: ApiError[];
}

export interface ApiError {
  code?: string;
  message: string;
  details?: Record<string, unknown>;
}

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}
