import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { RecoveryEvidenceTable } from '../components/reports/RecoveryEvidenceTable';

describe('Recovery evidence display', () => {
  it('keeps real zero distinct from missing endpoints and interval observations', () => {
    render(<RecoveryEvidenceTable evidence={{ version: '1', metrics: {
      fault_dispatch_latency: { status: 'exact', lower_seconds: 0, upper_seconds: 0 },
      infrastructure_recovery: { status: 'unobservable', lower_seconds: null, upper_seconds: null },
      service_readiness_recovery: { status: 'interval', lower_seconds: 2.1, upper_seconds: 2.8 },
    } }} />);
    expect(screen.getByText('0.000 s')).toBeInTheDocument();
    expect(screen.getByText('Not observable')).toBeInTheDocument();
    expect(screen.getByText('2.100–2.800 s')).toBeInTheDocument();
  });

  it('does not turn censored recovery into a completed recovery time', () => {
    render(<RecoveryEvidenceTable evidence={{ version: '1', metrics: {
      service_readiness_recovery: { status: 'right_censored', lower_seconds: 60, upper_seconds: null,
        reason: 'Observation ended before service readiness' },
    } }} />);
    expect(screen.getByText('At least 60.000 s; endpoint not observed')).toBeInTheDocument();
    expect(screen.getByText('Observation ended before service readiness')).toBeInTheDocument();
  });

  it('does not display reversed or nonfinite intervals as recovery measurements', () => {
    render(<RecoveryEvidenceTable evidence={{ version: '1', metrics: {
      service_readiness_recovery: { status: 'interval', lower_seconds: 3, upper_seconds: 2 },
      infrastructure_recovery: { status: 'exact', lower_seconds: Infinity, upper_seconds: Infinity },
    } }} />);
    expect(screen.getAllByText('Not observable')).toHaveLength(2);
  });
});
