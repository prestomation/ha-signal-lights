# AGENTS.md — Signal Lights

## What This Is

A Home Assistant custom integration that manages a priority queue of colored
light signals. Register physical HA light entities as outputs, define signals
with colors and priorities, and the engine pushes the winning color to lights.

## Repo Structure

```
custom_components/signal_lights/
├── __init__.py          # Entry setup, service registration
├── manifest.json        # HA integration manifest
├── const.py             # Domain, platforms, storage constants
├── config_flow.py       # Config flow + options flow
├── coordinator.py       # DataUpdateCoordinator + template tracking
├── engine.py            # Pure Python signal evaluation engine
├── store.py             # .storage JSON persistence
├── sensor.py            # Status sensors (active signal, color, queue depth)
├── binary_sensor.py     # Active binary sensor
├── services.py          # Service handlers
├── services.yaml        # Service definitions for HA UI
├── diagnostics.py       # HACS diagnostics support
├── strings.json         # UI strings
└── translations/en.json # English translations

tests/
├── test_engine.py                    # Unit tests (pure Python)
└── integration/
    ├── conftest.py                   # Docker HA bootstrap helpers
    ├── docker-compose.yml            # HA container for tests
    ├── ha_config/                    # Test HA config
    │   ├── configuration.yaml
    │   └── .storage/
    │       ├── core.config_entries   # Pre-seeded config entry
    │       └── signal_lights         # Pre-seeded test signals
    └── test_lifecycle.py             # Integration tests
```

## Key Design Decisions

- **engine.py is pure Python** — no HA imports, fully unit-testable
- **Template tracking via async_track_template_result** — efficient, event-driven
- **30s fallback polling** — catches expired event signals
- **Per-light filtering** — signals can target specific lights
- **Sort order tie-breaking** — deterministic when priorities match

## Codeowner

@prestomation

## HA Compatibility

- Minimum version: 2024.1
- IoT class: local_push
- No external dependencies
