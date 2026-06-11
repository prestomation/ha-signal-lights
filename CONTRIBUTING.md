# Contributing to Signal Lights

## Development Setup

### Prerequisites
- Python 3.12+
- Node.js 20+
- Docker (for integration tests)

### Install dependencies

```bash
# Python
pip install -e ".[dev]"

# JavaScript
npm install
```

## Running Tests

### Unit tests (Python engine)
```bash
python -m pytest tests/test_engine.py -v
```

### Unit tests (JavaScript card utilities)
```bash
npm test
```

### Compile check
```bash
find custom_components -name "*.py" -exec python -m py_compile {} +
```

### Integration tests (requires Docker)

The harness manages the Docker lifecycle itself — just run pytest:

```bash
cd tests/integration
python -m pytest . -v --tb=short --timeout=300
```

If Home Assistant is not already running on `:8123`, the session fixture
starts the compose stack, waits for readiness, runs the tests, tears the
stack down, and restores the seeded `.storage` files so repeated runs start
from identical state. If HA is already up (e.g. started manually or by CI),
the fixture uses it as-is and leaves lifecycle management to whoever
started it:

```bash
# optional: manage the stack yourself for faster iteration
cd tests/integration
docker compose up -d
bash ../../scripts/wait-for-ha.sh
python -m pytest . -v --tb=short --timeout=300
docker compose down -v
```

Integration tests talk to HA over both REST and the WebSocket API
(`conftest.HaWsClient`) — the WS path is the same transport the Lovelace
card uses, so service errors and `signal_lights/config` / `subscribe`
behavior are exercised exactly as the card sees them.

### Run everything (except integration)
```bash
python -m pytest tests/test_engine.py -v && npm test && find custom_components -name "*.py" -exec python -m py_compile {} +
```

## CI Checks

All CI workflows call scripts from `scripts/` — you can run the same checks locally:

| CI Check | Local Command |
|----------|--------------|
| Python unit tests | `python -m pytest tests/test_engine.py -v` |
| JS unit tests | `npm test` |
| Compile check | `find custom_components -name "*.py" -exec python -m py_compile {} +` |
| Integration tests | See above (Docker required) |
| HACS validation | Runs HACS action (CI only) |
| hassfest validation | Runs hassfest (CI only, but `python -m script.hassfest` works locally with HA dev env) |

## Releases

Releases are cut by pushing a tag; the Release workflow validates, runs the
integration tests, builds `signal_lights.zip`, and publishes a GitHub release.

### Full release

```bash
git tag v1.3.0 && git push origin v1.3.0
```

- Published as a normal GitHub release — all HACS users are offered the update
- `manifest.json` on `main` is bumped to the released version
- Release notes come from the matching `## [1.3.0]` section in CHANGELOG.md

### Beta release

```bash
git tag v1.3.0b1 && git push origin v1.3.0b1   # also: a1 (alpha), rc1
```

- Published as a GitHub **pre-release** — HACS only offers it to users who
  enabled **"Show beta versions"** for this repository (HACS → Signal Lights →
  ⋮ → Redownload → toggle "Show beta versions")
- `manifest.json` on `main` is **not** bumped; the beta version exists only
  inside the release zip
- Release notes fall back to the base version's changelog section, then to
  `## [Unreleased]`
- Tag betas on `main` — the release zip is built from the `main` branch

Tags that match neither `vX.Y.Z` nor `vX.Y.Z{a|b|rc}N` fail the workflow
before anything is published.

## Pull Request Process

1. Create a feature branch from `main`
2. Make your changes
3. Run all tests locally (see above)
4. Push and open a PR
5. CI runs automatically — all checks must pass
6. Squash merge when approved

## Code Style

- Python: follow Home Assistant conventions (type hints, async/await patterns)
- JavaScript: vanilla JS, no framework, use `_esc()` for all user data in innerHTML
- All signal names limited to 100 characters
- Notify targets must match `notify.<service_name>` pattern

## Architecture

- `engine.py` — pure Python signal priority queue (no HA dependencies, fully unit-testable)
- `coordinator.py` — HA integration layer (template tracking, light control, notifications)
- `store.py` — local JSON storage (`.storage/signal_lights_{entry_id}`)
- `services.py` — HA service handlers
- `websocket.py` — custom WS API for the Lovelace card
- `frontend/signal-lights-card.js` — Lovelace card (vanilla JS, WS-based data layer)
- `frontend/signal-lights-utils.js` — extracted pure functions for JS unit tests
