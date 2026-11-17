"""Controlled commit-log fixtures; never experimental fault outcomes."""
import io
import json
from contextlib import contextmanager
from unittest.mock import Mock

import pandas as pd
import pytest

from app.storage.spark_manifest import committed_paths
from app.storage.hdfs_client import HdfsStorageClient
from app.storage.exceptions import HdfsReadError


def entry(name="part-a.parquet", **overrides):
    return {"path": f"hdfs://namenode:9000/output/{name}", "isDir": False, "action": "add", **overrides}


def log(*entries):
    return "v1\n" + "\n".join(json.dumps(e) for e in entries)


def test_compaction_replaces_history_without_duplicate_files():
    logs = {"0": "malformed superseded history", "9.compact": log(entry()),
            "10": log(entry("part-b.parquet")), ".10.tmp": "partial"}
    assert committed_paths("/output", list(logs), logs.__getitem__) == [
        "/output/part-a.parquet", "/output/part-b.parquet"]


@pytest.mark.parametrize("logs", [
    {}, {"1": log(entry())}, {"0": "v2\n"}, {"0": "v1\n{"},
    {"0": log(entry()), "2": log(entry())},
    {"0": log(entry(path="hdfs://namenode:9000/elsewhere/x.parquet"))},
    {"0": log(entry(action="delete"))},
    {"0": log(entry(isDir=True))},
])
def test_bad_commit_metadata_is_not_readable_output(logs):
    with pytest.raises((ValueError, KeyError)):
        committed_paths("/output", list(logs), logs.__getitem__)


def make_client(tmp_path, rows):
    client = HdfsStorageClient()
    remote = Mock()
    remote.status.return_value = {"type": "DIRECTORY"}
    remote.list.side_effect = lambda p: ["0"] if p.endswith("_spark_metadata") else [
        "_spark_metadata", "part-a.parquet", "part-orphan.parquet"]

    @contextmanager
    def read(*args, **kwargs):
        yield io.StringIO(log(entry()))

    remote.read.side_effect = read

    def download(source, destination, **kwargs):
        assert source == "/output/part-a.parquet", "Uncommitted file was read"
        pd.DataFrame({"id": pd.Series(rows, dtype="int64")}).to_parquet(destination, index=False)

    remote.download.side_effect = download
    client._client = remote
    return client


@pytest.mark.parametrize("rows", [[], [1, 1, 2]])
def test_hdfs_counts_and_reads_only_committed_rows_including_zero(tmp_path, rows):
    client = make_client(tmp_path, rows)
    assert client.count_rows("/output") == len(rows)
    assert client.read_dataframe("/output")["id"].tolist() == rows


def test_truncated_committed_part_is_never_skipped(tmp_path):
    client = make_client(tmp_path, [1])
    client._client.download.side_effect = None  # Missing local download.
    with pytest.raises(HdfsReadError):
        client.count_rows("/output")
    with pytest.raises(HdfsReadError):
        client.read_dataframe("/output")


def test_schema_only_part_reads_as_typed_empty_dataframe(tmp_path):
    import pyarrow as pa
    import pyarrow.parquet as pq
    path = tmp_path / "empty.parquet"
    with pq.ParquetWriter(path, pa.schema([("id", pa.int64())])):
        pass
    result = HdfsStorageClient._read_parquet_part(str(path))
    assert result.empty
    assert list(result.columns) == ["id"]
    assert str(result["id"].dtype) == "int64"
