"""Controlled corruption fixtures, NOT naturally observed fault outcomes."""
import copy
from datetime import datetime
import math
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from app.reliability.data_consistency_validator import DataConsistencyValidator


@pytest.fixture
def exact_fixture(tmp_path):
    source = tmp_path / 'source.csv'
    source.write_text('transaction_id,amount,customer_id,product_id,timestamp\n'
                      'T1,1.25,C1,P1,2024-01-01T00:00:00\n'
                      'T1,1.25,C1,P1,2024-01-01T00:00:00\n'
                      'T2,2.5,C2,P2,2024-01-02T00:00:00\n'
                      'T3,-1,C3,P3,2024-01-03T00:00:00\n'
                      'T4,,C4,P4,2024-01-04T00:00:00\n')
    schema = pa.schema([('transaction_id', pa.string()), ('amount', pa.float64()),
                        ('customer_id', pa.string()), ('product_id', pa.string()), ('timestamp', pa.string())])
    config = {'pipeline': {'name': 'fixture', 'version': '1.0'},
              'source': {'type': 'csv', 'path': str(source)},
              'schema': [{'name': field.name, 'type': 'double' if field.name == 'amount' else 'string'} for field in schema],
              'processing': {'operations': [{'type': 'remove_nulls'}, {'type': 'filter', 'condition': 'amount > 0'}]},
              'streaming': {'enabled': False}, 'processing_engine': {'type': 'spark'},
              'storage': {'type': 'local', 'path': str(tmp_path / 'output')}}
    rows = [{'transaction_id': 'T1', 'amount': 1.25, 'customer_id': 'C1', 'product_id': 'P1', 'timestamp': '2024-01-01T00:00:00'},
            {'transaction_id': 'T1', 'amount': 1.25, 'customer_id': 'C1', 'product_id': 'P1', 'timestamp': '2024-01-01T00:00:00'},
            {'transaction_id': 'T2', 'amount': 2.5, 'customer_id': 'C2', 'product_id': 'P2', 'timestamp': '2024-01-02T00:00:00'}]
    return config, schema, rows


def write_result(config, schema, rows):
    path = Path(config['storage']['path'])
    path.mkdir(exist_ok=True)
    pq.write_table(pa.Table.from_pylist(rows, schema=schema), path/'part-0.parquet')


def validate(config, **kwargs):
    return DataConsistencyValidator().validate(output_location={'storage_type': 'local', 'path': config['storage']['path']},
                                               pipeline_config=config, writer_stopped=True, **kwargs)


def test_intentional_filtering_and_duplicate_multiplicity_pass(exact_fixture):
    config, schema, rows = exact_fixture
    write_result(config, schema, rows)
    result = validate(config, expected_records=5)  # Legacy input count is NOT the reference.
    assert result['validation_status'] == 'PASS'
    assert result['input_records'] == 5
    assert result['expected_records'] == result['actual_records'] == 3
    assert result['missing_records'] == result['unexpected_records'] == 0
    assert result['duplicate_ids_found'] is None
    assert result['validation_passed'] is True


def test_exact_full_row_deduplication_passes_and_rejects_extra_occurrence(exact_fixture):
    config, schema, rows = exact_fixture
    config['processing']['operations'].insert(1, {'type': 'remove_duplicates'})
    deduplicated = [rows[0], rows[2]]
    write_result(config, schema, deduplicated)
    result = validate(config)
    assert result['validation_status'] == 'PASS'
    assert result['expected_records'] == result['actual_records'] == 2

    # A repeated output row remains an independently detectable corruption.
    Path(config['storage']['path']).joinpath('part-0.parquet').unlink()
    write_result(config, schema, rows)
    result = validate(config)
    assert result['validation_status'] == 'FAIL'
    assert result['unexpected_records'] == 1


def test_bounded_streaming_deduplication_requires_one_event_time_value(exact_fixture):
    config, schema, rows = exact_fixture
    source = Path(config['source']['path'])
    source.write_text(
        'transaction_id,amount,customer_id,product_id,timestamp\n'
        'T1,1.25,C1,P1,2024-01-01T00:00:00\n'
        'T1,1.25,C1,P1,2024-01-01T00:00:00\n'
        'T2,2.5,C2,P2,2024-01-01T00:00:00\n'
        'T3,-1,C3,P3,2024-01-01T00:00:00\n'
        'T4,,C4,P4,2024-01-01T00:00:00\n'
    )
    config['schema'][-1]['type'] = 'timestamp'
    config['streaming'] = {
        'enabled': True,
        'watermark': {'column': 'timestamp', 'delay_seconds': 60},
    }
    timestamp_schema = schema.set(4, pa.field('timestamp', pa.timestamp('us')))
    for row in rows:
        row['timestamp'] = datetime(2024, 1, 1)
    config['processing']['operations'].insert(1, {'type': 'remove_duplicates'})
    write_result(config, timestamp_schema, [rows[0], rows[2]])
    assert validate(config)['validation_status'] == 'PASS'

    Path(config['storage']['path']).joinpath('part-0.parquet').unlink()
    source.write_text(source.read_text().replace('T2,2.5,C2,P2,2024-01-01T00:00:00',
                                                  'T2,2.5,C2,P2,2024-01-02T00:00:00'))
    rows[2]['timestamp'] = datetime(2024, 1, 2)
    write_result(config, timestamp_schema, [rows[0], rows[2]])
    result = validate(config)
    assert result['validation_status'] == 'UNKNOWN'
    assert 'one event-time value' in result['reason']


@pytest.mark.parametrize('corruption', ['missing', 'extra', 'equal_count_substitution', 'duplicate_occurrence',
                                       'timestamp', 'precision', 'null', 'nonfinite'])
