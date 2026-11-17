import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { Canvas } from '@react-three/fiber';
import { Html, Line, OrbitControls } from '@react-three/drei';
import { NetworkIcon, RefreshCwIcon } from 'lucide-react';

import { getInfrastructureComparison, getInfrastructureTopology, InfrastructureComparison, InfrastructureNode, InfrastructureTopology } from '../api/infrastructure';
import { listRecommendations, ArchitectureRecommendation } from '../api/recommendations';
import { Card, CardHeader, CardTitle } from '../components/ui/Card';
import { ErrorState } from '../components/ui/ErrorState';
import { Skeleton } from '../components/ui/Skeleton';
import { StatCard } from '../components/ui/StatCard';

const COLORS: Record<string, string> = { kafka: '#fb923c', 'spark-master': '#a855f7', 'spark-worker': '#c084fc', namenode: '#34d399', datanode: '#6ee7b7', postgres: '#38bdf8', 'flink-jobmanager': '#f472b6', 'flink-taskmanager': '#f9a8d4', 'hive-metastore': '#fbbf24', 'hive-server': '#fde68a', supporting: '#94a3b8' };

function NodeMesh({ node, position, onSelect }: { node: InfrastructureNode; position: [number, number, number]; onSelect: () => void }) {
  const color = COLORS[node.role] ?? COLORS.supporting;
  return <group position={position} onClick={onSelect}><mesh><boxGeometry args={[1.2, 0.8, 0.8]} /><meshStandardMaterial color={node.status === 'running' ? color : '#475569'} emissive={node.status === 'running' ? color : '#000000'} emissiveIntensity={0.18} /></mesh><Html center distanceFactor={9}><button type="button" className="w-32 rounded bg-slate-950/90 px-2 py-1 text-[10px] text-slate-100 shadow" onClick={(event) => { event.stopPropagation(); onSelect(); }}>{node.service ?? node.name}<span className="block text-[9px] text-slate-400">{node.status}</span></button></Html></group>;
}

