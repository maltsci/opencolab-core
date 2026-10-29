export interface DuplicateUploadLocation {
  location_type: string;
  label: string;
  asset_id: string | null;
  project_id: string | null;
  visibility_scope: string | null;
  can_use: boolean;
}

export interface SourceMetaInfo {
  title: string;
  description: string | null;
  tags: string[];
}

export interface DuplicateUploadInfo {
  code: 'duplicate_source';
  existing_source_id: string;
  content_hash: string | null;
  can_use_existing: boolean;
  can_request_access: boolean;
  inaccessible_count: number;
  locations: DuplicateUploadLocation[];
}
