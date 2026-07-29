"""Execution dispatch: the adapter interface, its implementations, and the worker."""

from __future__ import annotations

from atlas_conductor.dispatch.base import ExecutionAdapter
from atlas_conductor.dispatch.fake import FakeAdapter
from atlas_conductor.dispatch.worker import Worker

__all__ = ["ExecutionAdapter", "FakeAdapter", "Worker"]
