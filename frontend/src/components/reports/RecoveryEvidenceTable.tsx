import type { ReportDetail } from '../../types/report';

type Metric = NonNullable<ReportDetail['recoveryEvidence']>['metrics'][string];

const labels: Record<string, string> = {
  fault_dispatch_latency: 'Request to fault dispatch',
  confirmed_disruption_duration: 'Confirmed infrastructure disruption',
  infrastructure_recovery: 'Dispatch to infrastructure recovery',
  service_readiness_recovery: 'Dispatch to target service readiness',
  application_progress_recovery: 'Dispatch to post-readiness processing progress',
  committed_progress_recovery: 'Dispatch to post-readiness committed-batch progress',
  sustained_throughput_recovery: 'Dispatch to sustained throughput recovery',
  total_pipeline_duration: 'Pipeline start to completion',
  production_validation_completion: 'Pipeline start to production validation',
  validated_output_completion: 'Pipeline start to independent validation',
  rollback_to_service_readiness: 'Rollback to target service readiness',
};

function duration(metric: Metric): string {
  const lower = metric.lower_seconds;
  const upper = metric.upper_seconds;
  const validLower = typeof lower === 'number' && Number.isFinite(lower) && lower >= 0;
  const validUpper = typeof upper === 'number' && Number.isFinite(upper) && upper >= 0;
  if (metric.status === 'right_censored' && validLower && upper === null) {
    return `At least ${lower.toFixed(3)} s; endpoint not observed`;
  }
  if (!validLower || !validUpper || upper < lower) return 'Not observable';
  if (metric.status === 'exact' && lower === upper) return `${lower.toFixed(3)} s`;
  if (metric.status === 'interval') return `${lower.toFixed(3)}–${upper.toFixed(3)} s`;
  return 'Not observable';
}

export function RecoveryEvidenceTable({ evidence }: { evidence: ReportDetail['recoveryEvidence'] }) {
  if (!evidence?.metrics || typeof evidence.metrics !== 'object') return null;
  return (
    <section data-testid="report-recovery-evidence" className="flex flex-col gap-2">
      <h2 className="text-sm font-semibold text-slate-200">Recovery evidence by layer</h2>
      <p className="text-xs text-slate-400">
        Intervals show observation bounds. Processing progress comes from completed query batches;
        output correctness requires its separate validation. An unobserved endpoint is not zero.
      </p>
      <div className="overflow-x-auto rounded-xl border border-slate-800">
        <table className="w-full text-left text-xs">
          <thead className="bg-slate-950 text-slate-400">
            <tr><th className="p-3">Measurement</th><th className="p-3">Duration</th><th className="p-3">Observation</th></tr>
          </thead>
          <tbody className="divide-y divide-slate-800 text-slate-300">
            {Object.entries(labels).map(([key, label]) => {
              const metric = evidence.metrics[key];
              if (!metric || typeof metric !== 'object') return null;
              return (
                <tr key={key}>
                  <td className="p-3">{label}</td>
                  <td className="p-3 font-mono whitespace-nowrap">{duration(metric)}</td>
                  <td className="p-3 text-slate-400">{metric.reason || metric.status.replace(/_/g, ' ')}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </section>
  );
}
