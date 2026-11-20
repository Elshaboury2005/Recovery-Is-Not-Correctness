from unittest.mock import Mock, patch
import json

import pytest
import requests

from app.reliability.docker_controller import DockerController
from app.reliability.exceptions import UnsafeTargetError


def controller():
    safety = Mock()
    container = safety._find_container.return_value
    container.name = "target"
    container.id = "target-id"
    container.status = "running"
    return DockerController(safety), safety, container


def response(data):
    result = Mock()
    result.json.return_value = data
    return result


def test_docker_read_failure_is_unknown():
    probe, _, target = controller()
    target.reload.side_effect = TimeoutError
    assert probe.observe_container("kafka")["value"] is None


def test_safety_gate_applies_to_both_read_probes():
    probe, safety, _ = controller()
    safety.validate_target.side_effect = UnsafeTargetError("unlisted")
    for method in (probe.observe_container, probe.observe_service):
        with pytest.raises(UnsafeTargetError):
            method("unlisted")


def test_other_live_worker_cannot_satisfy_target_readiness():
    probe, safety, _ = controller()
    with patch("requests.get", side_effect=[response({"id": "target-worker"}),
               response({"workers": [{"id": "other-worker", "state": "ALIVE"}]})]):
        assert probe.observe_service("spark-worker")["value"] is False
    safety.validate_target.assert_called_once_with("spark-worker")


def test_namenode_readiness_cannot_substitute_for_target_datanode():
    probe, _, _ = controller()
    dn = {"DatanodeHostname": "target-dn", "DataPort": "9866",
          "BPServiceActorInfo": json.dumps([{"ActorState": "RUNNING"}])}
    nn = {"LiveNodes": json.dumps({"other-dn:9866": {"adminState": "In Service"}})}
    with patch("requests.get", side_effect=[response({"beans": [dn]}), response({"beans": [nn]})]):
        assert probe.observe_service("datanode")["value"] is False


@pytest.mark.parametrize("error,expected", [(requests.Timeout, False), (KeyError, None)])
def test_probe_failure_distinguishes_unready_from_unobservable(error, expected):
    probe, _, _ = controller()
    with patch("requests.get", side_effect=error):
        assert probe.observe_service("spark-worker")["value"] is expected
