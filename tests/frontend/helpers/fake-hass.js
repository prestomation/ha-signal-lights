/**
 * Test harness for the Signal Lights card element.
 *
 * FakeHass emulates the slice of the `hass` object the card uses, including
 * the *message ordering* of real Home Assistant: when a service call mutates
 * config, the WS subscription event is delivered BEFORE the service-call
 * promise resolves (HA sends the coordinator-update event message during
 * handler execution, then the call_service result afterwards).
 */

// jsdom does not implement CSS.escape — polyfill (browsers all have it).
if (typeof CSS === 'undefined' || !CSS.escape) {
  globalThis.CSS = globalThis.CSS || {};
  globalThis.CSS.escape = (v) => String(v).replace(/[^a-zA-Z0-9_ -￿-]/g, (c) => `\\${c}`);
}

export const TEST_ENTRY_ID = '01KM50NFDVH65G8ADNG8K0MST9';

export function makeSignal(overrides = {}) {
  return {
    name: 'Door open',
    sort_order: 0,
    color: [255, 0, 0],
    trigger_type: 'condition',
    trigger_mode: 'entity_equals',
    trigger_config: { entity_id: 'binary_sensor.front_door', state: 'on' },
    template: "{{ is_state('binary_sensor.front_door', 'on') }}",
    duration: 0,
    light_filter: [],
    ...overrides,
  };
}

export function makeSnapshot(overrides = {}) {
  return [{
    entry_id: TEST_ENTRY_ID,
    title: 'Signal Lights',
    signals: [makeSignal()],
    lights: [{ entity_id: 'light.desk', brightness: 255 }],
    notifications: { enabled: false, targets: [] },
    active_signal: 'none',
    active_color: '#000000',
    active_signal_names: [],
    queue_depth: 0,
    is_active: false,
    signal_errors: {},
    cycle_interval: 0,
    cycle_index: 0,
    ...overrides,
  }];
}

export class FakeHass {
  constructor(snapshot) {
    this.snapshot = snapshot;
    this.states = {};
    this.services = {};
    this.serviceCalls = [];
    this.subscribers = [];
    /** Optional hook: (domain, service, data) => void — mutate this.snapshot
     *  to emulate the backend applying the change. */
    this.onServiceCall = null;
    /** When set, callService rejects with this error (emulates a backend
     *  validation failure surfaced through the WS API). */
    this.serviceError = null;
    this.connection = {
      subscribeMessage: (cb) => {
        this.subscribers.push(cb);
        return Promise.resolve(() => {
          this.subscribers = this.subscribers.filter((s) => s !== cb);
        });
      },
    };
  }

  callWS() {
    return Promise.resolve(structuredClone(this.snapshot));
  }

  pushUpdate() {
    for (const cb of [...this.subscribers]) cb(structuredClone(this.snapshot));
  }

  async callService(domain, service, data) {
    this.serviceCalls.push({ domain, service, data });
    if (this.serviceError) throw this.serviceError;
    if (this.onServiceCall) this.onServiceCall(domain, service, data);
    // Deliver the subscription event BEFORE the service promise resolves,
    // mirroring real HA WS message ordering.
    this.pushUpdate();
  }
}

/** Create a card element wired to a FakeHass and attached to the DOM. */
export async function mountCard(hass, config = {}) {
  // Import side effect: defines the custom elements (once per test run).
  await import('../../../custom_components/signal_lights/frontend/signal-lights-card.js');
  const card = document.createElement('signal-lights-card');
  card.setConfig({ type: 'custom:signal-lights-card', ...config });
  card.hass = hass;
  document.body.appendChild(card);
  await flush();
  return card;
}

/** Flush pending microtasks + zero-delay timers. */
export async function flush() {
  for (let i = 0; i < 5; i++) {
    await new Promise((r) => setTimeout(r, 0));
  }
}
