import React, { useEffect, useState } from 'react';
import { RefreshCwIcon, ShieldCheckIcon } from 'lucide-react';
import { toast } from 'sonner';

import {
  approveReconfiguration,
  executeReconfiguration,
  getReconfiguration,
  listReconfigurations,
  preflightReconfiguration,
  Reconfiguration,
  rollbackReconfiguration,
} from '../api/reconfigurations';
import { Button } from '../components/ui/Button';
import { Card, CardHeader, CardTitle } from '../components/ui/Card';
import { EmptyState } from '../components/ui/EmptyState';
import { ErrorState } from '../components/ui/ErrorState';
import { Skeleton } from '../components/ui/Skeleton';
import { StatCard } from '../components/ui/StatCard';

function actionFor(operation: Reconfiguration): { label: string; run: () => Promise<unknown> } | null {
  if (operation.state === 'proposed') return { label: 'Run preflight', run: () => preflightReconfiguration(operation.operation_id) };
  if (operation.state === 'preflight_passed') return { label: 'Approve', run: () => approveReconfiguration(operation.operation_id) };
  if (operation.state === 'approved') return { label: 'Execute isolated verification', run: () => executeReconfiguration(operation.operation_id) };
  if (operation.state === 'succeeded') return { label: 'Record rollback', run: () => rollbackReconfiguration(operation.operation_id) };
  return null;
}

export default function ReconfigurationCenter() {
  const [items, setItems] = useState<Reconfiguration[] | null>(null);
  const [error, setError] = useState(false);
  const [busyId, setBusyId] = useState<string | null>(null);

  const load = async () => {
    try {
      setError(false);
      setItems(await listReconfigurations());
    } catch {
      setError(true);
    }
  };

  useEffect(() => { void load(); }, []);

  const refresh = async (operationId: string) => {
    const updated = await getReconfiguration(operationId);
    setItems((current) => current?.map((item) => item.operation_id === operationId ? updated : item) ?? [updated]);
  };

  const run = async (operation: Reconfiguration) => {
    const action = actionFor(operation);
    if (!action) return;
    setBusyId(operation.operation_id);
    try {
      await action.run();
      await refresh(operation.operation_id);
      toast.success(`${action.label} completed`);
    } catch (actionError) {
      toast.error(actionError instanceof Error ? actionError.message : 'Reconfiguration action failed');
    } finally {
      setBusyId(null);
    }
  };

  if (!items && !error) return <div className="space-y-4"><Skeleton className="h-10 w-72" /><Skeleton className="h-64 w-full" /></div>;
  if (error) return <ErrorState title="Reconfiguration Center is unavailable" description="The backend could not load the durable operation history." onRetry={() => void load()} />;

  const active = items?.filter((item) => ['proposed', 'preflight_passed', 'approved', 'executing'].includes(item.state)).length ?? 0;
  const verified = items?.filter((item) => item.state === 'succeeded').length ?? 0;
  return (
    <div className="space-y-6" data-testid="reconfiguration-center-page">
      <div className="flex items-start justify-between gap-4"><div><p className="text-xs uppercase tracking-widest text-brand-light font-semibold">Reconfiguration Center</p><h1 className="text-2xl font-bold text-slate-100 mt-1">Apply architecture changes safely</h1><p className="text-sm text-slate-400 mt-2 max-w-3xl">Every operation requires explicit preflight and approval. Execution uses an isolated verification namespace; production routing is never changed automatically.</p></div><Button variant="ghost" onClick={() => void load()}><RefreshCwIcon className="h-4 w-4" />Refresh</Button></div>
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4"><StatCard label="Operations" value={items?.length ?? 0} sub="durable history" accent="neutral" /><StatCard label="Active" value={active} sub="awaiting or verifying" accent="brand" /><StatCard label="Verified" value={verified} sub="correctness-passed isolated runs" accent="success" /></div>
      {!items?.length ? <EmptyState title="No reconfiguration operations" description="Create a proposal from the Architecture Advisor after a correctness-gated recommendation is available." /> : <div className="space-y-4">{items.map((operation) => { const action = actionFor(operation); const result = operation.execution_result; const correctness = result.correctness as { status?: string } | undefined; const outputPath = typeof result.output_path === 'string' ? result.output_path : null; return <Card key={operation.operation_id}><CardHeader><CardTitle>{operation.target_engine} architecture operation</CardTitle><span className="rounded-full bg-surface-base px-3 py-1 text-xs uppercase tracking-wide text-slate-300">{operation.state}</span></CardHeader><div className="space-y-3 text-sm"><div className="grid grid-cols-1 gap-2 md:grid-cols-3"><p className="text-slate-400">Previous <span className="float-right text-slate-200">{operation.current_engine ?? 'unknown'}</span></p><p className="text-slate-400">Target <span className="float-right text-slate-200">{operation.target_engine}</span></p><p className="text-slate-400">Correctness <span className="float-right text-slate-200">{correctness?.status ?? 'not measured'}</span></p></div>{operation.error_message && <p className="text-status-error">{operation.error_message}</p>}{outputPath && <p className="break-all rounded-md bg-surface-base px-3 py-2 text-xs text-slate-400">Evidence output: {outputPath}</p>}<div className="flex flex-wrap gap-2">{action && <Button disabled={busyId === operation.operation_id} onClick={() => void run(operation)}>{action.label}</Button>}{operation.state === 'executing' && <Button variant="ghost" disabled={busyId === operation.operation_id} onClick={() => void refresh(operation.operation_id)}>Refresh status</Button>}</div><details><summary className="cursor-pointer text-xs text-slate-500">Audit history ({operation.audit_events.length})</summary><div className="mt-2 space-y-1">{operation.audit_events.map((event, index) => <p key={`${operation.operation_id}-${index}`} className="text-xs text-slate-500">{String(event.action ?? 'event')} · {String(event.detail ?? '')}</p>)}</div></details></div></Card>; })}</div>}
      <Card><CardHeader><CardTitle>Safety contract</CardTitle><ShieldCheckIcon className="h-5 w-5 text-status-success" /></CardHeader><p className="text-sm text-slate-400">Rollback is only offered after an independently verified isolated run. Evidence is retained, and unsupported cross-engine state migration is never implied.</p></Card>
    </div>
  );
}
