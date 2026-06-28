from __future__ import annotations

"""Default-visible TaskHarness adapter entrypoint.

The implementation is still hosted in standard_harness.py for compatibility
with the historical workflow module. Default-visible bounded Executor code
imports through this module so component lifecycle tracking can distinguish the
shared Agent phase adapter from the legacy standard-harness workflow path.
"""

from .standard_harness import TaskHarness

__all__ = ["TaskHarness"]
