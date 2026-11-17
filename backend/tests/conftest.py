"""
backend/tests/conftest.py
Global fixtures and session-level teardown hooks for pytest.
"""

import logging
import pytest

logger = logging.getLogger(__name__)


@pytest.fixture(scope="session", autouse=True)
def sweep_chaoslab_test_containers():
    """Individual fixtures remove only containers they created.

    A session-wide label sweep could delete evidence from an older session or
    another test process. Preserve those containers for explicit inspection.
    """
    yield
