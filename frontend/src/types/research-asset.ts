import type { DuplicateUploadInfo, SourceMetaInfo } from './upload';
export interface ResearchAsset {
  id: string;
  asset_type: string;
  title: string;
  title_source: string;
  title_locked: boolean;
  original_filename?: string | null;
  metadata_status?: string;
  bibliographic_summary?: Record<string, unknown>;
  description: string | null;
  source_id: string | null;
  has_source?: boolean;
  research_object_id: string | null;
  owner_id: string | null;
  owner_name?: string | null;
  owning_group_name?: string | null;
  steward_user_id?: string | null;
  origin_project_id: string | null;
  origin_project_name?: string | null;
  origin_session_id: string | null;
  classification: string;
  visibility_scope: 'private' | 'project' | 'lab_private' | 'lab_public';
  publication_status: 'active' | 'withdrawn';
  published_by: string | null;
  published_by_name: string | null;
  published_at: string | null;
  withdrawn_at: string | null;
  withdrawal_reason: string | null;
  deleted_at: string | null;
  deleted_by: string | null;
  delete_reason: string | null;
  metadata_json: Record<string, unknown>;
  created_at: string;
  updated_at: string;
  is_linked_to_project: boolean;
  can_publish: boolean;
  can_grant_training: boolean;
  can_delete: boolean;
  can_withdraw: boolean;
  can_change_classification: boolean;
  can_preview_content: boolean;
  can_request_access: boolean;
  active_access_request_id: string | null;
  active_access_request_status: string | null;
  active_access_grant_valid_until: string | null;
  withdrawn_warning: string | null;
  source_processing_state: string | null;
  source_processing_progress: number | null;
  source_error_message: string | null;
  source_type?: 'file' | 'group' | 'data_package' | string | null;
  source_meta_info?: SourceMetaInfo | null;
  duplicate_info?: DuplicateUploadInfo | null;
}

export interface BibliographicTitleCandidate {
  value: string;
  source: string;
  confidence: string;
}

export interface BibliographicIdentifierCandidate {
  identifier_type: 'doi' | 'pmid' | 'pmcid' | 'arxiv' | string;
  value: string;
  source: string;
  confidence: string;
  eligible_for_lookup: boolean;
}

export interface BibliographicProviderCandidate {
  provider: string;
  identifier_type: string;
  identifier: string;
  title: string;
  authors?: string[];
  container_title?: string;
  published_date?: string;
  doi?: string;
  pmid?: string;
  pmcid?: string;
  arxiv_id?: string;
  record_url?: string;
}

export interface AppliedBibliographicMetadata {
  authors?: string[];
  container_title?: string;
  published_date?: string;
  doi?: string;
  pmid?: string;
  pmcid?: string;
  arxiv_id?: string;
  record_url?: string;
  source?: string;
  retrieved_at?: string;
  verification_status?: string;
  keywords?: string[];
}

export interface BibliographicCatalogMetadata extends Record<string, unknown> {
  bibliographic?: AppliedBibliographicMetadata;
}

export interface BibliographicMetadata {
  asset_id: string;
  title: string;
  original_filename: string | null;
  title_source: string;
  title_locked: boolean;
  metadata_status: string;
  metadata_checked_at: string | null;
  metadata_error: string | null;
  catalog_metadata: BibliographicCatalogMetadata;
  keywords: string[];
  local_title_candidate: BibliographicTitleCandidate | null;
  identifier_candidates: BibliographicIdentifierCandidate[];
  provider_candidates: BibliographicProviderCandidate[];
  resolution: Record<string, unknown>;
  can_update: boolean;
}

export interface AssetAccessRequest {
  id: string;
  research_asset_id: string;
  source_id?: string | null;
  asset_title: string | null;
  requester_id: string;
  requester_name: string | null;
  project_id: string | null;
  purpose: string;
  duration_days: number;
  status: 'pending' | 'approved' | 'rejected' | 'canceled';
  decided_by: string | null;
  decided_by_name: string | null;
  decision_note: string | null;
  decided_at: string | null;
  grant_valid_until: string | null;
  created_at: string;
  updated_at: string;
}

export interface LibraryCatalogSearchResult {
  id: string;
  title: string;
  asset_type?: string;
  description?: string | null;
  authors: string[];
  tags: string[];
  keywords: string[];
  directions?: Array<{
    id: string;
    name: string;
    status: string;
  }>;
  steward_name: string | null;
  project_name: string | null;
  date: string | null;
  match_type: 'title' | 'keyword' | 'catalog' | 'semantic';
  can_read_content: boolean;
  can_request_access: boolean;
  active_access_request_status: string | null;
}

export interface LibraryFullTextSearchResult extends LibraryCatalogSearchResult {
  snippet: string;
}

export interface LibrarySearchResponse {
  full_text_results: LibraryFullTextSearchResult[];
  catalog_results: LibraryCatalogSearchResult[];
  full_text_search_available: boolean;
}

export interface ResourceDirectionLink {
  id: string;
  direction_id: string;
  direction_name: string;
  direction_status: string;
  purpose: string | null;
  created_at: string;
}

export interface ResourceProfile {
  asset_id: string;
  steward_user_id: string | null;
  steward_name: string | null;
  purpose: string | null;
  suitable_for: string | null;
  limitations: string | null;
  access_instructions: string | null;
  request_url: string | null;
  gpu_configuration: string | null;
  gpu_login_instructions: string | null;
  gpu_maintenance_note: string | null;
  code_repository_url: string | null;
  code_runtime_environment: string | null;
  code_license: string | null;
  code_entrypoint: string | null;
  model_weight_source: string | null;
  model_weight_version: string | null;
  model_weight_framework: string | null;
  model_weight_license: string | null;
  model_weight_usage_instructions: string | null;
  dataset_source: string | null;
  dataset_version: string | null;
  dataset_format: string | null;
  dataset_update_frequency: string | null;
  protected_access_location: string | null;
  last_confirmed_at: string | null;
  review_due_at: string | null;
  is_stale: boolean;
  can_update: boolean;
  can_manage_direction_links: boolean;
  directions: ResourceDirectionLink[];
}

export interface ResourceMaintenanceItem {
  asset_id: string;
  title: string;
  asset_type: string;
  last_confirmed_at: string | null;
  review_due_at: string | null;
  issue: 'review_missing' | 'review_overdue';
}
