# Signal Lights

[![HACS Validation](https://github.com/prestomation/ha-signal-lights/actions/workflows/hacs.yml/badge.svg)](https://github.com/prestomation/ha-signal-lights/actions/workflows/hacs.yml)
[![Lint](https://github.com/prestomation/ha-signal-lights/actions/workflows/lint.yml/badge.svg)](https://github.com/prestomation/ha-signal-lights/actions/workflows/lint.yml)
[![Integration Tests](https://github.com/prestomation/ha-signal-lights/actions/workflows/integration.yml/badge.svg)](https://github.com/prestomation/ha-signal-lights/actions/workflows/integration.yml)

A Home Assistant custom integration that manages a **priority queue of colored light signals**. Register physical light entities as notification outputs, define signals with colors and priorities, and the engine automatically pushes the highest-priority active signal's color to your lights.

## How It Works

1. **Register lights** — Add existing HA light entities as signal outputs, each with a configurable brightness.
2. **Define signals** — Create signals with a name, priority, color, and trigger:
   - **Event signals**: Fire when a template becomes truthy, show for a set duration, then expire.
   - **Condition signals**: Stay active as long as a template evaluates to true.
3. **Engine evaluates** — The highest-priority active signal wins and its color is pushed to your lights. When it expires or is dismissed, the next one takes over. When nothing is active, lights turn off.

## Installation

### HACS (Recommended)

1. Add this repository as a custom repository in HACS
2. Search for "Signal Lights" and install
3. Restart Home Assistant
4. Go to Settings → Devices & Services → Add Integration → Signal Lights

### Manual

1. Copy `custom_components/signal_lights/` to your HA `config/custom_components/` directory
2. Restart Home Assistant
3. Add the integration via Settings → Devices & Services

## Configuration

After installing, configure lights and signals via the `.storage/signal_lights` file or programmatically via service calls.

### Signal Examples

#### Event signal: "Tess arrives home"
```yaml
name: Tess Home
priority: 1
color: [255, 0, 255]  # magenta
trigger_type: event
template: "{{ is_state('person.tess', 'home') }}"
duration: 60  # show for 60 seconds
```

#### Condition signal: "Back door open"
```yaml
name: Door Open
priority: 2
color: [255, 0, 0]  # red
trigger_type: condition
template: "{{ is_state('binary_sensor.back_door', 'on') }}"
```

#### Condition signal: "Sharky's collar battery low"
```yaml
name: Low Battery
priority: 5
color: [255, 165, 0]  # orange
trigger_type: condition
template: "{{ states('sensor.sharky_collar_battery') | int < 20 }}"
```

## Entities

| Entity | Description |
|--------|-------------|
| `sensor.signal_lights_active_signal` | Name of the current winning signal (or "none") |
| `sensor.signal_lights_active_color` | Hex color of the current signal |
| `sensor.signal_lights_queue_depth` | Number of currently active signals |
| `binary_sensor.signal_lights_active` | On when any signal is active |

## Services

| Service | Description |
|---------|-------------|
| `signal_lights.trigger_signal` | Manually fire an event signal by name |
| `signal_lights.dismiss_signal` | Dismiss an active signal |
| `signal_lights.refresh` | Force re-evaluation of all signals |

## How Priority Works

- Each signal has an integer priority (lower = higher priority)
- The highest-priority active signal wins per light
- Ties are broken by sort order
- Signals can optionally be filtered to specific lights
- When no signals are active, lights turn off

## License

MIT — see [LICENSE](LICENSE).
