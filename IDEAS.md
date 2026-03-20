# Ideas & Future Features

## Completed in v1.1.0

- ~~Lovelace Card~~ — Custom card with full configuration UI, drag-to-reorder, color swatches
- ~~Entity picker trigger modes~~ — entity_equals, entity_on, numeric_threshold, template
- ~~Drag-to-reorder signals~~ — HTML5 drag and drop in the card
- ~~Options flow reorder step~~ — "⬆️ Reorder signals" in the menu
- ~~Persistent notifications~~ — HA sidebar + mobile app notify targets

## v2 Features

### Signal Cycling
When multiple condition signals share the same sort_order, cycle between them every N seconds instead of picking one statically. Configurable cycle interval per position.

### Transition Effects
Brief flash or pulse when a new higher-priority signal activates:
- Quick white flash before switching to the new color
- Smooth fade transition between colors
- Configurable per-signal transition mode

### Card Enhancements
- Inline signal editing (change color, trigger, name without removing)
- Template live preview in the card
- Signal history timeline showing when signals activated/deactivated
- Brightness slider per-light directly in the card
- Entity autocomplete in the add signal form (requires HA entity picker web component)

## UI/UX Improvements

### Per-Signal Scheduling
- Time-of-day restrictions (e.g., only show between 6am-10pm)
- Day-of-week restrictions
- Quiet hours mode that suppresses lower-priority signals

### Signal Templates Library
- Pre-built signal templates for common use cases (door open, battery low, person arrives)
- One-click signal creation from templates

## Engine Improvements

### Signal Groups
- Group signals into categories (security, comfort, info)
- Per-group priority caps
- Group-level mute/unmute

### History & Analytics
- Track signal activation history
- Dashboard showing which signals fire most frequently
- Duration tracking per signal

### Multi-Instance Support
- Multiple Signal Lights instances for different rooms/zones
- Cross-instance signal forwarding

### Webhook Triggers
- HTTP webhook to trigger/dismiss signals from external systems
- MQTT support for signal control

### Notification Enhancements
- Per-signal notification override (some signals notify, some don't)
- Notification cooldown / rate limiting
- TTS announcements paired with signal activation
- Custom notification message templates per signal

## Technical Debt

### Template Caching
- Cache parsed templates to avoid re-parsing on every evaluation
- Benchmark template evaluation performance with many signals

### State Restoration
- Restore active event signals across HA restarts (currently lost)
- Persist event signal state with remaining duration

### Card Testing
- Automated browser tests for the Lovelace card
- Visual regression tests for card styling
