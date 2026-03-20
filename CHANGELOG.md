# Changelog

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