def test_full_row_occurrences_detect_corruption(exact_fixture, corruption):
    config, schema, rows = exact_fixture
    if corruption == 'missing': rows.pop(2)
    elif corruption == 'extra': rows.append(copy.deepcopy(rows[2]))
    elif corruption == 'equal_count_substitution': rows[2]['product_id'] = 'wrong'
    elif corruption == 'duplicate_occurrence': rows.pop(0)
    elif corruption == 'timestamp': rows[2]['timestamp'] = '2024-01-03T00:00:00'
    elif corruption == 'precision': rows[2]['amount'] = math.nextafter(2.5, math.inf)
    elif corruption == 'null': rows[2]['customer_id'] = None
    elif corruption == 'nonfinite': rows[2]['amount'] = math.inf
    write_result(config, schema, rows)
    result = validate(config)
    assert result['validation_status'] == 'FAIL', result
    assert result['validation_passed'] is False
    assert result['missing_records'] or result['unexpected_records']


@pytest.mark.parametrize('kind', ['wrong_type', 'column_order', 'missing_column'])
def test_physical_schema_mismatch_fails(exact_fixture, kind):
    config, schema, rows = exact_fixture
    if kind == 'wrong_type': schema = schema.set(1, pa.field('amount', pa.float32()))
    elif kind == 'column_order': schema = pa.schema(list(reversed(schema)))
    else: schema = pa.schema(list(schema)[:-1])
    write_result(config, schema, rows)
    result = validate(config)
    assert result['validation_status'] == 'FAIL'
    assert result['schema_valid'] is False


@pytest.mark.parametrize('kind', ['unavailable', 'truncated', 'missing_part'])
def test_unreadable_output_is_unknown_not_total_loss(exact_fixture, kind):
    config, schema, rows = exact_fixture
    if kind != 'unavailable':
        write_result(config, schema, rows)
        path = Path(config['storage']['path']) / ('part-0.parquet' if kind == 'truncated' else 'part-1.parquet')
        path.write_bytes(b'PAR1')
    result = validate(config)
    assert result['validation_status'] == 'UNKNOWN'
    assert result['validation_passed'] is None
    assert result['actual_records'] is None
    assert result['data_loss'] is None


def test_declared_timestamp_type_and_microsecond_precision(exact_fixture):
    config, schema, rows = exact_fixture
    config['schema'][-1]['type'] = 'timestamp'
    schema = schema.set(4, pa.field('timestamp', pa.timestamp('us')))
    for row in rows: row['timestamp'] = datetime.fromisoformat(row['timestamp'])
    write_result(config, schema, rows)
    assert validate(config)['validation_status'] == 'PASS'


def test_spark_nanosecond_timestamp_encoding_requires_microsecond_alignment(exact_fixture):
    config, _, rows = exact_fixture
    config['schema'][-1]['type'] = 'timestamp'
    for row in rows:
        row['timestamp'] = datetime.fromisoformat(row['timestamp'])
    expected_schema = pa.schema([('transaction_id', pa.string()), ('amount', pa.float64()),
                                 ('customer_id', pa.string()), ('product_id', pa.string()),
                                 ('timestamp', pa.timestamp('us'))])
    spark_schema = expected_schema.set(4, pa.field('timestamp', pa.timestamp('ns')))
    write_result(config, spark_schema, rows)
    assert validate(config)['validation_status'] == 'PASS'

    Path(config['storage']['path']).joinpath('part-0.parquet').unlink()
    table = pa.Table.from_arrays([
        pa.array(['T1', 'T1', 'T2']), pa.array([1.25, 1.25, 2.5]),
        pa.array(['C1', 'C1', 'C2']), pa.array(['P1', 'P1', 'P2']),
        pa.array([1704067200000000001, 1704067200000000000, 1704153600000000000], type=pa.timestamp('ns')),
    ], schema=spark_schema)
    pq.write_table(table, Path(config['storage']['path']) / 'part-0.parquet')
    result = validate(config)
    assert result['validation_status'] == 'FAIL'
    assert result['invariant_errors'] == 1


def test_valid_empty_output_is_not_missing(exact_fixture):
    config, schema, _ = exact_fixture
    config['processing']['operations'][1]['condition'] = 'amount > 1000'
    write_result(config, schema, [])
    result = validate(config)
    assert result['validation_status'] == 'PASS'
    assert result['actual_records'] == result['expected_records'] == 0


@pytest.mark.parametrize('reason', ['active_writer', 'no_config', 'unsupported_operation', 'row_bound', 'source_changed'])
def test_unestablished_contract_cannot_pass(exact_fixture, reason):
    config, schema, rows = exact_fixture
    write_result(config, schema, rows)
    options = {'pipeline_config': config, 'writer_stopped': True}
    if reason == 'active_writer': options['writer_stopped'] = False
    elif reason == 'no_config': options['pipeline_config'] = None
    elif reason == 'unsupported_operation': config['processing']['operations'] = [{'type': 'aggregate'}]
    elif reason == 'row_bound': options['max_rows'] = 2
    elif reason == 'source_changed': options['expected_source_sha256'] = '0' * 64
    result = DataConsistencyValidator().validate(expected_records=3,
             output_location={'storage_type': 'local', 'path': config['storage']['path']}, **options)
    assert result['validation_status'] == 'UNKNOWN'
    assert result['validation_passed'] is None


def test_partial_read_cannot_hide_bad_later_part(exact_fixture):
    config, schema, rows = exact_fixture
    write_result(config, schema, rows)
    (Path(config['storage']['path'])/'part-9.parquet').write_bytes(b'broken')
    result = validate(config)
    assert result['actual_records'] is None
    assert result['validation_status'] == 'UNKNOWN'
