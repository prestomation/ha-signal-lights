# Signal Lights

[![Integration Usage][integration-usage-shield]][integration-usage]

[![GitHub Downloads][downloads-shield]][releases]
[![GitHub Latest Downloads][downloads-latest-shield]][releases]
[![GitHub Release][releases-shield]][releases]
[![GitHub Release Date][release-date-shield]][releases]
[![GitHub Activity][commits-shield]][commits]
[![Coverage][coverage-shield]][coverage]
[![License][license-shield]](LICENSE)
[![hacs][hacsbadge]][hacs]
![Project Maintenance][maintenance-shield]
[![HACS Validation][hacs-validation-shield]][hacs-validation]
[![Validate][validate-shield]][validate]
[![Tests][tests-shield]][tests]
[![HA Version][ha-version-shield]][ha-version]

A Home Assistant custom integration that manages a **priority queue of colored light signals**. Register physical light entities as notification outputs, define signals with colors and priorities, and the engine automatically pushes the highest-priority active signal's color to your lights.

## How It Works

1. **Register lights** — Add existing HA light entities as signal outputs, each with a configurable brightness.
2. **Define signals** — Create signals with a name, color, and trigger:
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

### Lovelace Card (Recommended)

After installation, the custom **Signal Lights Card** is automatically registered. Add it to your dashboard:

1. Edit your dashboard → Add Card → Search "Signal Lights"
2. The card provides full configuration UI:
   - **Lights section**: Add/remove lights with brightness sliders
   - **Signals section**: Add/remove signals, drag-to-reorder priorities, trigger/dismiss
   - **Notifications section**: Enable/disable persistent notifications and mobile app targets

### Options Flow

You can also configure via Settings → Devices & Services → Signal Lights → Configure:

- ➕ Add a light / ➕ Add a signal
- ➖ Remove a light / ➖ Remove a signal
- ⬆️ Reorder signals
- 🔔 Configure notifications

### Trigger Modes

When adding a signal, choose a trigger mode:

| Mode | Description | Example |
|------|-------------|---------|
| **Entity equals state** | Matches when an entity has a specific state | `binary_sensor.front_door` = `on` |
| **Entity is on** | Matches when a binary entity is on | `binary_sensor.motion_detector` is on |
| **Numeric above/below** | Matches when a sensor value crosses a threshold | `sensor.battery_level` < `20` |
| **Template (advanced)** | Raw Jinja2 template for complex conditions | `{{ states('sensor.x') \| int > 5 }}` |

### Signal Examples

#### Condition signal: "Front door open"
```yaml
name: Front Door Open
color: [255, 0, 0]  # red
trigger_type: condition
trigger_mode: entity_equals
trigger_config:
  entity_id: binary_sensor.front_door
  state: "on"
```

#### Event signal: "Person A arrives home"
```yaml
name: Person A Home
color: [255, 0, 255]  # magenta
trigger_type: event
trigger_mode: entity_equals
trigger_config:
  entity_id: person.a
  state: "home"
duration: 60  # show for 60 seconds
```

#### Condition signal: "Low battery alert"
```yaml
name: Low Battery
color: [255, 165, 0]  # orange
trigger_type: condition
trigger_mode: numeric_threshold
trigger_config:
  entity_id: sensor.device_battery
  threshold: 20
  direction: below
```

## Notifications

Signal Lights can send persistent notifications when signals are active:

- **HA Sidebar**: Uses `persistent_notification.create` with a stable tag (updates in place)
- **Mobile apps**: Sends to configured notify targets (e.g., `notify.mobile_app_phone`)
- **Auto-clear**: When all signals clear, notifications are dismissed automatically

Configure via the Lovelace card or the options flow.

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
| `signal_lights.add_light` | Register a light entity as a signal output |
| `signal_lights.remove_light` | Unregister a light entity |
| `signal_lights.add_signal` | Add a signal definition (supports trigger modes) |
| `signal_lights.remove_signal` | Remove a signal definition by name |
| `signal_lights.reorder_signals` | Reorder signals by providing a name list |
| `signal_lights.configure_notifications` | Enable/disable notifications and set targets |

## How Priority Works

- Signals are ordered by position (first = highest priority)
- Priority is set by drag-to-reorder in the card or via the reorder service
- The highest-priority active signal wins per light
- Signals can optionally be filtered to specific lights
- When no signals are active, lights turn off

## License

MIT — see [LICENSE](LICENSE).

[integration-usage-shield]: https://img.shields.io/badge/dynamic/json?color=41BDF5&logo=home-assistant&label=integration%20usage&suffix=%20installs&cacheSeconds=15600&url=https%3A%2F%2Fanalytics.home-assistant.io%2Fcustom_integrations.json&query=%24.signal_lights.total&style=for-the-badge
[integration-usage]: https://analytics.home-assistant.io/custom_integrations.json
[commits-shield]: https://img.shields.io/github/last-commit/prestomation/ha-signal-lights?style=for-the-badge
[commits]: https://github.com/prestomation/ha-signal-lights/commits/main
[hacs]: https://github.com/custom-components/hacs
[hacsbadge]: https://img.shields.io/badge/HACS-Custom-orange.svg?style=for-the-badge
[license-shield]: https://img.shields.io/github/license/prestomation/ha-signal-lights.svg?style=for-the-badge
[maintenance-shield]: https://img.shields.io/badge/Maintainers-%40prestomation-blue.svg?style=for-the-badge
[downloads-shield]: https://img.shields.io/github/downloads/prestomation/ha-signal-lights/total.svg?style=for-the-badge
[downloads-latest-shield]: https://img.shields.io/github/downloads-pre/prestomation/ha-signal-lights/latest/total?style=for-the-badge
[releases-shield]: https://img.shields.io/github/release/prestomation/ha-signal-lights.svg?style=for-the-badge
[release-date-shield]: https://img.shields.io/github/release-date/prestomation/ha-signal-lights?style=for-the-badge
[releases]: https://github.com/prestomation/ha-signal-lights/releases
[coverage]: https://htmlpreview.github.io/?https://github.com/prestomation/ha-signal-lights/blob/python-coverage-comment-action-data/htmlcov/index.html
[coverage-shield]: https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/prestomation/ha-signal-lights/python-coverage-comment-action-data/endpoint.json&style=for-the-badge
[hacs-validation-shield]: https://github.com/prestomation/ha-signal-lights/actions/workflows/hacs.yml/badge.svg
[hacs-validation]: https://github.com/prestomation/ha-signal-lights/actions/workflows/hacs.yml
[validate-shield]: https://github.com/prestomation/ha-signal-lights/actions/workflows/lint.yml/badge.svg
[validate]: https://github.com/prestomation/ha-signal-lights/actions/workflows/lint.yml
[tests-shield]: https://github.com/prestomation/ha-signal-lights/actions/workflows/integration.yml/badge.svg
[tests]: https://github.com/prestomation/ha-signal-lights/actions/workflows/integration.yml
[ha-version-shield]: https://img.shields.io/badge/Home%20Assistant-2024.1%2B-blue.svg?style=for-the-badge
[ha-version]: https://www.home-assistant.io/
