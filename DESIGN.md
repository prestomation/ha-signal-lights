# Signal Lights — Home Assistant Integration

## Overview
A HA custom integration that manages a priority queue of "signals" (colored light notifications) across a set of registered physical lights. When conditions are met, the highest-priority active signal's color is pushed to all registered lights. When signals expire or conditions become false, the next signal takes over automatically. When no signals are active, lights turn off.

## Domain
`signal_lights`

## Architecture

### Three layers:
1. **Lights** — existing HA light entities registered as notification outputs. Each light has a configurable **brightness** (0-255) set at the light level.
2. **Signals** — conditions that want to show a color. Each has:
   - **Name** (user-friendly label)
   - **Priority** (integer, lower = higher priority, drag-to-reorder in UI)
   - **Color** (RGB tuple)
   - **Trigger type**: 
     - `event`: fires on state change, shows for a duration then expires
     - `condition`: active as long as a template evaluates to true (persistent)
   - **Trigger template** (Jinja2): for `event` type, triggers when template result changes to truthy; for `condition` type, signal is active whenever template is truthy
   - **Duration** (seconds, event type only): how long to show after triggering
   - **Per-light override** (optional): can specify which lights this signal applies to (default: all registered lights)
3. **Engine** — coordinator that:
   - Evaluates all signal conditions/timers
   - Maintains a priority stack
   - Pushes the winning color to each light
   - When a signal expires, immediately evaluates and pushes next winner
   - When no signals active → turns lights off

### Cycling (future, v2):
When multiple persistent signals share the same priority, cycle between them every N seconds. For v1, highest priority with lowest sort order wins.

### Transition Effects (future, v2):
Brief flash/pulse when a new higher-priority signal activates. For v1, instant color change.

## Config Flow

### Step 1: Integration setup
- Name the instance (default: "Signal Lights")

### Step 2: Options flow (post-setup, always accessible)
- **Lights tab**: Add/remove HA light entities, set per-light brightness
- **Signals tab**: Add/edit/remove/reorder signals
  - Each signal: name, color picker, priority (drag to reorder), trigger type, template, duration, optional light filter

## Storage
- Use HA `.storage` JSON (like Pawsistant pattern)
- Store: lights config, signals config with ordering

## Entities Created
- `sensor.signal_lights_active_signal` — name of currently active signal (or "none")
- `sensor.signal_lights_active_color` — current RGB hex color being displayed
- `sensor.signal_lights_queue_depth` — number of currently active signals
- `binary_sensor.signal_lights_active` — on when any signal is active

## Services
- `signal_lights.trigger_signal` — manually trigger an event-type signal by name
- `signal_lights.dismiss_signal` — manually dismiss/expire a signal
- `signal_lights.refresh` — force re-evaluation of all signals

## File Structure
```
custom_components/signal_lights/
├── __init__.py          # Setup, config entry, coordinator
├── manifest.json
├── const.py             # Constants
├── config_flow.py       # Config + options flow
├── coordinator.py       # Signal evaluation engine
├── store.py             # .storage JSON persistence
├── sensor.py            # Status sensors
├── binary_sensor.py     # Active binary sensor
├── services.py          # Service handlers
├── services.yaml        # Service definitions
├── strings.json         # UI strings
├── translations/
│   └── en.json
├── diagnostics.py       # HACS diagnostics
└── frontend/
    └── signal-lights-card.js  # Optional Lovelace card (v2)

hacs.json
pyproject.toml
LICENSE (MIT)
README.md
CHANGELOG.md
IDEAS.md
AGENTS.md
tests/
├── conftest.py
├── test_engine.py       # Unit tests for signal evaluation logic
├── integration/
│   ├── conftest.py      # Docker HA bootstrap (same pattern as Pawsistant)
│   ├── docker-compose.yml
│   ├── ha_config/
│   │   ├── configuration.yaml
│   │   └── .storage/
│   │       └── core.config_entries
│   └── test_lifecycle.py  # Integration tests
.github/
└── workflows/
    ├── hacs.yml
    ├── lint.yml
    ├── integration.yml
    └── release.yml
```

## Template Examples

### Event signal: "Tess arrives home"
```yaml
trigger_type: event
template: "{{ is_state('person.tess_corrigan', 'home') }}"
color: [255, 0, 255]  # magenta
duration: 60  # seconds
priority: 1
```

### Condition signal: "Back door open"
```yaml
trigger_type: condition
template: "{{ is_state('binary_sensor.back_door', 'on') }}"
color: [255, 0, 0]  # red
priority: 2
```

### Condition signal: "Low battery"
```yaml
trigger_type: condition
template: "{{ states('sensor.sharky_collar_battery') | int < 20 }}"
color: [255, 165, 0]  # orange
priority: 5
```

## Implementation Notes
- Use `async_track_template_result` for efficient template tracking (HA built-in)
- Coordinator polls on 30s interval as fallback, but template listeners handle most updates
- Light commands via `hass.services.async_call("light", "turn_on", ...)` with rgb_color and brightness
- All file I/O via `hass.async_add_executor_job` (no blocking)
- Config flow uses HA's multi-step options flow pattern
- Tests: unit tests for engine logic (pure Python, no HA deps), integration tests via Docker
