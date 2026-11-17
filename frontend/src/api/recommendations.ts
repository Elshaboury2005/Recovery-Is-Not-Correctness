import { apiClient } from './client';

export interface ArchitectureRecommendation {
  recommendation_id: string;
  workload_id: string;
  benchmark_campaign_id: string | null;
  optimization_goal: string;
  selected_engine: string | null;
  status: string;
  result: {
    confidence?: string;
    recommended_architecture?: { engine: string; resource_configuration: Record<string, unknown> | null } | null;
    tradeoff_explanation?: string[];
    known_limitations?: string[];
    supporting_benchmark_measurements?: Array<Record<string, unknown>>;
    proposed_benchmark_plan?: Record<string, unknown> | null;
    [key: string]: unknown;
  };
}

export type OptimizationGoal = 'execution_time' | 'throughput' | 'latency' | 'resource_usage' | 'reliability' | 'balanced';

export async function listRecommendations(): Promise<ArchitectureRecommendation[]> {
  const response = await apiClient.get<ArchitectureRecommendation[]>('/api/recommendations');
  return response.data;
}

export async function createRecommendation(input: {
  workload_id: string;
  benchmark_campaign_id?: string | null;
  optimization_goal: OptimizationGoal;
  resource_constraints?: Record<string, unknown>;
}): Promise<ArchitectureRecommendation> {
  const response = await apiClient.post<ArchitectureRecommendation>('/api/recommendations', input);
  return response.data;
}
