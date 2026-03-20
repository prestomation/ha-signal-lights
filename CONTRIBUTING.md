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
```bash
cd tests/integration
docker compose up -d
bash ../../scripts/wait-for-ha.sh
python -m pytest . -v --tb=short --timeout=300
docker compose down -v
```

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
