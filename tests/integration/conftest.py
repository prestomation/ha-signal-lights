"""Fixtures and helpers for Signal Lights Docker integration tests.

Auth is bootstrapped via HA's onboarding API (no pre-seeded auth files needed).

The Docker lifecycle is self-managed: if Home Assistant is not already
responding on :8123 (the CI workflow starts it externally), the session-scoped
`_docker_ha` fixture brings the compose stack up, waits for readiness, and
tears it down at the end of the session — restoring the seeded `.storage`
files so repeated local runs start from the same state.
"""

import json
import shutil
import subprocess
import time
import uuid
from pathlib import Path

import pytest
import requests
import websocket

HA_URL = "http://localhost:8123"
HA_WS_URL = "ws://localhost:8123/api/websocket"
HA_STARTUP_TIMEOUT = 120  # seconds

INTEGRATION_DIR = Path(__file__).parent

# Seeded storage files (tracked in git) that HA mutates during a test run.
SEED_FILES = [
    INTEGRATION_DIR / "ha_config" / ".storage" / "core.config_entries",
    INTEGRATION_DIR / "ha_config" / ".storage" / "signal_lights",
    INTEGRATION_DIR / "ha_config" / ".storage" / "signal_lights_signal_lights_test_entry",
]


def _ha_is_up() -> bool:
    """Return True if HA already responds on :8123."""
    try:
        r = requests.get(f"{HA_URL}/api/", timeout=2)
        return r.status_code in (200, 401)
    except requests.RequestException:
        return False


@pytest.fixture(scope="session", autouse=True)
def _docker_ha():
    """Start the HA compose stack if it isn't already running.

    In CI the workflow starts compose before pytest, so this fixture detects
    the running instance and leaves lifecycle management to the workflow.
    Locally, it owns the full lifecycle: seed backup → up → wait → down →
    seed restore.
    """
    if _ha_is_up():
        yield  # externally managed (CI) — don't touch the stack
        return

    backups = {f: f.read_bytes() for f in SEED_FILES if f.exists()}
    subprocess.run(
        ["docker", "compose", "up", "-d"],
        cwd=INTEGRATION_DIR,
        check=True,
        capture_output=True,
    )
    try:
        _wait_for_ha()
        yield
    finally:
        subprocess.run(
            ["docker", "compose", "down", "-v"],
            cwd=INTEGRATION_DIR,
            check=False,
            capture_output=True,
        )
        for f, data in backups.items():
            f.write_bytes(data)
        # Remove HA-generated runtime files so the next run starts clean.
        storage = INTEGRATION_DIR / "ha_config" / ".storage"
        if storage.exists():
            for child in storage.iterdir():
                if child not in backups:
                    if child.is_dir():
                        shutil.rmtree(child, ignore_errors=True)
                    else:
                        child.unlink(missing_ok=True)


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
    elif r.status_code in (403, 404):
        # Onboarding already completed (container restarted) — newer HA
        # returns 404 for the onboarding endpoint once done, older HA 403.
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


class HaWsClient:
    """Thin Home Assistant WebSocket API client.

    This exercises the exact transport the Lovelace card uses:
    - `signal_lights/config` (one-shot config fetch)
    - `signal_lights/subscribe` (live updates)
    - `call_service` (all card buttons — errors surface here, unlike REST
      where the card never looks at the response body)
    """

    def __init__(self, token: str):
        self.ws = websocket.create_connection(HA_WS_URL, timeout=15)
        assert json.loads(self.ws.recv())["type"] == "auth_required"
        self.ws.send(json.dumps({"type": "auth", "access_token": token}))
        msg = json.loads(self.ws.recv())
        assert msg["type"] == "auth_ok", f"WS auth failed: {msg}"
        self._id = 0

    def close(self):
        self.ws.close()

    def send(self, **msg) -> int:
        self._id += 1
        msg["id"] = self._id
        self.ws.send(json.dumps(msg))
        return self._id

    def recv_result(self, msg_id: int, timeout: float = 15) -> dict:
        """Read messages until the result for msg_id arrives (events are skipped)."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            self.ws.settimeout(max(0.1, deadline - time.monotonic()))
            resp = json.loads(self.ws.recv())
            if resp.get("id") == msg_id and resp.get("type") == "result":
                return resp
        raise TimeoutError(f"No result for WS message {msg_id} within {timeout}s")

    def cmd(self, **msg) -> dict:
        """Send a command and return its result message."""
        return self.recv_result(self.send(**msg))

    def call_service(self, domain: str, service: str, data: dict | None = None) -> dict:
        """Call a service the way the card does; returns the raw result message.

        result["success"] is False when the handler raised — this is what the
        card's `.catch()` sees.
        """
        return self.cmd(
            type="call_service",
            domain=domain,
            service=service,
            service_data=data or {},
        )

    def get_signal_lights_config(self, entry_id: str | None = None) -> list[dict]:
        msg = {"type": "signal_lights/config"}
        if entry_id:
            msg["entry_id"] = entry_id
        result = self.cmd(**msg)
        assert result["success"], f"signal_lights/config failed: {result}"
        return result["result"]


@pytest.fixture
def ws(ha_token):
    """Authenticated HA WebSocket client (closed after the test)."""
    client = HaWsClient(ha_token)
    yield client
    client.close()


@pytest.fixture
def unique_name():
    """A unique signal name so tests don't collide across runs."""
    return f"itest_{uuid.uuid4().hex[:8]}"


def get_signal(ws_client, name):
    """Return a signal dict by name from the first entry's config, or None."""
    entries = ws_client.get_signal_lights_config()
    for entry in entries:
        for sig in entry["signals"]:
            if sig["name"] == name:
                return sig
    return None


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
