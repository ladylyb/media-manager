export interface OperationResult {
  operation: string;
  success: boolean;
  summary: string;
  details: Record<string, unknown>;
  duration_ms: number;
}

export interface DirectoryPickerRoot {
  label: string;
  path: string;
}

export interface DirectoryPickerEntry {
  name: string;
  path: string;
}

export interface DirectoryPickerCapability {
  enabled: boolean;
  roots: DirectoryPickerRoot[];
}

export interface DirectoryPickerListing {
  current_path: string;
  parent_path: string | null;
  directories: DirectoryPickerEntry[];
}
