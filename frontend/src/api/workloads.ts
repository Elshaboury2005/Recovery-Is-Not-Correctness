import { apiClient } from './client';

export interface WorkloadClassification {
  categories: string[];
  required_capabilities: string[];
  bottlenecks: string[];
  compatible_engines: Array<{
    engine: string;
    compatible: boolean;
    reasons: string[];
    capabilities?: Record<string, unknown>;
  }>;
  recommended_benchmark_plan?: Record<string, unknown>;
  explanation?: { method?: string; rules?: string[]; [key: string]: unknown };
  profile_evidence?: Record<string, unknown>;
  [key: string]: unknown;
}

export interface WorkloadDefinition {
  workload_id: string;
  name: string;
  dataset_profile_id: string | null;
  constraints: Record<string, unknown> | null;
  classification: WorkloadClassification;
  created_at: string;
}

export async function listWorkloads(): Promise<WorkloadDefinition[]> {
  const response = await apiClient.get<WorkloadDefinition[]>('/api/workloads');
  return response.data;
}
