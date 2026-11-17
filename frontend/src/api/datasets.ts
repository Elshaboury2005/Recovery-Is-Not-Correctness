import { apiClient } from './client';

export interface DatasetCandidate {
  name: string;
  source_uri: string;
  format: string;
  size_bytes: number;
}

export interface ProfileColumn {
  name: string;
  data_type: string;
  null_count: number;
  null_percentage: number;
  null_scope: string;
  distinct_values: number;
  distinct_scope: string;
  cardinality_ratio: number;
  timestamp_candidate: boolean;
  timestamp_parse_ratio: number;
  statistics: Record<string, unknown>;
}

export interface DatasetProfileResult {
  record_count: { value: number; scope: string };
  column_count: { value: number; scope: string };
  columns: ProfileColumn[];
  timestamp_fields: string[];
  event_time_suitability: { suitable: boolean; timestamp_fields: string[]; scope: string };
  duplicate_characteristics: { duplicate_rows: number; duplicate_ratio: number; scope: string };
  data_quality: { issues: string[]; quality_issue_count: number };
  memory_characteristics: { sample_memory_bytes: number; estimated_full_memory_bytes: number; scope: string };
  dataset: { format: string; file_size_bytes: number; estimated_record_size_bytes?: number; sample_rows: number };
  statistics_scope: Record<string, string>;
}

export interface DatasetProfile {
  profile_id: string;
  dataset_name: string;
  source_uri: string;
  status: 'queued' | 'running' | 'succeeded' | 'failed';
  progress: number;
  format: string | null;
  profile_version: number;
  result: DatasetProfileResult | null;
  error_message: string | null;
  started_at: string | null;
  finished_at: string | null;
}

export async function discoverDatasets(): Promise<DatasetCandidate[]> {
  const response = await apiClient.get<DatasetCandidate[]>('/api/datasets/discover');
  return response.data;
}

export async function listDatasetProfiles(): Promise<DatasetProfile[]> {
  const response = await apiClient.get<DatasetProfile[]>('/api/datasets/profiles');
  return response.data;
}

export async function createDatasetProfile(input: {
  source_uri: string;
  dataset_name?: string;
  sample_rows?: number;
}): Promise<Pick<DatasetProfile, 'profile_id' | 'dataset_name' | 'status' | 'progress'>> {
  const response = await apiClient.post('/api/datasets/profiles', input);
  return response.data;
}

export async function getDatasetProfile(profileId: string): Promise<DatasetProfile> {
  const response = await apiClient.get<DatasetProfile>(`/api/datasets/profiles/${profileId}`);
  return response.data;
}
