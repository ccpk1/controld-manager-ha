"""Shared manager contract for the Control D runtime."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..models import ControlDManagerRuntime


class BaseManager:
    """Base class for entry-scoped manager modules."""

    def __init__(self) -> None:
        """Initialize the base manager."""
        self._runtime: ControlDManagerRuntime | None = None

    def attach_runtime(self, runtime: ControlDManagerRuntime) -> None:
        """Attach the shared runtime reference."""
        self._runtime = runtime

    @property
    def runtime(self) -> ControlDManagerRuntime:
        """Return the attached runtime."""
        if self._runtime is None:
            raise RuntimeError("Manager runtime is not attached")
        return self._runtime
