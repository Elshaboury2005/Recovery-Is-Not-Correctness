import { apiClient } from './client';

export type ReconfigurationState =
  | 'proposed'
  | 'preflight_passed'
  | 'approved'
  | 'executing'
  | 'succeeded'
  | 'failed'
  | 'blocked'
  | 'rolled_back';

export interface Reconfiguration {
  operation_id: string;
  recommendation_id: string;
  current_engine: string | null;
  target_engine: string;
  state: ReconfigurationState;
  requested_overrides: Record<string, unknown>;
  preflight_evidence: Record<string, unknown>;
  audit_events: Array<Record<string, unknown>>;
  execution_result: Record<string, unknown>;
  error_message: string | null;
}

interface ReconfigurationStateResponse {
  operation_id: string;
  state: ReconfigurationState;
}

export async function proposeReconfiguration(
  recommendationId: string,
  input: { current_engine?: string | null; target_engine?: string; overrides?: Record<string, unknown> } = {},
): Promise<Reconfiguration> {
  const response = await apiClient.post<Reconfiguration>('/api/reconfigurations', {
    recommendation_id: recommendationId,
    ...input,
  });
  return response.data;
}

export async function listReconfigurations(): Promise<Reconfiguration[]> {
  const response = await apiClient.get<Reconfiguration[]>('/api/reconfigurations');
  return response.data;
}

export async function getReconfiguration(operationId: string): Promise<Reconfiguration> {
  const response = await apiClient.get<Reconfiguration>(`/api/reconfigurations/${operationId}`);
  return response.data;
}

async function lifecycleAction(operationId: string, action: 'preflight' | 'approve' | 'execute' | 'rollback'): Promise<ReconfigurationStateResponse> {
  const response = await apiClient.post<ReconfigurationStateResponse>(`/api/reconfigurations/${operationId}/${action}`);
  return response.data;
}

export const preflightReconfiguration = (operationId: string) => lifecycleAction(operationId, 'preflight');
export const approveReconfiguration = (operationId: string) => lifecycleAction(operationId, 'approve');
export const executeReconfiguration = (operationId: string) => lifecycleAction(operationId, 'execute');
export const rollbackReconfiguration = (operationId: string) => lifecycleAction(operationId, 'rollback');
