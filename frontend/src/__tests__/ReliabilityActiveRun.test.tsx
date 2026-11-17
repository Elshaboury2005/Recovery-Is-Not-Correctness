import { describe, expect, it } from 'vitest';
import { hasActiveRun } from '../utils/experimentState';
import type { Experiment } from '../types/experiment';

describe('Reliability active-run identity', () => {
  const experiment: Experiment = { id: 'saved', name: 'saved', target: 'kafka',
    faultType: 'container_stop', status: 'pending', createdAt: '', latestRunId: null };
  it('does not block injection for a never-run pending configuration', () => {
    expect(hasActiveRun(experiment)).toBe(false);
  });
  it('blocks injection for a queued run with an actual run ID', () => {
    expect(hasActiveRun({ ...experiment, latestRunId: 'queued-run' })).toBe(true);
  });
  it('blocks running experiments', () => {
    expect(hasActiveRun({ ...experiment, status: 'running' })).toBe(true);
  });
  it.each(['succeeded', 'failed', 'cancelled'] as const)('does not block terminal %s runs', status => {
    expect(hasActiveRun({ ...experiment, status, latestRunId: 'old-run' })).toBe(false);
  });
});
