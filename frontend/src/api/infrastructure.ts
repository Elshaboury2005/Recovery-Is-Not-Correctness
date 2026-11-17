import { apiClient } from './client';

export interface InfrastructureNode {
  id: string;
  name: string;
  service: string | null;
  role: string;
  image: string | null;
  status: string;
  health: string | null;
  networks: string[];
  ports: string[];
}

export interface InfrastructureTopology {
  status: string;
  generated_at: string;
  project: string;
  nodes: InfrastructureNode[];
  edges: Array<{ source: string; target: string; network: string }>;
  error: string | null;
}

export interface InfrastructureComparison {
  status: string;
  generated_at: string;
  current: InfrastructureTopology;
  planned: {
    recommendation_id: string;
    status: string;
    engine: string | null;
    architecture: { engine?: string; resource_configuration?: Record<string, unknown> | null } | null;
    confidence?: string;
    optimization_goal?: string;
  } | null;
  changes: Array<{
    kind: string;
    current_engines: string[];
    planned_engine: string;
    status: string;
    evidence_based: boolean;
  }>;
  message: string;
}

export async function getInfrastructureTopology(): Promise<InfrastructureTopology> {
  const response = await apiClient.get<InfrastructureTopology>('/api/infrastructure/topology');
  return response.data;
}

export async function getInfrastructureComparison(recommendationId?: string): Promise<InfrastructureComparison> {
  const response = await apiClient.get<InfrastructureComparison>('/api/infrastructure/comparison', {
    params: recommendationId ? { recommendation_id: recommendationId } : undefined,
  });
  return response.data;
}
