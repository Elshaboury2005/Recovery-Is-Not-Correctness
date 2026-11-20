from unittest.mock import Mock

import pytest

from batch_processing_job import BatchProcessingJob


def job_for(spark):
    job = object.__new__(BatchProcessingJob)
    job.spark = spark
    job.logger = Mock()
    job.config = {'schema':[{'name':'id','type':'string'}, {'name':'amount','type':'double'},
                            {'name':'timestamp','type':'string'}]}
    return job


def test_batch_honors_declared_types_not_csv_inference(spark,tmp_path):
    path = tmp_path/'source.csv'
    path.write_text('id,amount,timestamp\n001,1.25,2024-01-01\n')
    frame = job_for(spark)._read_source(str(path))
    assert frame.schema.simpleString() == 'struct<id:string,amount:double,timestamp:string>'
    assert frame.first().asDict() == {'id':'001','amount':1.25,'timestamp':'2024-01-01'}


def test_mismatched_header_is_not_silently_projected(spark,tmp_path):
    path = tmp_path/'bad.csv'
    path.write_text('id,amount,wrong_date\n001,1.25,2024-01-01\n')
    with pytest.raises(Exception, match='CSV header does not conform'):
        job_for(spark)._read_source(str(path)).collect()


def test_unknown_batch_operation_fails():
    with pytest.raises(ValueError,match='Unsupported batch operation'):
        job_for(Mock())._apply_operations(Mock(),[{'type':'unknown'}])
