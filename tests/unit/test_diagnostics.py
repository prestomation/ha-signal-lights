"""Unit tests for the diagnostics platform.

Home Assistant flags file reads on the event loop. These tests make sure
the diagnostics code does not read files in the event loop thread.

Run with: python -m pytest tests/unit/test_diagnostics.py -v
"""

from __future__ import annotations

import asyncio
import pathlib
import threading
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from custom_components.signal_lights import diagnostics


def _run() -> dict:
    return asyncio.run(
        diagnostics.async_get_config_entry_diagnostics(MagicMock(), _make_entry())
    )


def _make_entry() -> MagicMock:
    engine = MagicMock()
    engine.get_active_signals.return_value = []
    store = MagicMock()
    store.get_lights.return_value = []
    store.get_signals.return_value = []
    entry = MagicMock()
    entry.runtime_data = SimpleNamespace(engine=engine, store=store)
    entry.as_dict.return_value = {"entry_id": "abc", "data": {}}
    return entry


def test_diagnostics_do_not_read_files_in_event_loop():
    """No file read may happen in the event loop thread."""
    loop_thread = threading.get_ident()
    calls: list[int] = []
    original = pathlib.Path.read_text

    def spy(self, *args, **kwargs):
        calls.append(threading.get_ident())
        return original(self, *args, **kwargs)

    integration = SimpleNamespace(version="9.9.9")
    with (
        patch.object(pathlib.Path, "read_text", spy),
        patch.object(
            diagnostics,
            "async_get_loaded_integration",
            return_value=integration,
        ),
    ):
        _run()

    assert loop_thread not in calls


def test_diagnostics_version_comes_from_loaded_integration():
    """The reported version is the version of the loaded integration."""
    integration = SimpleNamespace(version="9.9.9")
    with patch.object(
        diagnostics,
        "async_get_loaded_integration",
        return_value=integration,
    ):
        result = _run()

    assert result["integration_version"] == "9.9.9"
    assert result["queue_depth"] == 0


def test_diagnostics_version_unknown_when_integration_has_no_version():
    """A missing version is reported as "unknown"."""
    integration = SimpleNamespace(version=None)
    with patch.object(
        diagnostics,
        "async_get_loaded_integration",
        return_value=integration,
    ):
        result = _run()

    assert result["integration_version"] == "unknown"