export default function InfrastructureExplorer() {
  const [topology, setTopology] = useState<InfrastructureTopology | null>(null);
  const [comparison, setComparison] = useState<InfrastructureComparison | null>(null);
  const [recommendations, setRecommendations] = useState<ArchitectureRecommendation[]>([]);
  const [recommendationId, setRecommendationId] = useState('');
  const [showPlanned, setShowPlanned] = useState(false);
  const [lastRefreshed, setLastRefreshed] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [search, setSearch] = useState('');
  const [healthFilter, setHealthFilter] = useState<'all' | 'healthy' | 'unavailable'>('all');
  const [error, setError] = useState(false);
  const load = useCallback(async (selectedRecommendationId = recommendationId) => { try { setError(false); const [nextTopology, nextComparison, nextRecommendations] = await Promise.all([getInfrastructureTopology(), getInfrastructureComparison(selectedRecommendationId || undefined), listRecommendations()]); setTopology(nextTopology); setComparison(nextComparison); setRecommendations(nextRecommendations); setLastRefreshed(new Date().toISOString()); } catch { setError(true); } }, [recommendationId]);
  useEffect(() => { void load(); }, [load]);
  useEffect(() => { const timer = window.setInterval(() => void load(), 15000); return () => window.clearInterval(timer); }, [load]);
  const filteredNodes = useMemo(() => {
    const needle = search.trim().toLowerCase();
    return (topology?.nodes ?? []).filter((node) => {
      const matchesSearch = !needle || [node.name, node.service, node.role, node.image].filter(Boolean).some((value) => String(value).toLowerCase().includes(needle));
      const matchesHealth = healthFilter === 'all' || (healthFilter === 'healthy' ? node.status === 'running' && node.health !== 'unhealthy' : node.status !== 'running' || node.health === 'unhealthy');
      return matchesSearch && matchesHealth;
    });
  }, [healthFilter, search, topology]);
  const filteredIds = useMemo(() => new Set(filteredNodes.map((node) => node.id)), [filteredNodes]);
  const filteredEdges = useMemo(() => (topology?.edges ?? []).filter((edge) => filteredIds.has(edge.source) && filteredIds.has(edge.target)), [filteredIds, topology]);
  const positions = useMemo(
    () => new Map(
      filteredNodes.map(
        (node, index) => [
          node.id,
          [((index % 4) - 1.5) * 2.8, (Math.floor(index / 4) - 0.5) * -2.2, 0] as [number, number, number],
        ] as const,
      ),
    ),
    [filteredNodes],
  );
  const selected = filteredNodes.find((node) => node.id === selectedId);
  if (!topology && !error) return <div className="space-y-4"><Skeleton className="h-10 w-72" /><Skeleton className="h-96 w-full" /></div>;
  if (error) return <ErrorState title="Infrastructure topology is unavailable" description="The backend could not discover the owned Compose topology." onRetry={() => void load()} />;
  return <div className="space-y-6" data-testid="infrastructure-explorer-page"><div className="flex items-start justify-between gap-4"><div><p className="text-xs uppercase tracking-widest text-brand-light font-semibold">Infrastructure Explorer</p><h1 className="text-2xl font-bold text-slate-100 mt-1">Explore the deployed platform topology</h1><p className="text-sm text-slate-400 mt-2">Nodes and edges come from the project-labeled Docker deployment; unavailable discovery is never replaced with static system data.</p><p className="mt-1 text-xs text-slate-500">Live refresh polls every 15 seconds{lastRefreshed ? ` · last refreshed ${new Date(lastRefreshed).toLocaleTimeString()}` : ''}</p></div><button type="button" className="rounded-md border border-surface-border p-2 text-slate-400 hover:text-slate-100" onClick={() => void load()} aria-label="Refresh topology"><RefreshCwIcon className="h-4 w-4" /></button></div><div className="grid grid-cols-1 sm:grid-cols-3 gap-4"><StatCard label="Discovery" value={topology?.status ?? 'UNKNOWN'} sub={topology?.project} accent={topology?.status === 'ready' ? 'success' : 'warning'} /><StatCard label="Nodes" value={`${filteredNodes.length}/${topology?.nodes.length ?? 0}`} sub="visible / discovered containers" accent="brand" /><StatCard label="Edges" value={filteredEdges.length} sub="visible shared-network links" accent="neutral" /></div><Card><CardHeader><CardTitle>Planned comparison</CardTitle><NetworkIcon className="h-5 w-5 text-slate-400" /></CardHeader><div className="space-y-3"><div className="grid grid-cols-1 gap-3 md:grid-cols-[1fr_auto]"><select value={recommendationId} onChange={(event) => { setRecommendationId(event.target.value); setShowPlanned(Boolean(event.target.value)); }} className="rounded-md border border-surface-border bg-surface-base px-3 py-2 text-sm text-slate-200" aria-label="Select architecture recommendation"><option value="">No planned recommendation</option>{recommendations.map((item) => <option key={item.recommendation_id} value={item.recommendation_id}>{item.selected_engine ?? 'Not established'} · {item.status} · {item.recommendation_id.slice(0, 8)}</option>)}</select><button type="button" className="rounded-md border border-surface-border px-3 py-2 text-sm text-slate-300" onClick={() => setShowPlanned((value) => !value)} disabled={!comparison?.planned}>{showPlanned ? 'Show deployed' : 'Show planned'}</button></div>{comparison && <div className="rounded-md bg-surface-base p-3 text-sm"><p className="text-slate-200">{showPlanned && comparison.planned ? `Planned target: ${comparison.planned.engine ?? 'not established'}` : `Deployed engines: ${comparison.current.nodes.filter((node) => node.role.includes('spark') || node.role.includes('flink')).map((node) => node.role.includes('spark') ? 'spark' : 'flink').filter((value, index, values) => values.indexOf(value) === index).join(', ') || 'none detected'}`}</p><p className="mt-1 text-xs text-slate-500">{comparison.message}</p>{comparison.changes.map((change) => <p key={change.kind} className="mt-2 text-xs text-slate-400">{change.kind.replace(/_/g, ' ')}: {change.status} · evidence-based: {change.evidence_based ? 'yes' : 'no'}</p>)}</div>}</div></Card><Card><CardHeader><CardTitle>Topology filters</CardTitle><NetworkIcon className="h-5 w-5 text-slate-400" /></CardHeader><div className="grid grid-cols-1 gap-3 md:grid-cols-[1fr_auto]"><input value={search} onChange={(event) => setSearch(event.target.value)} className="rounded-md border border-surface-border bg-surface-base px-3 py-2 text-sm text-slate-200" placeholder="Search services, roles, or images" aria-label="Search infrastructure services" /><select value={healthFilter} onChange={(event) => setHealthFilter(event.target.value as typeof healthFilter)} className="rounded-md border border-surface-border bg-surface-base px-3 py-2 text-sm text-slate-200" aria-label="Filter infrastructure health"><option value="all">All discovered nodes</option><option value="healthy">Running and healthy</option><option value="unavailable">Unavailable or stopped</option></select></div></Card><Card><CardHeader><CardTitle>{showPlanned ? 'Planned architecture' : '3D topology'}</CardTitle><span className="text-xs text-slate-500">{showPlanned ? 'Recommendation view · no runtime mutation' : 'Deployed view · drag to rotate · scroll to zoom'}</span></CardHeader>{showPlanned && comparison?.planned ? <div className="space-y-3 p-4 text-sm"><p className="text-slate-200">Engine: <span className="font-semibold text-brand-light">{comparison.planned.engine ?? 'Not established'}</span></p><p className="text-slate-400">Confidence: {comparison.planned.confidence ?? 'not established'} · objective: {comparison.planned.optimization_goal ?? '—'}</p><pre className="overflow-auto rounded-md bg-slate-950 p-3 text-xs text-slate-400">{JSON.stringify(comparison.planned.architecture, null, 2)}</pre></div> : <div className="h-[480px] overflow-hidden rounded-lg bg-slate-950"><Canvas fallback={<div className="p-6 text-sm text-slate-400">WebGL is unavailable. Use the node inspection list below.</div>} camera={{ position: [0, 0, 12], fov: 45 }}><ambientLight intensity={0.8} /><pointLight position={[5, 5, 8]} intensity={20} /><OrbitControls enablePan enableZoom /><gridHelper args={[20, 20, '#334155', '#172033']} />{filteredEdges.map((edge) => { const from = positions.get(edge.source); const to = positions.get(edge.target); return from && to ? <Line key={`${edge.source}-${edge.target}-${edge.network}`} points={[from, to]} color="#475569" lineWidth={1} /> : null; })}{filteredNodes.map((node) => <NodeMesh key={node.id} node={node} position={positions.get(node.id) ?? [0, 0, 0]} onSelect={() => setSelectedId(node.id)} />)}</Canvas></div>}</Card>{selected && !showPlanned && <Card><CardHeader><CardTitle>{selected.service ?? selected.name}</CardTitle><span className="text-xs uppercase text-slate-400">{selected.health ?? selected.status}</span></CardHeader><div className="grid grid-cols-1 md:grid-cols-2 gap-2 text-sm"><p className="text-slate-400">Image <span className="float-right text-slate-200">{selected.image ?? '—'}</span></p><p className="text-slate-400">Networks <span className="float-right text-slate-200">{selected.networks.join(', ') || '—'}</span></p><p className="text-slate-400">Ports <span className="float-right text-slate-200">{selected.ports.join(', ') || '—'}</span></p><p className="text-slate-400">Role <span className="float-right text-slate-200">{selected.role}</span></p></div></Card>}</div>;
}
