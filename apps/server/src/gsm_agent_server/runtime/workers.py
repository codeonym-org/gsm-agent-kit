"""Observe worker termination without changing its scheduling or retry policy."""

import asyncio
import logging
from collections.abc import Awaitable, Callable

from gsm_agent.application.runtime import WorkerId

from gsm_agent_server.infra.runtime import RuntimeMonitor

logger = logging.getLogger(__name__)


async def observe_worker(
    operation: Callable[[], Awaitable[None]], monitor: RuntimeMonitor, worker: WorkerId
) -> None:
    try:
        await operation()
    except asyncio.CancelledError:
        monitor.exited(worker, cancelled=True)
        raise
    except Exception:
        monitor.exited(worker, cancelled=False)
        logger.error("Background worker %s exited unexpectedly", worker.value)
    else:
        monitor.exited(worker, cancelled=False)
        logger.error("Background worker %s returned unexpectedly", worker.value)
