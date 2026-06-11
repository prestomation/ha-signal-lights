# Changelog

## [Unreleased]

### Fixed
- **Adding/editing signals was broken on current Home Assistant releases**
  (#12, #13): template validation called `Template()` without the now-required
  `hass` argument, so every `add_signal`/`update_signal` call failed — and the
  failure was only logged, so the card's Save/Add buttons appeared to do
  nothing. Validation now passes `hass` (and actually compiles the template
  via `ensure_valid()`).
- **Service errors are now surfaced to the caller** (#12, #13): invalid
  trigger config, duplicate names, unknown signals/lights, etc. raise
  `ServiceValidationError` instead of logging silently, so the Lovelace card
  shows the real error in its toast and automations fail visibly.
- **Editing a signal's trigger now takes effect** (#13): `update_signal`
  regenerates the stored Jinja2 template when `trigger_mode`/`trigger_config`
  change (unless an explicit template is supplied). Previously the engine
  kept evaluating the old template.
- **Card re-renders after a successful save** (#13): the WS update that
  arrives while an edit/add form is open is intentionally buffered to avoid
  disrupting typing — but the card never re-rendered afterwards, leaving the
  edit panel open with stale data. Save/Add/Cancel now re-render from the
  buffered state.
- **Entity picker always usable** (#12): `ha-entity-picker` is lazy-loaded by
  the HA frontend and could be inert on dashboards that never loaded it. The
  card now force-loads it via the card helpers and, until it's available,
  renders a plain text input with entity-ID suggestions. Submitting without
  an entity now shows a clear validation message instead of a cryptic backend
  error.

### Added
- Self-managing Docker integration test harness: `pytest tests/integration`
  starts/stops the HA compose stack itself and restores seeded storage;
  includes an HA WebSocket client used to test services over the card's
  transport.
- Regression test suites for #12/#13 (frontend jsdom tests driving the real
  card element, plus Docker-backed service tests) and comprehensive service
  API integration tests.

## [1.2.0] - 2026-04-02

### Added
- **Signal cycling**: when multiple signals are active for the same light, the light automatically cycles through them in priority order. Default dwell time is 3 seconds; configurable via Settings → Integrations → Signal Lights → Configure → 🔄 Configure signal cycling.
- **Notifications list all active signals**: persistent and mobile notifications now show every active signal (one per line, highest priority first) instead of only the winner.

## [Unreleased] - 2026-03-20

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
