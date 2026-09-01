"""
feeds — THE ONLY PACKAGE THAT TOUCHES THE NETWORK.

Everything above this package (agents, orchestrator, synthesis, UI) consumes
contracts.py objects and never learns where a number came from. That boundary is
the whole point: the working providers here are undocumented internal APIs, not
licensed feeds, and they will eventually change shape or block us. When that
happens the fix is one adapter, not a pipeline rewrite.

MODES (docs/ARCHITECTURE.md §15.4), read from DATA_MODE:

  auto      live -> last-known-good cache -> fixture   (default)
  live      live only; a provider failure degrades that dimension
  fixtures  never opens a socket. CI and validate.py run here.

Every downgrade must append a line to data_quality.warnings. A silent fallback
would put stale or synthetic numbers in front of a user as if they were live.
"""
import os

AUTO = "auto"
LIVE = "live"
FIXTURES = "fixtures"
_VALID = (AUTO, LIVE, FIXTURES)


def mode() -> str:
    """Read every time rather than at import, so a test can flip it per case."""
    m = os.getenv("DATA_MODE", AUTO).strip().lower()
    return m if m in _VALID else AUTO


def offline() -> bool:
    """True when we are forbidden from opening a socket."""
    return mode() == FIXTURES


def may_use_fixtures() -> bool:
    """True when falling back to the hand-written corpus is allowed."""
    return mode() in (AUTO, FIXTURES)
