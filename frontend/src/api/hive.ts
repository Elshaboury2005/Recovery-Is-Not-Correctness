import { apiClient } from './client';

export interface HiveHealth {
  connected: boolean;
  status: string;
  duration_ms?: number;
  error?: string | null;
}

export interface HiveQuery {
  query_id: string;
  sql: string;
  status: string;
  row_count: number | null;
  columns: string[] | null;
  rows: unknown[][] | null;
  duration_ms: number | null;
  error_message: string | null;
}

export interface HiveTable {
  table_name: string;
  columns?: Record<string, unknown>[] | null;
  error_message?: string | null;
}

export async function getHiveHealth(): Promise<HiveHealth> {
  const response = await apiClient.get<HiveHealth>('/api/hive/health');
  return response.data;
}

export async function listHiveQueries(): Promise<HiveQuery[]> {
  const response = await apiClient.get<HiveQuery[]>('/api/hive/queries');
  return response.data;
}

export async function listHiveTables(): Promise<HiveTable[]> {
  const response = await apiClient.get<HiveTable[]>('/api/hive/tables');
  return response.data;
}

export async function registerHiveTable(input: { table_name: string; location: string; columns: { name: string; hive_type: string }[] }): Promise<HiveTable> {
  const response = await apiClient.post<HiveTable>('/api/hive/tables', input);
  return response.data;
}

export async function runHiveQuery(input: { sql: string; max_rows?: number }): Promise<HiveQuery> {
  const response = await apiClient.post<HiveQuery>('/api/hive/queries', input);
  return response.data;
}
