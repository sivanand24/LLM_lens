"""Baselines and drift detection. Called periodically from the worker thread.

Phase 3 fills in baseline building and the drift rules; for now this is the hook.
"""
import logging

log = logging.getLogger(__name__)


def run_drift() -> None:
    """Rebuild stale baselines and evaluate drift rules into the alerts collection."""
    log.debug("drift job: not implemented yet")
