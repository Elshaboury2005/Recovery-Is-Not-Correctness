"""Distinct abrupt mechanism, safety enforcement and rollback behavior."""
from unittest.mock import MagicMock

import pytest

from app.reliability.docker_controller import DockerController
from app.reliability.exceptions import FaultInjectionError, UnsafeTargetError
from app.reliability.experiment_models import FaultConfig
from app.reliability.fault_injectors.base_fault import FAULT_INJECTOR_REGISTRY
from app.reliability.fault_injectors.container_sigkill_fault import ContainerSigkillFault


def test_explicit_schema_registry_and_no_graceful_stop():
    assert FaultConfig(type="container_sigkill", duration=5).type == "container_sigkill"
    assert FAULT_INJECTOR_REGISTRY["container_sigkill"] is ContainerSigkillFault
    safety = MagicMock()
    container = safety._find_container.return_value
    container.id = "a"*64
    container.name = "platform-datanode"
    controller = DockerController(safety)
    fault = ContainerSigkillFault(controller)
    result = fault.inject("datanode", {})
    safety.validate_target.assert_called_once_with("datanode")
    container.kill.assert_called_once_with(signal="SIGKILL")
    container.stop.assert_not_called()
    assert result["fault_type"] == "container_sigkill"
    assert result["signal_requested"] == "SIGKILL"


def test_rejected_target_is_never_resolved_or_killed():
    safety = MagicMock()
    safety.validate_target.side_effect = UnsafeTargetError("Forbidden target")
    with pytest.raises(UnsafeTargetError):
        DockerController(safety).kill_container("unrelated-service")
    safety._find_container.assert_not_called()


def test_docker_failure_is_not_reported_as_success():
    safety = MagicMock()
    safety._find_container.return_value.kill.side_effect = RuntimeError("daemon refused")
    with pytest.raises(FaultInjectionError) as error:
        DockerController(safety).kill_container("datanode")
    assert error.value.fault_type == "container_sigkill"


@pytest.mark.parametrize("running", [False, True])
def test_rollback_recovers_stopped_target_and_is_idempotent(running):
    controller = MagicMock()
    controller.is_container_running.return_value = running
    ContainerSigkillFault(controller).rollback("datanode", {})
    assert controller.start_container.call_count == (0 if running else 1)
