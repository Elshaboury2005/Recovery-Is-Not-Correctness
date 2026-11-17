import { apiClient } from './client';

export interface BenchmarkRun {
  run_id: string;
  engine: string;
  repetition: number;
  is_warmup: boolean;
  status: string;
  configuration: Record<string, unknown>;
  metrics: {
    end_to_end_seconds: number | null;
    throughput_records_per_second: number | null;
    input_records?: number | null;
    output_records?: number | null;
    measurement_status?: string;
    [key: string]: unknown;
  };
  resource_metrics: Record<string, unknown>;
  correctness: { status?: string; validator?: { validation_status?: string; reason?: string }; reason?: string };
  software_versions: Record<string, unknown>;
  error_message: string | null;
}

export interface BenchmarkCampaign {
  campaign_id: string;
  name: string;
  status: string;
  workload_id: string;
  plan: { candidates?: Array<{ engine: string; [key: string]: unknown }>; [key: string]: unknown };
  fairness_contract: Record<string, boolean>;
  error_message: string | null;
}

export interface BenchmarkDetail extends BenchmarkCampaign {
  runs: BenchmarkRun[];
  comparison: {
    winner: string | null;
    winner_basis: string | null;
    ranked_engines: Array<{
      engine: string;
      successful_measured_runs: number;
      mean_end_to_end_seconds: number;
      mean_throughput_records_per_second: number | null;
      confidence: string;
    }>;
    excluded_runs_requirements: string[];
  };
}

export async function listBenchmarks(): Promise<BenchmarkCampaign[]> {
  const response = await apiClient.get<BenchmarkCampaign[]>('/api/benchmarks');
  return response.data;
}

export async function getBenchmark(campaignId: string): Promise<BenchmarkDetail> {
  const response = await apiClient.get<BenchmarkDetail>(`/api/benchmarks/${campaignId}`);
  return response.data;
}

export async function executeBenchmark(campaignId: string): Promise<{ campaign_id: string; status: string }> {
  const response = await apiClient.post(`/api/benchmarks/${campaignId}/execute`);
  return response.data;
}
