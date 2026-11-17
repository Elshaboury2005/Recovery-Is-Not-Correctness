import React, { useEffect, useState } from 'react';
import { LightbulbIcon, RefreshCwIcon, ShieldCheckIcon } from 'lucide-react';
import { toast } from 'sonner';

import { createRecommendation, listRecommendations, ArchitectureRecommendation, OptimizationGoal } from '../api/recommendations';
import {
  approveReconfiguration,
  executeReconfiguration,
  getReconfiguration,
  preflightReconfiguration,
  proposeReconfiguration,
  Reconfiguration,
  rollbackReconfiguration,
} from '../api/reconfigurations';
import { Button } from '../components/ui/Button';
import { Card, CardHeader, CardTitle } from '../components/ui/Card';
import { EmptyState } from '../components/ui/EmptyState';
import { ErrorState } from '../components/ui/ErrorState';
import { Skeleton } from '../components/ui/Skeleton';
import { StatCard } from '../components/ui/StatCard';

export default function ArchitectureAdvisor() {
  const [items, setItems] = useState<ArchitectureRecommendation[] | null>(null);
  const [operation, setOperation] = useState<Reconfiguration | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(false);
  const [optimizationGoal, setOptimizationGoal] = useState<OptimizationGoal>('balanced');
  const [targetEngine, setTargetEngine] = useState('');
  const [overrideText, setOverrideText] = useState('{}');
  const load = async () => {
    try { setError(false); setItems(await listRecommendations()); } catch { setError(true); }
  };
  useEffect(() => { void load(); }, []);

  const refreshOperation = async () => {
    if (operation) setOperation(await getReconfiguration(operation.operation_id));
  };

  const runAction = async (action: () => Promise<unknown>, successMessage: string) => {
    setBusy(true);
    try {
      await action();
      await refreshOperation();
      toast.success(successMessage);
    } catch (actionError) {
      toast.error(actionError instanceof Error ? actionError.message : 'Safe reconfiguration action failed');
    } finally {
      setBusy(false);
    }
  };

  if (!items && !error) return <div className="space-y-4"><Skeleton className="h-10 w-72" /><Skeleton className="h-64 w-full" /></div>;
  if (error) return <ErrorState title="Architecture Advisor is unavailable" description="The backend could not load persisted recommendations." onRetry={() => void load()} />;
  if (!items?.length) return <EmptyState title="No recommendations yet" description="Run a correctness-gated benchmark and create a recommendation from its verified evidence." />;

  const item = items[0];
  const measuredEngines = Array.from(new Set([item.selected_engine, ...(item.result.supporting_benchmark_measurements ?? []).map((measurement) => typeof measurement.engine === 'string' ? measurement.engine : null)].filter((engine): engine is string => Boolean(engine))));
  const result = item.result;
  const recommended = result.recommended_architecture;
  const recalculate = async () => {
    setBusy(true);
    try {
      await createRecommendation({ workload_id: item.workload_id, benchmark_campaign_id: item.benchmark_campaign_id, optimization_goal: optimizationGoal });
      await load();
      toast.success(`Recommendation recalculated for ${optimizationGoal.replace(/_/g, ' ')}`);
    } catch (actionError) {
      toast.error(actionError instanceof Error ? actionError.message : 'Could not recalculate recommendation');
    } finally {
      setBusy(false);
    }
  };
  const propose = async () => {
    setBusy(true);
    try {
      let overrides: Record<string, unknown>;
      try { overrides = JSON.parse(overrideText) as Record<string, unknown>; } catch { throw new Error('Resource overrides must be valid JSON'); }
      if (!overrides || Array.isArray(overrides) || typeof overrides !== 'object') throw new Error('Resource overrides must be a JSON object');
      setOperation(await proposeReconfiguration(item.recommendation_id, { current_engine: 'spark', target_engine: targetEngine || undefined, overrides }));
      toast.success('Safe reconfiguration proposal created');
    } catch (actionError) {
      toast.error(actionError instanceof Error ? actionError.message : 'Could not create proposal');
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className="space-y-6" data-testid="architecture-advisor-page">
      <div className="flex items-start justify-between gap-4"><div><p className="text-xs uppercase tracking-widest text-brand-light font-semibold">Architecture Advisor</p><h1 className="text-2xl font-bold text-slate-100 mt-1">Evidence-backed engine selection</h1><p className="text-sm text-slate-400 mt-2 max-w-3xl">Recommendations are scoped to a workload and never turn missing measurements into performance predictions.</p></div><button type="button" className="rounded-md border border-surface-border p-2 text-slate-400 hover:text-slate-100" onClick={() => void load()} aria-label="Refresh recommendations"><RefreshCwIcon className="h-4 w-4" /></button></div>
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4"><StatCard label="Decision" value={item.status} sub={item.optimization_goal.replace(/_/g, ' ')} accent={item.status === 'RECOMMENDED' ? 'success' : 'warning'} /><StatCard label="Selected engine" value={item.selected_engine ?? 'Not established'} sub={result.confidence ?? 'insufficient evidence'} accent={item.selected_engine ? 'brand' : 'neutral'} /><StatCard label="Benchmark evidence" value={result.supporting_benchmark_measurements?.length ?? 0} sub="correct measured engines" accent="neutral" /></div>
      <Card><CardHeader><CardTitle>Recommendation</CardTitle>{item.status === 'RECOMMENDED' ? <ShieldCheckIcon className="h-5 w-5 text-status-success" /> : <LightbulbIcon className="h-5 w-5 text-status-warning" />}</CardHeader><div className="space-y-4">{recommended ? <div className="space-y-2 text-sm"><p className="text-slate-200">Use <span className="font-semibold text-brand-light">{recommended.engine}</span> for this workload.</p><p className="text-slate-400">The selected resource configuration is the one captured by the measured campaign; no unmeasured resource estimate was substituted.</p></div> : <p className="text-sm text-status-warning">INSUFFICIENT_BENCHMARK_EVIDENCE — execute a compatible benchmark campaign before deployment.</p>}<div className="grid grid-cols-1 gap-3 md:grid-cols-[1fr_auto]"><select value={optimizationGoal} onChange={(event) => setOptimizationGoal(event.target.value as OptimizationGoal)} className="rounded-md border border-surface-border bg-surface-base px-3 py-2 text-sm text-slate-200" aria-label="Optimization objective"><option value="balanced">Balanced</option><option value="execution_time">Lowest execution time</option><option value="throughput">Highest throughput</option><option value="latency">Lowest latency</option><option value="resource_usage">Lowest resource usage</option><option value="reliability">Reliability</option></select><Button disabled={busy} onClick={() => void recalculate()}>Recalculate from evidence</Button></div><p className="text-xs text-slate-500">Changing the objective creates a new persisted recommendation; it does not mutate runtime configuration.</p></div></Card>
      {recommended && <Card><CardHeader><CardTitle>Safe reconfiguration</CardTitle><ShieldCheckIcon className="h-5 w-5 text-status-success" /></CardHeader><div className="space-y-3 text-sm"><p className="text-slate-400">Proposal, preflight, approval, isolated verification, and rollback are separate auditable actions. Production routing is not changed by this workflow.</p>{operation ? <><div className="flex flex-wrap items-center gap-3"><span className="rounded-full bg-surface-base px-3 py-1 text-xs uppercase tracking-wide text-slate-300">{operation.state}</span><span className="text-slate-500">target: {operation.target_engine}</span></div>{operation.error_message && <p className="text-status-error">{operation.error_message}</p>}<div className="flex flex-wrap gap-2">{operation.state === 'proposed' && <Button disabled={busy} onClick={() => void runAction(() => preflightReconfiguration(operation.operation_id), 'Preflight completed')}>Run preflight</Button>}{operation.state === 'preflight_passed' && <Button disabled={busy} onClick={() => void runAction(() => approveReconfiguration(operation.operation_id), 'Explicit approval recorded')}>Approve</Button>}{operation.state === 'approved' && <Button disabled={busy} onClick={() => void runAction(() => executeReconfiguration(operation.operation_id), 'Isolated verification queued')}>Execute isolated verification</Button>}{operation.state === 'executing' && <Button disabled={busy} onClick={() => void refreshOperation()}>Refresh status</Button>}{operation.state === 'succeeded' && <Button variant="ghost" disabled={busy} onClick={() => void runAction(() => rollbackReconfiguration(operation.operation_id), 'Rollback boundary recorded')}>Record rollback</Button>}{['failed', 'blocked', 'rolled_back'].includes(operation.state) && <Button variant="ghost" disabled={busy} onClick={() => void refreshOperation()}>Refresh evidence</Button>}</div><p className="text-xs text-slate-500">Operation ID: {operation.operation_id}</p></> : <div className="space-y-3"><select value={targetEngine} onChange={(event) => setTargetEngine(event.target.value)} className="w-full rounded-md border border-surface-border bg-surface-base px-3 py-2 text-sm text-slate-200" aria-label="Reconfiguration target engine"><option value="">Use recommended engine ({item.selected_engine ?? 'none'})</option>{measuredEngines.map((engine) => <option key={engine} value={engine}>{engine} · measured evidence</option>)}</select><textarea value={overrideText} onChange={(event) => setOverrideText(event.target.value)} className="min-h-20 w-full rounded-md border border-surface-border bg-surface-base px-3 py-2 font-mono text-xs text-slate-200" aria-label="Resource overrides" spellCheck={false} /><p className="text-xs text-slate-500">Resource overrides are recorded for preflight. Engine overrides are accepted only when correctness-passed measured evidence exists.</p><Button disabled={busy} onClick={() => void propose()}>Propose safe reconfiguration</Button></div>}</div></Card>}
      <Card><CardHeader><CardTitle>Tradeoffs and provenance</CardTitle></CardHeader><div className="space-y-2">{[...(result.tradeoff_explanation ?? []), ...(result.known_limitations ?? [])].map((line, index) => <p key={`${index}-${line}`} className="rounded-md bg-surface-base px-3 py-2 text-sm text-slate-400">{line}</p>)}</div></Card>
    </div>
  );
}
