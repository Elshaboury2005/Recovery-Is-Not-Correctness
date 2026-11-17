from app.reliability.experiment_models import ExperimentModel
from app.reliability.recovery_observer import DisabledRecoveryObserver


def test_observer_switch_defaults_to_enabled():
    config = ExperimentModel.model_validate({
        "experiment": {"name": "observer-mode"},
        "target": {"service": "kafka"},
        "fault": {"type": "container_stop", "duration": 1},
    })
    assert config.observer_enabled is True


def test_disabled_observer_is_explicitly_unobservable():
    observer = DisabledRecoveryObserver()
    assert observer.start() is True
    evidence = observer.stop()
    assert evidence["observer"]["enabled"] is False
    assert evidence["throughput_rule"]["status"] == "unobservable"
    assert evidence["events"]
