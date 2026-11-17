import React, { useEffect, useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { BarChart3Icon, PlayIcon, RefreshCwIcon, ShieldCheckIcon } from 'lucide-react';
import { toast } from 'sonner';

import { executeBenchmark, getBenchmark, listBenchmarks } from '../api/benchmarks';
import { Button } from '../components/ui/Button';
import { Card, CardHeader, CardTitle } from '../components/ui/Card';
import { EmptyState } from '../components/ui/EmptyState';
import { ErrorState } from '../components/ui/ErrorState';
import { Skeleton } from '../components/ui/Skeleton';
import { StatCard } from '../components/ui/StatCard';

export default function BenchmarkLab() {
  const queryClient = useQueryClient();
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const campaignsQuery = useQuery({ queryKey: ['benchmarks'], queryFn: listBenchmarks });
  const detailQuery = useQuery({
    queryKey: ['benchmark', selectedId],
    queryFn: () => getBenchmark(selectedId as string),
    enabled: Boolean(selectedId),
  });
  const { data: selected, refetch: refetchDetail } = detailQuery;

  useEffect(() => {
    if (!selectedId || !selected || !['queued', 'running'].includes(selected.status)) return;
    const timer = window.setTimeout(() => void refetchDetail(), 1500);
    return () => window.clearTimeout(timer);
  }, [selectedId, selected, refetchDetail]);

  useEffect(() => {
    if (!selectedId && campaignsQuery.data?.length) setSelectedId(campaignsQuery.data[0].campaign_id);
  }, [selectedId, campaignsQuery.data]);

  const executeMutation = useMutation({
    mutationFn: () => executeBenchmark(selectedId as string),
    onSuccess: () => { toast.success('Benchmark campaign queued'); void refetchDetail(); void queryClient.invalidateQueries({ queryKey: ['benchmarks'] }); },
    onError: (error) => toast.error(error instanceof Error ? error.message : 'Could not execute benchmark'),
  });

  const fastest = useMemo(() => selected?.comparison.ranked_engines[0], [selected]);
  if (campaignsQuery.isLoading) return <div className="space-y-4"><Skeleton className="h-10 w-72" /><Skeleton className="h-64 w-full" /></div>;
  if (campaignsQuery.isError) return <ErrorState title="Benchmark Lab is unavailable" description="The backend could not load benchmark campaigns." onRetry={() => void campaignsQuery.refetch()} />;

  return (
    <div className="space-y-6" data-testid="benchmark-lab-page">
      <div>
        <p className="text-xs uppercase tracking-widest text-brand-light font-semibold">Benchmark Lab</p>
        <h1 className="text-2xl font-bold text-slate-100 mt-1">Compare measured execution architectures</h1>
        <p className="text-sm text-slate-400 mt-2 max-w-3xl">Only successful runs with independent correctness evidence can rank an engine. Missing measurements stay visible.</p>
      </div>

      {!campaignsQuery.data?.length ? <EmptyState title="No benchmark campaigns yet" description="Classify a workload first, then create a controlled campaign from the benchmark API." /> : (
        <>
          <Card>
            <CardHeader><CardTitle>Campaign</CardTitle><Button variant="ghost" onClick={() => void campaignsQuery.refetch()}><RefreshCwIcon className="h-4 w-4" />Refresh</Button></CardHeader>
            <div className="flex flex-col md:flex-row gap-3">
              <select className="flex-1 rounded-md border border-surface-border bg-surface-base px-3 py-2 text-sm text-slate-200" value={selectedId ?? ''} onChange={(event) => setSelectedId(event.target.value)} aria-label="Benchmark campaign">
                {campaignsQuery.data.map((campaign) => <option key={campaign.campaign_id} value={campaign.campaign_id}>{campaign.name} · {campaign.status}</option>)}
              </select>
              <Button disabled={!selected || selected.status !== 'planned' || executeMutation.isPending} onClick={() => executeMutation.mutate()}><PlayIcon className="h-4 w-4" />Run measured campaign</Button>
            </div>
          </Card>

          {detailQuery.isLoading ? <Skeleton className="h-64 w-full" /> : detailQuery.isError || !selected ? <ErrorState title="Campaign details unavailable" description="The selected campaign could not be loaded." onRetry={() => void refetchDetail()} /> : (
            <>
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                <StatCard label="Status" value={selected.status} sub={`${selected.runs.length} attempts retained`} accent={selected.status === 'succeeded' ? 'success' : selected.status === 'failed' ? 'warning' : 'brand'} />
                <StatCard label="Recommended winner" value={selected.comparison.winner ?? 'Not established'} sub={selected.comparison.winner ? selected.comparison.winner_basis ?? 'Measured evidence' : 'Correctness evidence required'} accent={selected.comparison.winner ? 'success' : 'neutral'} />
                <StatCard label="Fastest mean" value={fastest ? `${fastest.mean_end_to_end_seconds.toFixed(2)}s` : '—'} sub={fastest ? `${fastest.engine} · ${fastest.confidence} confidence` : 'No eligible run'} accent="brand" />
              </div>
              <Card>
                <CardHeader><CardTitle>Fairness contract</CardTitle><ShieldCheckIcon className="h-5 w-5 text-status-success" /></CardHeader>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-2 text-sm">{Object.entries(selected.fairness_contract).map(([key, value]) => <div key={key} className="flex items-center justify-between rounded-md bg-surface-base px-3 py-2"><span className="text-slate-400">{key.replace(/_/g, ' ')}</span><span className={value ? 'text-status-success' : 'text-status-error'}>{value ? 'yes' : 'no'}</span></div>)}</div>
              </Card>
              <Card>
                <CardHeader><CardTitle>Measured comparison</CardTitle><BarChart3Icon className="h-5 w-5 text-slate-400" /></CardHeader>
                {selected.comparison.ranked_engines.length ? <div className="space-y-3">{selected.comparison.ranked_engines.map((item) => <div key={item.engine} className="rounded-md border border-surface-border p-3"><div className="flex justify-between text-sm"><span className="font-semibold text-slate-200">{item.engine}</span><span className="text-slate-400">{item.mean_end_to_end_seconds.toFixed(2)}s mean · {item.confidence}</span></div><div className="mt-2 h-2 rounded bg-surface-base overflow-hidden"><div className="h-full rounded bg-brand" style={{ width: `${Math.max(8, Math.min(100, (fastest ? fastest.mean_end_to_end_seconds / item.mean_end_to_end_seconds : 0) * 100))}%` }} /></div><p className="text-xs text-slate-500 mt-2">{item.successful_measured_runs} correct measured run(s) · {item.mean_throughput_records_per_second?.toFixed(2) ?? '—'} records/sec</p></div>)}</div> : <EmptyState title="No ranked engine" description="Runs are excluded until they have measured duration and independent correctness status=passed." />}
              </Card>
              <Card>
                <CardHeader><CardTitle>Run evidence</CardTitle></CardHeader>
                <div className="overflow-x-auto"><table className="w-full text-left text-sm"><thead className="text-xs uppercase text-slate-500"><tr><th className="py-2 pr-4">Engine</th><th className="py-2 pr-4">Mode</th><th className="py-2 pr-4">Status</th><th className="py-2 pr-4">Time</th><th className="py-2">Correctness</th></tr></thead><tbody className="divide-y divide-surface-border">{selected.runs.map((run) => <tr key={run.run_id}><td className="py-3 pr-4 text-slate-200">{run.engine}</td><td className="py-3 pr-4 text-slate-400">{run.is_warmup ? 'warm-up' : `run ${run.repetition}`}</td><td className="py-3 pr-4 text-slate-400">{run.status}</td><td className="py-3 pr-4 text-slate-400">{run.metrics.end_to_end_seconds?.toFixed(2) ?? '—'}s</td><td className={run.correctness.status === 'passed' ? 'py-3 text-status-success' : 'py-3 text-status-warning'}>{run.correctness.status ?? 'unknown'}</td></tr>)}</tbody></table></div>
              </Card>
            </>
          )}
        </>
      )}
    </div>
  );
}
