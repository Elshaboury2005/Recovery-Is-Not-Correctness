import React, { useEffect, useState } from 'react';
import { DatabaseZapIcon, PlayIcon, RefreshCwIcon } from 'lucide-react';
import { toast } from 'sonner';

import { getHiveHealth, listHiveQueries, listHiveTables, registerHiveTable, runHiveQuery, HiveHealth, HiveQuery, HiveTable } from '../api/hive';
import { Button } from '../components/ui/Button';
import { Card, CardHeader, CardTitle } from '../components/ui/Card';
import { EmptyState } from '../components/ui/EmptyState';
import { ErrorState } from '../components/ui/ErrorState';
import { Skeleton } from '../components/ui/Skeleton';
import { StatCard } from '../components/ui/StatCard';

const DEFAULT_SQL = 'SHOW TABLES';

export default function HiveExplorer() {
  const [health, setHealth] = useState<HiveHealth | null>(null);
  const [history, setHistory] = useState<HiveQuery[] | null>(null);
  const [tables, setTables] = useState<HiveTable[] | null>(null);
  const [sql, setSql] = useState(DEFAULT_SQL);
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);
  const [registering, setRegistering] = useState(false);
  const [tableName, setTableName] = useState('chaosflow_output');
  const [tableLocation, setTableLocation] = useState('hdfs://namenode:9000/data/chaosflow-output');
  const [tableColumns, setTableColumns] = useState('id:BIGINT, value:STRING');
  const [error, setError] = useState(false);
  const load = async () => {
    try {
      setError(false);
      const [nextHealth, nextHistory] = await Promise.all([getHiveHealth(), listHiveQueries()]);
      setHealth(nextHealth); setHistory(nextHistory);
      try { setTables(await listHiveTables()); } catch { setTables(null); }
    } catch { setError(true); } finally { setLoading(false); }
  };
  useEffect(() => { void load(); }, []);
  const submit = async () => {
    setRunning(true);
    try { await runHiveQuery({ sql, max_rows: 500 }); toast.success('Hive query recorded'); await load(); } catch (requestError) { toast.error(requestError instanceof Error ? requestError.message : 'Hive query failed'); } finally { setRunning(false); }
  };
  const register = async () => {
    const columns = tableColumns.split(',').map((entry) => entry.trim()).filter(Boolean).map((entry) => {
      const [name, ...typeParts] = entry.split(':');
      return { name: name.trim(), hive_type: typeParts.join(':').trim() };
    });
    setRegistering(true);
    try { await registerHiveTable({ table_name: tableName.trim(), location: tableLocation.trim(), columns }); toast.success('Hive table registration recorded'); await load(); } catch (requestError) { toast.error(requestError instanceof Error ? requestError.message : 'Hive table registration failed'); } finally { setRegistering(false); }
  };
  if (loading) return <div className="space-y-4"><Skeleton className="h-10 w-72" /><Skeleton className="h-64 w-full" /></div>;
  if (error && !health) return <ErrorState title="Hive Explorer is unavailable" description="The backend could not load Hive health or query history." onRetry={() => void load()} />;
  const latest = history?.[0];
  return (
    <div className="space-y-6" data-testid="hive-explorer-page">
      <div className="flex items-start justify-between gap-4"><div><p className="text-xs uppercase tracking-widest text-brand-light font-semibold">Hive SQL Explorer</p><h1 className="text-2xl font-bold text-slate-100 mt-1">Inspect analytical metadata safely</h1><p className="text-sm text-slate-400 mt-2 max-w-3xl">Only read-only SQL is accepted. Every attempt is persisted with its runtime status and error evidence.</p></div><button type="button" className="rounded-md border border-surface-border p-2 text-slate-400 hover:text-slate-100" onClick={() => void load()} aria-label="Refresh Hive"><RefreshCwIcon className="h-4 w-4" /></button></div>
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4"><StatCard label="Hive status" value={health?.status ?? 'UNKNOWN'} sub={health?.error ?? 'Health probe'} accent={health?.connected ? 'success' : 'warning'} /><StatCard label="Query history" value={history?.length ?? 0} sub="persisted attempts" accent="neutral" /><StatCard label="Latest result" value={latest?.status ?? '—'} sub={latest?.error_message ?? (latest ? `${latest.row_count ?? 0} rows` : 'No queries yet')} accent={latest?.status === 'succeeded' ? 'success' : 'neutral'} /></div>
      <Card><CardHeader><CardTitle>Read-only query</CardTitle><DatabaseZapIcon className="h-5 w-5 text-slate-400" /></CardHeader><textarea value={sql} onChange={(event) => setSql(event.target.value)} className="min-h-32 w-full rounded-md border border-surface-border bg-surface-base p-3 font-mono text-sm text-slate-200" aria-label="Hive SQL" /><div className="mt-3 flex justify-end"><Button disabled={!sql.trim() || running} onClick={() => void submit()}><PlayIcon className="h-4 w-4" />{running ? 'Running…' : 'Run query'}</Button></div></Card>
      <Card><CardHeader><CardTitle>Registered tables</CardTitle></CardHeader>{tables?.length ? <div className="grid grid-cols-1 gap-2 md:grid-cols-2">{tables.map((table) => <button key={table.table_name} type="button" className="rounded-md border border-surface-border p-3 text-left text-sm text-slate-200 hover:border-brand-light" onClick={() => setSql(`DESCRIBE ${table.table_name}`)}>{table.table_name}</button>)}</div> : <EmptyState title="No table metadata available" description={health?.connected ? 'Hive returned no registered tables.' : 'Start HiveServer2 and install the backend client driver to browse metadata.'} />}</Card>
      <Card><CardHeader><CardTitle>Register HDFS Parquet output</CardTitle></CardHeader><p className="text-sm text-slate-400">Use the explicit registration boundary for a supported HDFS Parquet directory. Arbitrary DDL remains unavailable in the SQL editor.</p><div className="mt-4 grid gap-3 md:grid-cols-2"><input value={tableName} onChange={(event) => setTableName(event.target.value)} className="rounded-md border border-surface-border bg-surface-base p-2 text-sm text-slate-200" aria-label="Hive table name" placeholder="table_name" /><input value={tableLocation} onChange={(event) => setTableLocation(event.target.value)} className="rounded-md border border-surface-border bg-surface-base p-2 text-sm text-slate-200" aria-label="HDFS Parquet location" placeholder="hdfs://namenode:9000/path" /><input value={tableColumns} onChange={(event) => setTableColumns(event.target.value)} className="rounded-md border border-surface-border bg-surface-base p-2 text-sm text-slate-200 md:col-span-2" aria-label="Hive columns" placeholder="id:BIGINT, value:STRING" /></div><div className="mt-3 flex justify-end"><Button disabled={!tableName.trim() || !tableLocation.trim() || !tableColumns.trim() || registering} onClick={() => void register()}>{registering ? 'Registering…' : 'Register output'}</Button></div></Card>
      <Card><CardHeader><CardTitle>Query history</CardTitle></CardHeader>{history?.length ? <div className="space-y-2">{history.map((item) => <div key={item.query_id} className="rounded-md border border-surface-border p-3"><div className="flex justify-between gap-3 text-sm"><code className="text-slate-200 truncate">{item.sql}</code><span className={item.status === 'succeeded' ? 'text-status-success' : 'text-status-warning'}>{item.status}</span></div><p className="text-xs text-slate-500 mt-2">{item.error_message ?? `${item.row_count ?? 0} rows · ${item.duration_ms ?? '—'} ms`}</p></div>)}</div> : <EmptyState title="No query history" description="Run SHOW TABLES or a SELECT statement to create a persisted record." />}</Card>
    </div>
  );
}
