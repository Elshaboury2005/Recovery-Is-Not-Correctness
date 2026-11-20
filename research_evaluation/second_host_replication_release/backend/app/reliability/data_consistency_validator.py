"""Bounded, transformation-aware CSV -> Parquet exact production validation.

Production reference: Arrow CSV parsing + a small independent interpreter,
disk-backed SQLite full-row multiplicities and deduplication state, plus binary
typed canonicalization. It imports neither Spark transformation code nor the
research CSV/Counter oracle. UNKNOWN is an absence of evidence, never an
invented empty output.
"""
from __future__ import annotations

import ast
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import math
import operator
from pathlib import Path
import re
import sqlite3
import struct
import tempfile
import time
from urllib.parse import urlsplit

import pyarrow as pa
import pyarrow.csv as arrow_csv
import pyarrow.parquet as parquet


class ContractUnavailable(ValueError):
    """Unsupported, unstable, unreadable, or resource-bounded evidence."""


TYPES = {'string': pa.string(), 'integer': pa.int32(), 'double': pa.float64(),
         'boolean': pa.bool_(), 'timestamp': pa.timestamp('us')}
COMPARISONS = {'>': operator.gt, '<': operator.lt, '>=': operator.ge, '<=': operator.le,
               '=': operator.eq, '==': operator.eq, '!=': operator.ne}


