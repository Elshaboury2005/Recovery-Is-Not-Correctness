"""Exercise task callables against the documented blocking run contract."""
from unittest.mock import Mock, patch
import pytest
from .test_dag_integrity import AIRFLOW_AVAILABLE, dagbag, dag

pytestmark=pytest.mark.skipif(not AIRFLOW_AVAILABLE,reason='Airflow runtime required')

def test_run_requests_blocking_contract_and_retains_public_id(dag):
    task=dag.get_task('run_spark_processing')
    response=Mock()
    response.json.return_value={'status':'success','pipeline_run_id':'public-id','run_id':'internal-id','metrics':{'storage':{'output_rows':17}}}
    with patch('requests.post',return_value=response) as post:
        result=task.python_callable({'yaml_content':'fixture','pipeline_id':'p'}, {'connected':True})
    assert post.call_args.kwargs['params']=={'wait':'true'}
    assert result['run_id']=='public-id'
    assert result['status']=='success'
    assert task.retries==0

@pytest.mark.parametrize('status',['running','failed','cancelled'])
def test_non_success_response_never_passes(dag,status):
    from airflow.exceptions import AirflowException
    response=Mock(); response.json.return_value={'status':status}
    with patch('requests.post',return_value=response),pytest.raises(AirflowException):
        dag.get_task('run_spark_processing').python_callable({'yaml_content':'fixture','pipeline_id':'p'}, {})
