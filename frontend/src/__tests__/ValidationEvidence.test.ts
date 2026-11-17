import { describe, expect, it } from 'vitest';
import { mapToExperimentDetail } from '../api/experiments';
import { mapToReportDetail, mapToReportListItem } from '../api/reports';
import { criterionLabels } from '../lib/reliability';

describe('validation evidence through API mapping and criteria', () => {
  it.each([undefined, null, '', 'invalid', false, Number.NaN])('keeps unmeasured counts unknown: %s', (value) => {
    const results = { dataLoss: value, duplicates: value, expectedRecords: value, processedRecords: value };
    const detail = mapToExperimentDetail({ results });
    expect(detail.results.dataLoss).toBeNull();
    expect(detail.results.duplicates).toBeNull();
    expect(detail.results.expectedRecords).toBeNull();
    expect(detail.results.processedRecords).toBeNull();
    expect(mapToReportListItem({ dataLoss: value }).dataLoss).toBeNull();
    expect(criterionLabels(detail).find(c => c.name === 'Data Loss')?.passed).toBeNull();
  });

  it('preserves observed zero and reads the transformed expected count', () => {
    const detail = mapToExperimentDetail({ results: {
      data_loss: 0, actual_records: 0, expected_records: 0, expected_record_count: 100,
      validation_status: 'PASS',
    } });
    expect(detail.results.dataLoss).toBe(0);
    expect(detail.results.expectedRecords).toBe(0);
    expect(detail.results.processedRecords).toBe(0);
    expect(mapToReportListItem({ data_loss: 0 }).dataLoss).toBe(0);
    expect(criterionLabels(detail).find(c => c.name === 'Output Correctness')?.passed).toBe(true);
  });

  it('does not replace an explicit unknown with an obsolete alias', () => {
    const detail = mapToExperimentDetail({ results: {
      dataLoss: null, data_loss: 0, expectedRecords: null, expected_record_count: 100,
    } });
    expect(detail.results.dataLoss).toBeNull();
    expect(detail.results.expectedRecords).toBeNull();
    expect(mapToReportListItem({ dataLoss: null, data_loss: 0 }).dataLoss).toBeNull();
  });

  it.each(['FAIL', 'UNKNOWN'] as const)('count agreement does not imply correctness: %s', (status) => {
    const detail = mapToReportDetail({ validationStatus: status, validationReason: 'fixture reason',
      results: { dataLoss: 0, expectedRecords: 3, processedRecords: 3 },
    });
    expect(detail.results.validationStatus).toBe(status);
    expect(detail.results.validationReason).toBe('fixture reason');
    expect(criterionLabels(detail).find(c => c.name === 'Output Correctness')?.passed)
      .toBe(status === 'FAIL' ? false : null);
  });
});
