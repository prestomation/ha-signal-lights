"""Touch every user-facing surface once, so the Home Assistant log can show problems.

The CI log gate (scripts/check_ha_log.py) reads the container log after all
tests ran. It can only find a problem in code that ran. These tests call:

- the diagnostics download (REST endpoint)
- the options flow (REST endpoints)
- each service, one time with valid data

They check that each call works. The log gate checks what the calls wrote
to the log.
"""

import pytest
from conftest import HA_URL

FLOW_URL = f"{HA_URL}/api/config/config_entries/options/flow"


@pytest.fixture
def entry_id(ws):
    entries = ws.get_signal_lights_config()
    assert entries, "no Signal Lights config entry"
    return entries[0]["entry_id"]


def test_diagnostics_download(ha, entry_id):
    """Download diagnostics the way the Home Assistant UI does."""
    r = ha.get(f"{HA_URL}/api/diagnostics/config_entry/{entry_id}", timeout=30)
    assert r.status_code == 200, r.text
    body = r.json()
    assert isinstance(body, dict), body
    # Home Assistant wraps the integration data under "data".
    assert "data" in body, f"no 'data' key; body keys: {sorted(body)}"
    data = body["data"]
    expected = (
        "config_entry",
        "integration_version",
        "lights",
        "signals",
        "active_signals",
        "queue_depth",
    )
    for key in expected:
        assert key in data, f"missing diagnostics key {key}; data keys: {sorted(data)}"
    version = data["integration_version"]
    assert isinstance(version, str) and version, f"bad version: {version!r}"


def _start_flow(ha, entry_id):
    r = ha.post(FLOW_URL, json={"handler": entry_id}, timeout=15)
    assert r.status_code == 200, r.text
    result = r.json()
    assert result["type"] == "form", result
    return result["flow_id"]


def test_options_flow_open_and_abort(ha, entry_id):
    """Open the options menu, then close it without a change."""
    flow_id = _start_flow(ha, entry_id)
    r = ha.delete(f"{FLOW_URL}/{flow_id}", timeout=15)
    assert r.status_code == 200, r.text


def test_options_flow_configure_cycling(ha, entry_id):
    flow_id = _start_flow(ha, entry_id)
    r = ha.post(f"{FLOW_URL}/{flow_id}", json={"action": "configure_cycling"}, timeout=15)
    assert r.status_code == 200, r.text
    assert r.json()["step_id"] == "configure_cycling"
    r = ha.post(
        f"{FLOW_URL}/{flow_id}",
        json={"cycle_interval_seconds": 3},
        timeout=15,
    )
    assert r.status_code == 200, r.text
    assert r.json()["type"] == "create_entry", r.json()


def test_options_flow_configure_notifications(ha, entry_id):
    flow_id = _start_flow(ha, entry_id)
    r = ha.post(
        f"{FLOW_URL}/{flow_id}", json={"action": "configure_notifications"}, timeout=15
    )
    assert r.status_code == 200, r.text
    assert r.json()["step_id"] == "configure_notifications"
    r = ha.post(f"{FLOW_URL}/{flow_id}", json={"enabled": False}, timeout=15)
    assert r.status_code == 200, r.text
    assert r.json()["type"] == "create_entry", r.json()


def test_every_service_once(ws, unique_name):
    """Call each Signal Lights service one time with valid data."""
    light = "light.surface_lamp"
    name = unique_name

    def call(service, data=None):
        result = ws.call_service("signal_lights", service, data or {})
        assert result["success"], f"{service} failed: {result}"

    try:
        call("add_light", {"entity_id": light, "brightness": 100})
        call("add_signal", {
            "name": name,
            "color": [1, 2, 3],
            "trigger_type": "event",
            "trigger_mode": "entity_equals",
            "trigger_config": {"entity_id": "binary_sensor.surface", "state": "on"},
            "template": "",
            "duration": 30,
        })
        call("update_signal", {
            "name": name,
            "color": [3, 2, 1],
            "trigger_type": "event",
            "trigger_mode": "entity_equals",
            "trigger_config": {"entity_id": "binary_sensor.surface", "state": "on"},
            "duration": 30,
        })
        call("trigger_signal", {"name": name})
        call("refresh")
        call("dismiss_signal", {"name": name})
        order = [s["name"] for s in ws.get_signal_lights_config()[0]["signals"]]
        call("reorder_signals", {"order": order})
        call("configure_notifications", {"enabled": False, "targets": []})
        call("set_cycle_interval", {"cycle_interval_seconds": 3})
    finally:
        ws.call_service("signal_lights", "remove_signal", {"name": name})
        ws.call_service("signal_lights", "remove_light", {"entity_id": light})
