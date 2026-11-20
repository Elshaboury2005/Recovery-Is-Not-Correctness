from types import SimpleNamespace
from unittest.mock import Mock
import uuid

import pytest
import yaml

from app.reliability.experiment_runner import ExperimentRunner
from tests.reliability.test_experiment_runner import _make_experiment_config


@pytest.mark.parametrize('correct', [False, None])
def test_count_agreement_does_not_override_failed_or_unknown_integrity(correct):
    runner = ExperimentRunner(Mock(), safety=Mock(), docker_controller=Mock())
    result, reasons = runner._analyze(_make_experiment_config(), 1.0, 0,
                                    validation_passed=correct, validation_required=True)
    assert result == 'FAIL'
    assert 'Output correctness' in reasons[0]


def test_service_only_pass_makes_no_output_claim():
    runner = ExperimentRunner(Mock(), safety=Mock(), docker_controller=Mock())
    assert runner._analyze(_make_experiment_config(), 1.0, None, validation_required=False)[0] == 'PASS'


@pytest.mark.parametrize('status,path,source_hash', [
    ('running','/output','f'*64), ('succeeded',None,'f'*64), ('succeeded','/output',None),
])
def test_missing_run_evidence_never_reads_guessed_path(status,path,source_hash):
    runner = ExperimentRunner(Mock(), safety=Mock(), docker_controller=Mock())
    runner._validator = Mock()
    run = SimpleNamespace(id=uuid.uuid4(), status=status, output_path=path,
                          config_yaml='storage: {type: hdfs}',
                          last_progress_snapshot={'source':{'sha256':source_hash},'kafka':{'published':999}})
    result = runner._validate_pipeline_run(run, max_wait=0)
    assert result['validation_status'] == 'UNKNOWN'
    runner._validator.validate.assert_not_called()


def test_terminal_run_passes_its_config_source_identity_and_real_output_to_validator():
    runner = ExperimentRunner(Mock(), safety=Mock(), docker_controller=Mock())
    runner._validator = Mock()
    runner._validator.validate.return_value = {'validation_status':'PASS','validation_passed':True}
    config = {'storage':{'type':'local','path':'/configured/but/redirected'}}
    run = SimpleNamespace(id=uuid.uuid4(), status='succeeded', output_path='hdfs://namenode:9000/actual',
                          config_yaml=yaml.safe_dump(config),
                          last_progress_snapshot={'source':{'sha256':'a'*64},'kafka':{'published':999}})
    result = runner._validate_pipeline_run(run,max_wait=0)
    assert result['validated_pipeline_run_id'] == str(run.id)
    runner._validator.validate.assert_called_once_with(
        output_location={'storage_type':'hdfs','path':run.output_path},pipeline_config=config,
        writer_stopped=True, expected_source_sha256='a'*64)


@pytest.mark.parametrize('count,status', [(None, 'UNKNOWN'), (0, 'PASS'), (3, 'FAIL')])
def test_report_preserves_validation_evidence_and_explicit_unknown(count, status):
    from app.models.experiment import Experiment
    from app.models.experiment_run import ExperimentRun
    from app.reliability.report_generator import ReportGenerator

    run = ExperimentRun(id=uuid.uuid4(), experiment_id=uuid.uuid4(), pipeline_run_id=uuid.uuid4(),
        status='succeeded', params={}, results={
            'expected_record_count': 100, 'expected_records': count, 'processed_records': count,
            'actual_records': 100, 'data_loss': None if count is None else 0,
            'validation_status': status, 'reason': 'retained fixture reason',
        })
    experiment = Experiment(id=run.experiment_id, name='evidence fixture', experiment_yaml='')
    db = Mock()
    db.get.side_effect = lambda model, _: run if model is ExperimentRun else experiment
    report = ReportGenerator().generate(run.id, db)
    for record in (report, report['results']):
        assert record['expectedRecords'] == record['processedRecords'] == count
        assert record['validationStatus'] == status
        assert record['validationReason'] == 'retained fixture reason'
        assert record['duplicates'] is None
