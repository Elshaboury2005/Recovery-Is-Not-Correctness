"""Legacy count-only calls cannot establish correctness under the new contract.

Old count/ID-heuristic acceptance assertions are deliberately retired. Actual
missing/extra/duplicate/schema/Parquet tests now live in test_exact_validation.
The original implementation and tests remain in the Phase 2 source archive.
"""
import pandas as pd
import pytest

from app.reliability.data_consistency_validator import DataConsistencyValidator


@pytest.mark.parametrize('expected,actual,duplicates', [
    (3,3,False), (5,2,False), (5,10,False), (0,0,False),
    (3,3,True), (2,2,False), (4,3,False), (100000,100000,False),
])
def test_legacy_cardinality_or_unique_ids_cannot_prove_correctness(tmp_path, expected, actual, duplicates):
    frame = pd.DataFrame({'transaction_id': ['same' if duplicates else str(i) for i in range(actual)]})
    path = tmp_path/'data.parquet'
    frame.to_parquet(path,index=False)
    result = DataConsistencyValidator().validate(expected, {'storage_type':'local','path':str(path)}, writer_stopped=True)
    assert result['validation_status'] == 'UNKNOWN'
    assert result['validation_passed'] is None
    assert result['data_loss'] is None
    assert result['duplicate_ids_found'] is None


def test_missing_output_without_contract_is_not_claimed_as_total_loss():
    result = DataConsistencyValidator().validate(100, {'storage_type':'local','path':'/nonexistent/output'})
    assert result['actual_records'] is None
    assert result['data_loss_percentage'] is None
    assert result['validation_status'] == 'UNKNOWN'
