"""Recorded background-worker observations, independent of the hosting runtime."""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Literal

from gsm_agent_core.domain.devices import DeviceReadIssue

type WorkerIssue = DeviceReadIssue | Literal["operation_failed", "unexpected_exit"]


class WorkerId(StrEnum):
    INBOX = "inbox"
    REPLIES = "replies"


class WorkerState(StrEnum):
    DISABLED = "disabled"
    STARTING = "starting"
    RUNNING = "running"
    WAITING = "waiting"
    DEGRADED = "degraded"
    FAILED = "failed"
    STOPPED = "stopped"


@dataclass(frozen=True, slots=True)
class WorkerStatus:
    worker_id: WorkerId
    state: WorkerState
    iterations_started: int = 0
    iterations_succeeded: int = 0
    iterations_failed: int = 0
    consecutive_failures: int = 0
    last_attempt_at: datetime | None = None
    last_success_at: datetime | None = None
    last_failure_at: datetime | None = None
    last_issue: WorkerIssue | None = None


@dataclass(frozen=True, slots=True)
class RuntimeStatus:
    started_at: datetime
    observed_at: datetime
    workers: tuple[WorkerStatus, ...]
