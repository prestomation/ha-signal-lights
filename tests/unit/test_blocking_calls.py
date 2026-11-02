"""Tests that no code blocks the event loop.

The autouse ``blockbuster`` fixture in conftest.py does the checking. Each
test runs code in a real event loop. A blocking call in that code fails the
test with the file and line of the call.

Run with: python -m pytest tests/unit/test_blocking_calls.py -v
"""

from __future__ import annotations

import asyncio
import time
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from blockbuster import BlockingError

from custom_components.signal_lights import diagnostics


def test_blockbuster_finds_a_blocking_call():
    """Guard test: the fixture must be active, or the other tests prove nothing."""

    async def blocking() -> None:
        time.sleep(0.01)

    with pytest.raises(BlockingError):
        asyncio.run(blocking())


def test_diagnostics_do_not_block_the_event_loop():
    """Downloading diagnostics must not read files in the event loop."""
    engine = MagicMock()
    engine.get_active_signals.return_value = []
    store = MagicMock()
    store.get_lights.return_value = []
    store.get_signals.return_value = []
    entry = MagicMock()
    entry.runtime_data = SimpleNamespace(engine=engine, store=store)
    entry.as_dict.return_value = {"entry_id": "abc", "data": {}}

    # create=True: the name exists only when the code reads the version from
    # the loaded integration instead of from manifest.json.
    with patch.object(
        diagnostics,
        "async_get_loaded_integration",
        create=True,
        return_value=SimpleNamespace(version="1.2.3"),
    ):
        result = asyncio.run(
            diagnostics.async_get_config_entry_diagnostics(MagicMock(), entry)
        )

    assert result["queue_depth"] == 0
