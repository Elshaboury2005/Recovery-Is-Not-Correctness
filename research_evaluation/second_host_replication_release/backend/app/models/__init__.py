"""
app/models/__init__.py
----------------------
Re-exports all ORM models so that Alembic's env.py only needs to import
this single module to register every table with the shared MetaData.
"""

from app.models.audit_log import AuditLog
from app.models.architecture_recommendation import ArchitectureRecommendation
from app.models.benchmark_campaign import BenchmarkCampaign, BenchmarkRun
from app.models.dataset_profile import DatasetProfile
from app.models.experiment import Experiment
from app.models.experiment_event import ExperimentEvent
from app.models.experiment_run import ExperimentRun
from app.models.fault_injection import FaultInjection
from app.models.hive_query import HiveQueryHistory
from app.models.metric import Metric
from app.models.pipeline import Pipeline
from app.models.pipeline_run import PipelineRun
from app.models.pipeline_run_event import PipelineRunEvent
from app.models.pipeline_version import PipelineVersion
from app.models.report import Report
from app.models.reconfiguration import ReconfigurationOperation
from app.models.user import User
from app.models.workload_definition import WorkloadDefinition

__all__ = [
    "AuditLog",
    "ArchitectureRecommendation",
    "BenchmarkCampaign",
    "BenchmarkRun",
    "DatasetProfile",
    "Experiment",
    "ExperimentEvent",
    "ExperimentRun",
    "FaultInjection",
    "HiveQueryHistory",
    "Metric",
    "Pipeline",
    "PipelineRun",
    "PipelineRunEvent",
    "PipelineVersion",
    "Report",
    "ReconfigurationOperation",
    "User",
    "WorkloadDefinition",
]
