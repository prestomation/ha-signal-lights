# Ideas & Future Features

## v2 Features

### Signal Cycling
When multiple condition signals share the same priority, cycle between them every N seconds instead of picking one by sort order. Configurable cycle interval per priority level.

### Transition Effects
Brief flash or pulse when a new higher-priority signal activates:
- Quick white flash before switching to the new color
- Smooth fade transition between colors
- Configurable per-signal transition mode

### Lovelace Card
Custom card (`signal-lights-card.js`) showing:
- Current active signal with color preview
- Active signal queue with priorities
- Drag-to-reorder signals
- Add/edit/remove signals inline
- Light registration with brightness sliders
- Color picker for signal colors

## UI/UX Improvements

### Options Flow Enhancements
- Full CRUD for lights and signals in the options flow
- Entity picker for light selection
- Color wheel for signal color
- Template editor with live preview
- Drag-to-reorder for signal priority

### Per-Signal Scheduling
- Time-of-day restrictions (e.g., only show between 6am-10pm)
- Day-of-week restrictions
- Quiet hours mode that suppresses lower-priority signals

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

### Notification Integration
- Optionally send HA notifications when high-priority signals activate
- Mobile app push when critical signals fire
- TTS announcements paired with signal activation

## Technical Debt

### Template Caching
- Cache parsed templates to avoid re-parsing on every evaluation
- Benchmark template evaluation performance with many signals

### State Restoration
- Restore active event signals across HA restarts (currently lost)
- Persist event signal state with remaining duration
