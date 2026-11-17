from unittest.mock import Mock

import pytest

from streaming_processing_job import StreamingProcessingJob


def test_unsupported_transformation_is_not_silently_skipped():
    job = object.__new__(StreamingProcessingJob)
    with pytest.raises(ValueError, match="Unsupported streaming operation"):
        job._apply_streaming_operations(Mock(), [{"type": "not_implemented"}])


@pytest.mark.parametrize("rows", [0, 17])
def test_committed_count_comes_from_sink_not_input(rows):
    job = object.__new__(StreamingProcessingJob)
    job.spark = Mock()
    job.spark.read.parquet.return_value.count.return_value = rows
    assert job._committed_output_rows("hdfs://namenode:9000/test") == rows
    job.spark.read.parquet.assert_called_once_with("hdfs://namenode:9000/test")
