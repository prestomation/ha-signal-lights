# Changelog

## [1.1.0] - 2026-03-20

### Added
- **Trigger modes**: Entity equals state, Entity is on, Numeric above/below, Template (advanced)
  - Friendly entity picker UI instead of raw templates for common use cases
  - Stores trigger_mode and trigger_config alongside generated template
- **Lovelace configuration card** (`signal-lights-card.js`)
  - Full configuration UI: add/remove lights and signals
  - Drag-to-reorder signals for priority management
  - Color swatches, trigger descriptions, type badges
  - Live status showing which signal is currently active
  - Inline add signal form with trigger mode selector
  - Notification configuration section
  - Auto-registered as a Lovelace resource
- **Reorder signals**: New `signal_lights.reorder_signals` service
  - Drag-to-reorder in the Lovelace card
  - "⬆️ Reorder signals" option in the options flow
  - Accepts a list of signal names in desired priority order
- **Persistent notifications**
  - Optional notifications when signals become active
  - HA sidebar persistent notifications (updates in place via stable tag)
  - Mobile app notify targets support
  - Auto-clear when all signals are dismissed
  - New `signal_lights.configure_notifications` service
  - Configurable via options flow and Lovelace card

### Changed
- Priority is now determined by position (sort_order) instead of a numeric priority field
  - Lower sort_order = higher priority
  - Auto-assigned on signal creation (appended to end)
  - Legacy `priority` field kept for backward compatibility but ignored for ordering
- Options flow updated with trigger mode selector (replaces raw template input)
- Options flow menu now includes reorder and notification configuration
- Sensor `active_signal` now exposes full config data in attributes for the Lovelace card
- Engine sorts active signals by sort_order only (not priority + sort_order)

### Fixed
- Sort order re-indexed after signal removal to prevent gaps

## [1.0.0] - 2026-03-20

### Added
- Initial release
- Priority queue signal engine with event and condition triggers
- Template-based signal activation via `async_track_template_result`
- Per-light brightness configuration
- Per-light signal filtering
- Sensor entities: active signal, active color, queue depth
- Binary sensor: active state
- Services: trigger_signal, dismiss_signal, refresh
- `.storage` JSON persistence for lights and signals
- Config flow with options flow
- Diagnostics support
- Unit tests for engine logic
- Docker-based integration tests
- CI workflows: HACS validation, lint, integration tests, release
