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

Releases are produced by merging a PR that bumps the version — on the merge to
`main`, the Release workflow reads the version from `manifest.json`, validates
it, builds `signal_lights.zip`, tags the commit, and publishes the GitHub
release automatically. No manual `git tag`. No commits back to `main` from CI.
The version in `manifest.json` is the single source of truth.

### Full release

Open a PR with exactly these changes and merge it:

- `custom_components/signal_lights/manifest.json` — bump `version` to `X.Y.Z`
- `CHANGELOG.md` — add a `## [X.Y.Z] - YYYY-MM-DD` section

On merge, the workflow verifies a matching `## [X.Y.Z]` changelog section
exists, builds the zip, pushes tag `vX.Y.Z`, and creates the GitHub release
(release notes come from that changelog section). All HACS users are offered
the update. If tag `vX.Y.Z` already exists, the workflow is a no-op.

### Beta release

Same flow, using a PEP 440 pre-release version (`bN` beta, `aN` alpha, `rcN`
release candidate):

- `custom_components/signal_lights/manifest.json` — bump `version` to `X.Y.ZbN` (e.g. `1.4.0b1`)
- `CHANGELOG.md` — add a `## [1.4.0b1] - YYYY-MM-DD` section

CI recognizes the pre-release version string and publishes a GitHub
**pre-release** — HACS only offers it to users who enabled **"Show beta
versions"** for this repository (HACS → Signal Lights → ⋮ → Redownload →
toggle "Show beta versions"). Iterate with `b2`, `b3`, … as needed (each its
own PR, release, and `## [X.Y.ZbN]` changelog section), then cut the final
`X.Y.Z` with a normal bump. The beta version lives in `main`'s `manifest.json`
until that final bump.

A malformed `version` (matching neither `X.Y.Z` nor `X.Y.Z{a|b|rc}N`) fails the
workflow before anything is published.

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
