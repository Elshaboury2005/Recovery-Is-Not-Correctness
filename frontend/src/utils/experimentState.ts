import type { Experiment } from '../types/experiment';

// Saved configurations have pending status but no run. Pending runs with an
// ID are queued work and must continue to block conflicting fault injection.
export const hasActiveRun = (experiment: Experiment): boolean =>
  experiment.status === 'running' ||
  (experiment.status === 'pending' && experiment.latestRunId != null);
