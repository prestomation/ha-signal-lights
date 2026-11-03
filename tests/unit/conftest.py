"""Fixtures for unit tests that load the integration."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from blockbuster import BlockBuster, blockbuster_ctx


@pytest.fixture(autouse=True)
def blockbuster() -> Iterator[BlockBuster]:
    """Fail a test when code blocks the event loop thread.

    Blockbuster patches file, socket, sleep and similar calls. When such a
    call runs while an event loop runs in the same thread, it raises
    BlockingError. The error message has the exact file and line.

    Home Assistant gives the same warning at run time ("Detected blocking
    call"). This fixture finds the problem in the unit tests instead.
    The pytest-homeassistant-custom-component package does not include it,
    so we use the blockbuster package directly.
    """
    with blockbuster_ctx() as bb:
        yield bb