def file_hash(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def compile_contract(config):
    if config.get('source', {}).get('type') != 'csv':
        raise ContractUnavailable('Only finite local CSV-source contracts are implemented')
    fields = config.get('schema', [])
    if not fields or len({f['name'] for f in fields}) != len(fields):
        raise ContractUnavailable('Missing or ambiguous declared schema')
    input_schema = pa.schema([(f['name'], TYPES[f['type']]) for f in fields])
    schema = input_schema
    instructions = []
    deduplication_count = 0
    for op in config.get('processing', {}).get('operations', []):
        kind = op['type']
        if kind == 'remove_nulls':
            instructions.append((kind, None))
        elif kind == 'remove_duplicates':
            # The table name is generated here, never taken from configuration.
            # Retaining state in SQLite keeps the reference bounded and avoids a
            # hidden in-memory set for large finite sources.
            instructions.append((kind, (f'dedup_{deduplication_count}', schema)))
            deduplication_count += 1
        elif kind == 'filter':
            match = re.fullmatch(r'\s*([A-Za-z_]\w*)\s*(>=|<=|!=|==|=|>|<)\s*(.+?)\s*', op['condition'])
            if not match or match[1] not in schema.names:
                raise ContractUnavailable('Filter reference supports one column/literal comparison only')
            literal = ast.literal_eval(match[3])
            if not isinstance(literal, (str, int, float, bool)) or (isinstance(literal, float) and not math.isfinite(literal)):
                raise ContractUnavailable('Unsupported filter literal')
            instructions.append((kind, (match[1], COMPARISONS[match[2]], literal)))
        elif kind == 'select_columns':
            columns = op['columns']
            if len(columns) != len(set(columns)):
                raise ContractUnavailable('Repeated projected column names')
            schema = pa.schema([schema.field(c) for c in columns])
            instructions.append((kind, columns))
        elif kind == 'rename_columns':
            mapping = op['mapping']
            if set(mapping) - set(schema.names) or set(mapping.values()) & set(schema.names):
                raise ContractUnavailable('Renaming collisions/chains not supported')
            schema = pa.schema([(mapping.get(f.name, f.name), f.type) for f in schema])
            if len(set(schema.names)) != len(schema.names):
                raise ContractUnavailable('Ambiguous renamed schema')
            instructions.append((kind, mapping))
        else:
            raise ContractUnavailable(f'No independent reference for operation: {kind}')
    return input_schema, schema, instructions


def transform(row, instructions, index):
    for kind, operand in instructions:
        if kind == 'remove_nulls' and any(v is None for v in row.values()):
            return None
        if kind == 'remove_duplicates':
            table, current_schema = operand
            inserted = index.execute(
                f'INSERT OR IGNORE INTO {table} (row) VALUES (?)',
                (encode_row(row, current_schema),),
            ).rowcount
            if inserted != 1:
                return None
        if kind == 'filter':
            column, compare, literal = operand
            if row[column] is None or not compare(row[column], literal):
                return None
        if kind == 'select_columns':
            row = {column: row[column] for column in operand}
        if kind == 'rename_columns':
            row = {operand.get(column, column): value for column, value in row.items()}
    return row


def encode_row(row, schema):
    """Type+length-delimited bytes; no rounding, hashing collisions, or ID heuristic."""
    chunks = []
    for field in schema:
        value = row[field.name]
        if value is None:
            chunks.append(b'N')
            continue
        kind = field.type
        if pa.types.is_string(kind):
            data = value.encode('utf-8')
            chunks.append(b'S' + struct.pack('>Q', len(data)) + data)
        elif pa.types.is_floating(kind):
            chunks.append(b'F' + struct.pack('>d', value))
        elif pa.types.is_integer(kind):
            chunks.append(b'I' + struct.pack('>q', value))
        elif pa.types.is_boolean(kind):
            chunks.append(b'B1' if value else b'B0')
        elif pa.types.is_timestamp(kind):
            if value.tzinfo:
                value = value.astimezone(timezone.utc).replace(tzinfo=None)
            delta = value - datetime(1970, 1, 1)
            micros = (delta.days * 86400 + delta.seconds) * 1000000 + delta.microseconds
            chunks.append(b'T' + struct.pack('>q', micros))
        else:
            raise ContractUnavailable(f'Unsupported physical type: {kind}')
    return b''.join(chunks)


def schema_compatible(actual, expected):
    """Compare declared logical types without accepting timestamp precision loss.

    Spark 3.5's Parquet writer exposes its logical timestamps as ``ns`` through
    PyArrow even when all source values have microsecond precision. The finite
    CSV contract supports microseconds, so ``ns`` is compatible only when the
    values themselves are microsecond-aligned (checked while reading batches).
    """
    if actual.names != expected.names or len(actual) != len(expected):
        return False
    for observed, wanted in zip(actual, expected):
        if pa.types.is_timestamp(wanted.type):
            if not pa.types.is_timestamp(observed.type) or observed.type.tz is not None:
                return False
        elif observed.type != wanted.type:
            return False
    return True


def submicrosecond_timestamp_values(batch, schema):
    """Count nanosecond timestamp values that cannot represent CSV microseconds."""
    errors = 0
    for position, field in enumerate(schema):
        if not pa.types.is_timestamp(field.type) or field.type.unit != 'ns':
            continue
        raw = batch.column(position).cast(pa.int64()).to_pylist()
        errors += sum(value is not None and value % 1_000 != 0 for value in raw)
    return errors


def unknown_result(reason, **evidence):
    return {'validator_version': 'exact-csv-sqlite-v1', 'validation_status': 'UNKNOWN',
            'validation_passed': None, 'output_correct': None, 'reason': reason,
            'expected_records': None, 'actual_records': None, 'processed_records': None,
            'data_loss': None, 'data_loss_percentage': None, 'missing_records': None,
            'unexpected_records': None, 'schema_valid': None, 'invariant_errors': None,
            'duplicate_ids_found': None, 'id_column': None, **evidence}


class DataConsistencyValidator:
    def validate(self, expected_records=None, output_location=None, *, pipeline_config=None,
                 writer_stopped=False, expected_source_sha256=None, max_rows=2_000_000,
                 max_source_bytes=256*1024*1024, max_output_bytes=1024*1024*1024,
                 max_seconds=180, max_index_bytes=1024*1024*1024):
        """Exact bounded validation. Legacy expected_records is ignored by design.

        Caller must establish a stopped writer and exact run/output association.
        Defaults bound source/output/SQLite bytes, row counts, and computation.
        Local temporary comparison state is discarded; returned evidence includes
        source/config/part hashes, scope, schema and occurrence differences.
        """
        start = time.monotonic()
        evidence = {'validation_scope': 'declared-csv-full-row-multiset',
                    'legacy_expected_records_ignored': expected_records,
                    'limits': {'max_rows': max_rows, 'max_source_bytes': max_source_bytes,
                               'max_output_bytes': max_output_bytes, 'max_seconds': max_seconds,
                               'max_index_bytes': max_index_bytes}}
        try:
            if not writer_stopped:
                raise ContractUnavailable('Writer is not confirmed stopped')
            if not pipeline_config:
                raise ContractUnavailable('Transformation semantics and source are required; count alone is insufficient')
            if hasattr(pipeline_config, 'model_dump'):
                pipeline_config = pipeline_config.model_dump(by_alias=True)
            evidence['configuration_sha256'] = hashlib.sha256(json.dumps(pipeline_config,sort_keys=True).encode()).hexdigest()
            source_schema, expected_schema, instructions = compile_contract(pipeline_config)
            streaming_deduplication = bool(
                pipeline_config.get('streaming', {}).get('enabled')
                and any(kind == 'remove_duplicates' for kind, _ in instructions)
            )
            watermark_column = None
            if streaming_deduplication:
                watermark = pipeline_config.get('streaming', {}).get('watermark') or {}
                watermark_column = watermark.get('column')
                if watermark_column not in source_schema.names or not pa.types.is_timestamp(source_schema.field(watermark_column).type):
                    raise ContractUnavailable('Streaming deduplication requires a declared timestamp watermark column')
                evidence['streaming_deduplication_scope'] = (
                    'finite source with one non-null event-time value; exact full-row state is retained for the bounded run'
                )
            source = Path(pipeline_config['source']['path'])
            if source.stat().st_size > max_source_bytes:
                raise ContractUnavailable('Source byte bound exceeded')
            evidence['source_sha256'] = file_hash(source)
            if expected_source_sha256 is not None and evidence['source_sha256'] != expected_source_sha256:
                raise ContractUnavailable('Source differs from captured run input')
            evidence['source_identity_scope'] = 'matches captured source' if expected_source_sha256 else 'validation-time source only'
            with tempfile.TemporaryDirectory(prefix='chaosflow-validate-') as temporary:
                index_path = Path(temporary)/'occurrences.sqlite'
                with sqlite3.connect(index_path) as index:
                    index.execute('PRAGMA cache_size=-8192')
                    index.execute('PRAGMA temp_store=FILE')
                    index.execute('CREATE TABLE rows (row BLOB PRIMARY KEY, expected INTEGER NOT NULL, actual INTEGER NOT NULL) WITHOUT ROWID')
                    for kind, operand in instructions:
                        if kind == 'remove_duplicates':
                            table, _ = operand
                            index.execute(f'CREATE TABLE {table} (row BLOB PRIMARY KEY) WITHOUT ROWID')
                    def bound():
                        if time.monotonic()-start > max_seconds:
                            raise ContractUnavailable('Validation computation deadline exceeded')
                        if index_path.stat().st_size > max_index_bytes:
                            raise ContractUnavailable('Disk-backed comparison bound exceeded')
                    def add(rows, column):
                        counts = Counter(encode_row(row, expected_schema) for row in rows)
                        sql = ('INSERT INTO rows VALUES (?, ?, 0) ON CONFLICT(row) DO UPDATE SET expected=expected+excluded.expected'
                               if column == 'expected' else
                               'INSERT INTO rows VALUES (?, 0, ?) ON CONFLICT(row) DO UPDATE SET actual=actual+excluded.actual')
                        index.executemany(sql, counts.items())
                        index.commit()
                        bound()
                    source_count = expected_count = 0
                    watermark_values = set()
                    reader = arrow_csv.open_csv(source,
                        read_options=arrow_csv.ReadOptions(block_size=1024*1024, use_threads=False),
                        convert_options=arrow_csv.ConvertOptions(column_types=source_schema,
                            strings_can_be_null=True, null_values=['']))
                    if reader.schema.names != source_schema.names:
                        raise ContractUnavailable('CSV header/order differs from declared schema')
                    for batch in reader:
                        source_count += batch.num_rows
                        if source_count > max_rows:
                            raise ContractUnavailable('Source row bound exceeded')
                        expected = []
                        for row in batch.to_pylist():
                            if any(isinstance(v, float) and not math.isfinite(v) for v in row.values()):
                                raise ContractUnavailable('Nonfinite source numeric value: unsupported source-data quality')
                            if streaming_deduplication:
                                # With one event-time value, every valid row is
                                # above the same watermark and Spark cannot evict
                                # prior deduplication state during this finite run.
                                # Broader watermark/late-data semantics remain
                                # intentionally unavailable to this validator.
                                value = row[watermark_column]
                                if value is None:
                                    raise ContractUnavailable('Streaming deduplication source has null watermark values')
                                watermark_values.add(value)
                                if len(watermark_values) > 1:
                                    raise ContractUnavailable(
                                        'Streaming deduplication requires one event-time value; watermark eviction/late-data semantics are unavailable'
                                    )
                            output = transform(row, instructions, index)
                            if output is not None: expected.append(output)
                        expected_count += len(expected)
                        add(expected, 'expected')
                    if file_hash(source) != evidence['source_sha256']:
                        raise ContractUnavailable('Source changed while computing reference')
                    evidence.update(input_records=source_count, expected_records=expected_count,
                                    expected_schema=str(expected_schema))
                    files = list(self._output_files(output_location, temporary))
                    if not files:
                        raise ContractUnavailable('No schema-bearing committed output parts')
                    actual_count = total_bytes = errors = 0
                    schema_valid = True
                    parts = []
                    for remote, local, byte_count in files:
                        total_bytes += byte_count
                        if total_bytes > max_output_bytes:
                            raise ContractUnavailable('Output byte bound exceeded')
                        # Downloads are lazy and occur only after the byte check.
                        local = local() if callable(local) else local
                        part = parquet.ParquetFile(local)
                        valid = schema_compatible(part.schema_arrow, expected_schema)
                        schema_valid &= valid
                        if actual_count + part.metadata.num_rows > max_rows:
                            raise ContractUnavailable('Output row bound exceeded')
                        # Zero row-group Spark files are schema-bearing empty outputs.
                        if part.metadata.num_row_groups:
                            for batch in part.iter_batches(batch_size=8192, use_threads=False):
                                actual_count += batch.num_rows
                                if valid:
                                    rows = batch.to_pylist()
                                    errors += sum(any(isinstance(v, float) and not math.isfinite(v) for v in row.values()) for row in rows)
                                    errors += submicrosecond_timestamp_values(batch, part.schema_arrow)
                                    add(rows, 'actual')
                                bound()
                        parts.append({'path': remote, 'rows': part.metadata.num_rows,
                                      'schema': str(part.schema_arrow), 'bytes': byte_count, 'sha256': file_hash(local)})
                    evidence['parts'] = parts
                    missing, extra = index.execute('SELECT coalesce(sum(max(expected-actual,0)),0), coalesce(sum(max(actual-expected,0)),0) FROM rows').fetchone()
                    passed = schema_valid and not missing and not extra and not errors
                    return {**unknown_result('', **evidence), 'validation_status': 'PASS' if passed else 'FAIL',
                            'validation_passed': passed, 'output_correct': passed, 'reason': None,
                            'actual_records': actual_count, 'processed_records': actual_count,
                            'schema_valid': schema_valid, 'invariant_errors': errors,
                            'missing_records': missing if schema_valid else None,
                            'unexpected_records': extra if schema_valid else None,
                            'data_loss': missing if schema_valid else None,
                            'data_loss_percentage': (round(missing/expected_count*100,4) if expected_count else 0.0) if schema_valid else None,
                            'validation_seconds': time.monotonic()-start}
        except Exception as exc:
            return unknown_result(f'{type(exc).__name__}: {exc}', **evidence,
                                  validation_seconds=time.monotonic()-start)

    def _output_files(self, output_location, temporary):
        if not output_location or not output_location.get('path'):
            raise ContractUnavailable('Missing exact run output location')
        path = output_location['path']
        storage = output_location.get('storage_type')
        if storage == 'hdfs' or urlsplit(path).scheme == 'hdfs':
            from app.storage.hdfs_client import HdfsStorageClient
            client = HdfsStorageClient()
            for i, remote in enumerate(client.parquet_paths(path)):
                size = client._hdfs_client.status(remote)['length']
                local = str(Path(temporary)/f'part-{i}.parquet')
                def download(remote=remote, local=local):
                    client._hdfs_client.download(remote, local)
                    return local
                yield remote, download, size
        elif storage == 'local':
            root = Path(path)
            if (root/'_spark_metadata').exists():
                raise ContractUnavailable('Local Spark commit logs not implemented; no directory fallback')
            files = sorted(root.glob('*.parquet')) if root.is_dir() else [root]
            for part in files:
                yield str(part), part, part.stat().st_size
        else:
            raise ContractUnavailable(f'Unsupported storage: {storage}')
