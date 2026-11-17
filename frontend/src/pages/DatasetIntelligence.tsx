import React, { useEffect, useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { DatabaseIcon, FileSearchIcon, RefreshCwIcon, SparklesIcon } from 'lucide-react';
import { toast } from 'sonner';

import {
  createDatasetProfile,
  discoverDatasets,
  getDatasetProfile,
  listDatasetProfiles,
  DatasetProfile,
} from '../api/datasets';
import { listWorkloads, WorkloadDefinition } from '../api/workloads';
import { Card, CardHeader, CardTitle } from '../components/ui/Card';
import { Button } from '../components/ui/Button';
import { EmptyState } from '../components/ui/EmptyState';
import { ErrorState } from '../components/ui/ErrorState';
import { ProgressBar } from '../components/ui/ProgressBar';
import { Skeleton } from '../components/ui/Skeleton';
import { StatCard } from '../components/ui/StatCard';

function formatBytes(value: number): string {
  if (value < 1024) return `${value} B`;
  if (value < 1024 ** 2) return `${(value / 1024).toFixed(1)} KB`;
  if (value < 1024 ** 3) return `${(value / 1024 ** 2).toFixed(1)} MB`;
  return `${(value / 1024 ** 3).toFixed(1)} GB`;
}

export default function DatasetIntelligence() {
  const queryClient = useQueryClient();
  const [selectedSource, setSelectedSource] = useState('');
  const [activeProfileId, setActiveProfileId] = useState<string | null>(null);

  const datasetsQuery = useQuery({ queryKey: ['datasets'], queryFn: discoverDatasets });
  const profilesQuery = useQuery({ queryKey: ['datasetProfiles'], queryFn: listDatasetProfiles });
  const workloadsQuery = useQuery({ queryKey: ['workloads'], queryFn: listWorkloads });
  const profileQuery = useQuery({
    queryKey: ['datasetProfile', activeProfileId],
    queryFn: () => getDatasetProfile(activeProfileId as string),
    enabled: Boolean(activeProfileId),
  });
  const { data: profile, refetch: refetchProfile } = profileQuery;

  useEffect(() => {
    if (!activeProfileId || !profile || ['succeeded', 'failed'].includes(profile.status)) return;
    const timer = window.setTimeout(() => refetchProfile(), 1000);
    return () => window.clearTimeout(timer);
  }, [activeProfileId, profile, refetchProfile]);

  const createMutation = useMutation({
    mutationFn: () => createDatasetProfile({ source_uri: selectedSource, sample_rows: 10_000 }),
    onSuccess: (job) => {
      setActiveProfileId(job.profile_id);
      void queryClient.invalidateQueries({ queryKey: ['datasetProfiles'] });
      toast.success('Dataset profiling started');
    },
    onError: (error) => toast.error(error instanceof Error ? error.message : 'Could not start profiling'),
  });

  const selectedDataset = useMemo(
    () => datasetsQuery.data?.find((dataset) => dataset.source_uri === selectedSource),
    [datasetsQuery.data, selectedSource]
  );

  if (datasetsQuery.isLoading || profilesQuery.isLoading || workloadsQuery.isLoading) {
    return <div className="space-y-4"><Skeleton className="h-10 w-72" /><Skeleton className="h-64 w-full" /></div>;
  }
  if (datasetsQuery.isError || profilesQuery.isError || workloadsQuery.isError) {
    return <ErrorState title="Dataset intelligence is unavailable" description="The backend could not load dataset discovery, profile history, or workload classifications." onRetry={() => { void datasetsQuery.refetch(); void profilesQuery.refetch(); void workloadsQuery.refetch(); }} />;
  }

  const result = profile?.result;
  return (
    <div className="space-y-6" data-testid="dataset-intelligence-page">
      <div>
        <p className="text-xs uppercase tracking-widest text-brand-light font-semibold">Dataset Intelligence</p>
        <h1 className="text-2xl font-bold text-slate-100 mt-1">Profile data before you choose an engine</h1>
        <p className="text-sm text-slate-400 mt-2 max-w-3xl">Every statistic below comes from the profiling service and is labeled as exact, sampled, or estimated.</p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Start a profile</CardTitle>
          <DatabaseIcon className="h-5 w-5 text-brand-light" />
        </CardHeader>
        <div className="flex flex-col md:flex-row gap-3">
          <select
            className="flex-1 rounded-md border border-surface-border bg-surface-base px-3 py-2 text-sm text-slate-200"
            value={selectedSource}
            onChange={(event) => setSelectedSource(event.target.value)}
            aria-label="Dataset"
          >
            <option value="">Select a discovered dataset</option>
            {datasetsQuery.data?.map((dataset) => <option key={dataset.source_uri} value={dataset.source_uri}>{dataset.name} · {dataset.format} · {formatBytes(dataset.size_bytes)}</option>)}
          </select>
          <Button disabled={!selectedSource || createMutation.isPending} onClick={() => createMutation.mutate()}>
            <SparklesIcon className="h-4 w-4" />
            {createMutation.isPending ? 'Starting…' : 'Profile dataset'}
          </Button>
        </div>
        {selectedDataset && <p className="text-xs text-slate-500 mt-3">Source: {selectedDataset.source_uri}</p>}
      </Card>

      {profile && (
        <Card>
          <CardHeader>
            <CardTitle>Profile job · {profile.dataset_name} v{profile.profile_version}</CardTitle>
            <span className={profile.status === 'succeeded' ? 'text-status-success text-xs uppercase' : profile.status === 'failed' ? 'text-status-error text-xs uppercase' : 'text-status-warning text-xs uppercase'}>{profile.status}</span>
          </CardHeader>
          <ProgressBar value={profile.progress} label={`${profile.progress}% complete`} />
          {profile.error_message && <p className="text-sm text-status-error mt-3">{profile.error_message}</p>}
        </Card>
      )}

      {result && (
        <>
          <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-4">
            <StatCard label="Records" value={result.record_count.value.toLocaleString()} sub={result.record_count.scope} accent="brand" />
            <StatCard label="Columns" value={result.column_count.value} sub="exact schema count" accent="neutral" />
            <StatCard label="Duplicate rows" value={result.duplicate_characteristics.duplicate_rows} sub={result.duplicate_characteristics.scope} accent={result.duplicate_characteristics.duplicate_rows ? 'warning' : 'success'} />
            <StatCard label="Quality issues" value={result.data_quality.quality_issue_count} sub="reported by profiler" accent={result.data_quality.quality_issue_count ? 'warning' : 'success'} />
          </div>
          <Card>
            <CardHeader><CardTitle>Detected schema and quality signals</CardTitle><FileSearchIcon className="h-5 w-5 text-slate-400" /></CardHeader>
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm"><thead className="text-xs uppercase text-slate-500"><tr><th className="py-2 pr-4">Column</th><th className="py-2 pr-4">Type</th><th className="py-2 pr-4">Nulls</th><th className="py-2 pr-4">Distinct</th><th className="py-2">Signal</th></tr></thead><tbody className="divide-y divide-surface-border">{result.columns.map((column) => <tr key={column.name}><td className="py-3 pr-4 font-mono text-slate-200">{column.name}</td><td className="py-3 pr-4 text-slate-400">{column.data_type}</td><td className="py-3 pr-4 text-slate-400">{column.null_percentage}% <span className="text-xs text-slate-600">({column.null_scope})</span></td><td className="py-3 pr-4 text-slate-400">{column.distinct_values} <span className="text-xs text-slate-600">({column.distinct_scope})</span></td><td className="py-3">{column.timestamp_candidate ? <span className="text-status-success">event-time candidate</span> : '—'}</td></tr>)}</tbody></table>
            </div>
          </Card>
        </>
      )}

      <Card>
        <CardHeader><CardTitle>Workload classification history</CardTitle><Button variant="ghost" onClick={() => { void workloadsQuery.refetch(); }}><RefreshCwIcon className="h-4 w-4" />Refresh</Button></CardHeader>
        {workloadsQuery.data?.length ? <div className="space-y-3">{workloadsQuery.data.slice(0, 8).map((workload: WorkloadDefinition) => {
          const classification = workload.classification;
          const compatible = classification.compatible_engines?.filter((engine) => engine.compatible).map((engine) => engine.engine).join(', ') || 'none established';
          return <div key={workload.workload_id} className="rounded-md border border-surface-border p-4"><div className="flex flex-wrap items-center justify-between gap-2"><div><p className="text-sm font-semibold text-slate-200">{workload.name}</p><p className="text-xs text-slate-500">{new Date(workload.created_at).toLocaleString()}</p></div><span className="rounded-full bg-surface-base px-3 py-1 text-xs text-brand-light">{compatible}</span></div><div className="mt-3 flex flex-wrap gap-2">{(classification.categories ?? []).map((category) => <span key={category} className="rounded bg-surface-base px-2 py-1 text-xs text-slate-400">{category.replace(/_/g, ' ')}</span>)}</div><p className="mt-3 text-xs text-slate-400">Required capabilities: {classification.required_capabilities?.join(', ') || 'none'}.</p>{classification.bottlenecks?.length ? <p className="mt-1 text-xs text-status-warning">Bottlenecks: {classification.bottlenecks.join('; ')}</p> : null}<p className="mt-1 text-xs text-slate-500">Method: {classification.explanation?.method ?? 'deterministic classification'}</p></div>;
        })}</div> : <EmptyState title="No workload classifications yet" description="Classify a profiled pipeline through the workload API to make its engine compatibility and bottlenecks visible here." />}
      </Card>

      <Card>
        <CardHeader><CardTitle>Profile history</CardTitle><Button variant="ghost" onClick={() => { void profilesQuery.refetch(); }}><RefreshCwIcon className="h-4 w-4" />Refresh</Button></CardHeader>
        {profilesQuery.data?.length ? <div className="space-y-2">{profilesQuery.data.map((item: DatasetProfile) => <button key={item.profile_id} type="button" className="w-full flex items-center justify-between rounded-md border border-surface-border px-4 py-3 text-left hover:border-brand/50" onClick={() => setActiveProfileId(item.profile_id)}><span><span className="block text-sm text-slate-200">{item.dataset_name} v{item.profile_version}</span><span className="block text-xs text-slate-500">{item.source_uri}</span></span><span className="text-xs uppercase text-slate-400">{item.status}</span></button>)}</div> : <EmptyState title="No profiles yet" description="Select a dataset above to create the first persisted profile." />}
      </Card>
    </div>
  );
}
