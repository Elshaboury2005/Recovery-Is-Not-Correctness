import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { SuccessSummary } from '../components/pipelines/details/SuccessSummary';

describe('Execution success is not integrity evidence', () => {
  it('does not claim verification when no progress evidence is available', () => {
    render(<SuccessSummary progress={null} elapsedMs={1000} onViewOutput={() => undefined} />);
    expect(screen.getByText('Execution completed. Output correctness requires separate validation.')).toBeInTheDocument();
    expect(screen.queryByText(/output verified in HDFS/i)).not.toBeInTheDocument();
  });
});
