"""Fixtures and helpers for Signal Lights Docker integration tests.

Auth is bootstrapped via HA's onboarding API (no pre-seeded auth files needed).
"""

import time

import pytest
import requests

HA_URL = "http://localhost:8123"
HA_STARTUP_TIMEOUT = 120  # seconds


def _wait_for_ha():
    """Block until HA responds to requests."""
    deadline = time.monotonic() + HA_STARTUP_TIMEOUT
    while time.monotonic() < deadline:
        try:
            r = requests.get(f"{HA_URL}/api/", timeout=5)
            if r.status_code in (200, 401):
                return
        except requests.ConnectionError:
            pass
        time.sleep(2)
    raise TimeoutError(f"Home Assistant did not start within {HA_STARTUP_TIMEOUT}s")


def _complete_onboarding():
    """Complete HA onboarding and return an access token."""
    r = requests.post(
        f"{HA_URL}/api/onboarding/users",
        json={
            "client_id": f"{HA_URL}/",
            "name": "Test",
            "username": "test",
            "password": "testtest1",
            "language": "en",
        },
        timeout=10,
    )
    if r.status_code == 200:
        auth_code = r.json()["auth_code"]
    elif r.status_code == 403:
        return _login("test", "testtest1")
    else:
        raise RuntimeError(f"Failed to create onboarding user: {r.status_code} {r.text}")

    r = requests.post(
        f"{HA_URL}/auth/token",
        data={
            "grant_type": "authorization_code",
            "code": auth_code,
            "client_id": f"{HA_URL}/",
        },
        timeout=10,
    )
    r.raise_for_status()
    token_data = r.json()
    access_token = token_data["access_token"]
    headers = {"Authorization": f"Bearer {access_token}"}

    for endpoint, payload in [
        ("core_config", {}),
        ("analytics", {}),
        ("integration", {"client_id": f"{HA_URL}/", "redirect_uri": f"{HA_URL}/?auth_callback=1"}),
    ]:
        r = requests.post(
            f"{HA_URL}/api/onboarding/{endpoint}",
            headers=headers,
            json=payload,
            timeout=10,
        )
        r.raise_for_status()

    return access_token


def _login(username, password):
    """Log in with existing credentials and return an access token."""
    r = requests.post(
        f"{HA_URL}/auth/login_flow",
        json={
            "client_id": f"{HA_URL}/",
            "handler": ["homeassistant", None],
            "redirect_uri": f"{HA_URL}/?auth_callback=1",
        },
        timeout=10,
    )
    r.raise_for_status()
    flow_id = r.json()["flow_id"]

    r = requests.post(
        f"{HA_URL}/auth/login_flow/{flow_id}",
        json={"username": username, "password": password, "client_id": f"{HA_URL}/"},
        timeout=10,
    )
    r.raise_for_status()
    result = r.json()

    r = requests.post(
        f"{HA_URL}/auth/token",
        data={
            "grant_type": "authorization_code",
            "code": result["result"],
            "client_id": f"{HA_URL}/",
        },
        timeout=10,
    )
    r.raise_for_status()
    return r.json()["access_token"]


@pytest.fixture(scope="session")
def ha_token():
    """Wait for HA to start, complete onboarding, and return an access token."""
    _wait_for_ha()
    return _complete_onboarding()


@pytest.fixture(scope="session")
def ha(ha_token):
    """Return a requests.Session pre-configured with HA auth headers."""
    session = requests.Session()
    session.headers.update({
        "Authorization": f"Bearer {ha_token}",
        "Content-Type": "application/json",
    })
    session.base_url = HA_URL

    # Wait for signal_lights entities to appear
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        try:
            r = session.get(f"{HA_URL}/api/states")
            if r.status_code == 200:
                states = r.json()
                entity_ids = [s["entity_id"] for s in states]
                if any("signal_lights" in eid for eid in entity_ids):
                    break
        except Exception:
            pass
        time.sleep(2)

    return session


def get_state(ha, entity_id):
    """Get the state object for an entity."""
    r = ha.get(f"{HA_URL}/api/states/{entity_id}")
    if r.status_code == 404:
        return None
    r.raise_for_status()
    return r.json()


def call_service(ha, domain, service, data=None):
    """Call a HA service."""
    r = ha.post(
        f"{HA_URL}/api/services/{domain}/{service}",
        json=data or {},
    )
    r.raise_for_status()
    return r.json()


def poll_state(ha, entity_id, condition, timeout=15):
    """Poll a sensor's state until condition(state_value) is True."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        state_obj = get_state(ha, entity_id)
        if state_obj is not None:
            value = state_obj["state"]
            try:
                if condition(value):
                    return value
            except (ValueError, TypeError):
                pass
        time.sleep(1)
    state_obj = get_state(ha, entity_id)
    state_val = state_obj["state"] if state_obj else "<entity not found>"
    raise TimeoutError(
        f"Timed out waiting for {entity_id} to satisfy condition. "
        f"Last state: {state_val}"
    )
