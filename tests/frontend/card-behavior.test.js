/**
 * Comprehensive behavior tests for the signal-lights-card element.
 *
 * Driven through the real custom element in jsdom with a FakeHass that
 * mirrors HA's WS message ordering (subscription events arrive before the
 * service-call promise resolves).
 */
import { describe, it, expect, afterEach } from 'vitest';
import {
  FakeHass,
  makeSnapshot,
  makeSignal,
  mountCard,
  flush,
  TEST_ENTRY_ID,
} from './helpers/fake-hass.js';

afterEach(() => {
  document.body.innerHTML = '';
});

/* ── Render states ──────────────────────────────────────────────────────── */

describe('render states', () => {
  it('shows a loading spinner until WS data arrives', async () => {
    const hass = new FakeHass(makeSnapshot());
    // Make the initial fetch hang
    hass.callWS = () => new Promise(() => {});
    const card = await mountCard(hass);
    expect(card.shadowRoot.querySelector('.loading-state')).toBeTruthy();
  });

  it('shows an admin error when the subscription is unauthorized', async () => {
    const hass = new FakeHass(makeSnapshot());
    const err = new Error('unauthorized');
    err.code = 'unauthorized';
    hass.callWS = () => Promise.reject(err);
    const card = await mountCard(hass);
    const text = card.shadowRoot.querySelector('.error-text');
    expect(text.textContent).toContain('Admin access required');
  });

  it('shows empty states when no lights or signals are configured', async () => {
    const hass = new FakeHass(makeSnapshot({ signals: [], lights: [] }));
    const card = await mountCard(hass);
    const empties = [...card.shadowRoot.querySelectorAll('.empty-state')].map((e) => e.textContent);
    expect(empties.join(' ')).toContain('No lights registered');
    expect(empties.join(' ')).toContain('No signals defined');
  });

  it('shows a not-found message when config_entry_id matches no entry', async () => {
    const hass = new FakeHass(makeSnapshot());
    const card = await mountCard(hass, { config_entry_id: '01XXXXXXXXXXXXXXXXXXXXXXXX' });
    expect(card.shadowRoot.textContent).toContain('entry not found');
  });
});

/* ── Status bar ─────────────────────────────────────────────────────────── */

describe('status bar', () => {
  it('shows "No active signal" when idle', async () => {
    const hass = new FakeHass(makeSnapshot());
    const card = await mountCard(hass);
    expect(card.shadowRoot.querySelector('.status-text').textContent).toBe('No active signal');
  });

  it('shows the active signal name and color', async () => {
    const hass = new FakeHass(makeSnapshot({
      active_signal: 'Door open',
      active_color: '#ff0000',
      active_signal_names: ['Door open'],
      queue_depth: 1,
      is_active: true,
    }));
    const card = await mountCard(hass);
    expect(card.shadowRoot.querySelector('.status-text').textContent).toBe('Door open');
    expect(card.shadowRoot.querySelector('.status-dot').style.background).toBe('rgb(255, 0, 0)');
  });

  it('shows queue badge and cycle badge when cycling through multiple signals', async () => {
    const hass = new FakeHass(makeSnapshot({
      active_signal: 'Door open',
      active_signal_names: ['Door open', 'Low battery'],
      queue_depth: 2,
      is_active: true,
      cycle_interval: 3,
    }));
    const card = await mountCard(hass);
    expect(card.shadowRoot.querySelector('.queue-badge').textContent).toContain('2 in queue');
    expect(card.shadowRoot.querySelector('.cycle-badge')).toBeTruthy();
  });

  it('updates the status bar from a pushed WS event without user action', async () => {
    const hass = new FakeHass(makeSnapshot());
    const card = await mountCard(hass);
    hass.snapshot[0].active_signal = 'Door open';
    hass.snapshot[0].active_signal_names = ['Door open'];
    hass.snapshot[0].is_active = true;
    hass.pushUpdate();
    await flush();
    expect(card.shadowRoot.querySelector('.status-text').textContent).toBe('Door open');
  });
});

/* ── Signal actions ─────────────────────────────────────────────────────── */

describe('signal actions', () => {
  it('trigger button calls trigger_signal with the entry id', async () => {
    const hass = new FakeHass(makeSnapshot({
      signals: [makeSignal({ trigger_type: 'event' })],
    }));
    const card = await mountCard(hass);
    card.shadowRoot.querySelector('.btn-trigger').click();
    await flush();
    const call = hass.serviceCalls.find((c) => c.service === 'trigger_signal');
    expect(call.data).toEqual({ name: 'Door open', config_entry_id: TEST_ENTRY_ID });
  });

  it('dismiss button appears for active signals and calls dismiss_signal', async () => {
    const hass = new FakeHass(makeSnapshot({
      active_signal: 'Door open',
      active_signal_names: ['Door open'],
      is_active: true,
    }));
    const card = await mountCard(hass);
    card.shadowRoot.querySelector('.btn-dismiss').click();
    await flush();
    expect(hass.serviceCalls.find((c) => c.service === 'dismiss_signal')).toBeTruthy();
  });

  it('remove requires a second confirming click', async () => {
    const hass = new FakeHass(makeSnapshot());
    hass.onServiceCall = (d, s, data) => {
      if (s === 'remove_signal') {
        hass.snapshot[0].signals = hass.snapshot[0].signals.filter((x) => x.name !== data.name);
      }
    };
    const card = await mountCard(hass);
    const btn = card.shadowRoot.querySelector('.signal-row .btn-remove');
    btn.click();
    await flush();
    expect(hass.serviceCalls.filter((c) => c.service === 'remove_signal')).toHaveLength(0);
    expect(btn.textContent).toBe('⚠️');
    btn.click();
    await flush();
    expect(hass.serviceCalls.filter((c) => c.service === 'remove_signal')).toHaveLength(1);
  });

  it('drag-and-drop reorders signals via reorder_signals', async () => {
    const hass = new FakeHass(makeSnapshot({
      signals: [
        makeSignal({ name: 'First', sort_order: 0 }),
        makeSignal({ name: 'Second', sort_order: 1 }),
      ],
    }));
    const card = await mountCard(hass);
    const rows = card.shadowRoot.querySelectorAll('.signal-row');

    const dataTransfer = { effectAllowed: '', dropEffect: '', setData() {}, getData() { return '0'; } };
    const dragStart = new Event('dragstart', { bubbles: true });
    dragStart.dataTransfer = dataTransfer;
    rows[0].dispatchEvent(dragStart);
    const drop = new Event('drop', { bubbles: true });
    drop.dataTransfer = dataTransfer;
    rows[1].dispatchEvent(drop);
    await flush();

    const call = hass.serviceCalls.find((c) => c.service === 'reorder_signals');
    expect(call.data.order).toEqual(['Second', 'First']);
  });
});

/* ── Edit form behavior ─────────────────────────────────────────────────── */

describe('edit form', () => {
  it('pre-populates fields from the signal definition', async () => {
    const hass = new FakeHass(makeSnapshot({
      signals: [makeSignal({ trigger_type: 'event', duration: 45 })],
    }));
    const card = await mountCard(hass);
    card.shadowRoot.querySelector('.btn-edit').click();
    await flush();
    const form = card.shadowRoot.querySelector('.edit-signal-form-container');
    expect(form.querySelector('#sl-edit-sig-name').value).toBe('Door open');
    expect(form.querySelector('#sl-edit-sig-color-r').value).toBe('255');
    expect(form.querySelector('#sl-edit-sig-entity').value).toBe('binary_sensor.front_door');
    expect(form.querySelector('#sl-edit-sig-state').value).toBe('on');
    expect(form.querySelector('#sl-edit-sig-duration').value).toBe('45');
  });

  it('preserves edits when switching trigger mode', async () => {
    const hass = new FakeHass(makeSnapshot());
    const card = await mountCard(hass);
    card.shadowRoot.querySelector('.btn-edit').click();
    await flush();
    let form = card.shadowRoot.querySelector('.edit-signal-form-container');
    form.querySelector('#sl-edit-sig-name').value = 'Renamed';
    const modeSelect = form.querySelector('#sl-edit-sig-trigger-mode');
    modeSelect.value = 'template';
    modeSelect.dispatchEvent(new Event('change'));
    await flush();
    form = card.shadowRoot.querySelector('.edit-signal-form-container');
    expect(form.querySelector('#sl-edit-sig-name').value).toBe('Renamed');
    expect(form.querySelector('#sl-edit-sig-template')).toBeTruthy();
  });

  it('cancel closes the form without calling any service', async () => {
    const hass = new FakeHass(makeSnapshot());
    const card = await mountCard(hass);
    card.shadowRoot.querySelector('.btn-edit').click();
    await flush();
    card.shadowRoot.querySelector('#sl-edit-sig-cancel').click();
    await flush();
    expect(card.shadowRoot.querySelector('.edit-signal-form-container')).toBeNull();
    expect(hass.serviceCalls.filter((c) => c.service === 'update_signal')).toHaveLength(0);
  });

  it('does not disrupt the open form when a WS update arrives, and applies it on cancel', async () => {
    const hass = new FakeHass(makeSnapshot());
    const card = await mountCard(hass);
    card.shadowRoot.querySelector('.btn-edit').click();
    await flush();
    const form = card.shadowRoot.querySelector('.edit-signal-form-container');
    form.querySelector('#sl-edit-sig-name').value = 'half-typed';

    // Another client adds a signal while the form is open
    hass.snapshot[0].signals.push(makeSignal({ name: 'From elsewhere', sort_order: 1 }));
    hass.pushUpdate();
    await flush();

    // Form (and the user's typing) must be untouched
    const formAfter = card.shadowRoot.querySelector('.edit-signal-form-container');
    expect(formAfter).toBe(form);
    expect(formAfter.querySelector('#sl-edit-sig-name').value).toBe('half-typed');

    // Closing the form applies the buffered update
    formAfter.querySelector('#sl-edit-sig-cancel').click();
    await flush();
    expect(card.shadowRoot.textContent).toContain('From elsewhere');
  });

  it('template mode save sends the template field', async () => {
    const hass = new FakeHass(makeSnapshot({
      signals: [makeSignal({
        trigger_mode: 'template',
        trigger_config: {},
        template: '{{ true }}',
      })],
    }));
    const card = await mountCard(hass);
    card.shadowRoot.querySelector('.btn-edit').click();
    await flush();
    const form = card.shadowRoot.querySelector('.edit-signal-form-container');
    form.querySelector('#sl-edit-sig-template').value = '{{ false }}';
    form.querySelector('#sl-edit-sig-save').click();
    await flush();
    const call = hass.serviceCalls.find((c) => c.service === 'update_signal');
    expect(call.data.template).toBe('{{ false }}');
    expect(call.data.trigger_mode).toBe('template');
  });
});

/* ── Notifications section ──────────────────────────────────────────────── */

describe('notifications', () => {
  it('lists notify services as checkboxes and saves the selection', async () => {
    const hass = new FakeHass(makeSnapshot());
    hass.services = { notify: { mobile_app_phone: {}, persistent_notification: {} } };
    const card = await mountCard(hass);

    const boxes = card.shadowRoot.querySelectorAll('#sl-notif-targets input[type="checkbox"]');
    expect(boxes).toHaveLength(2);

    card.shadowRoot.getElementById('sl-notif-enabled').click();
    boxes[0].click();
    card.shadowRoot.getElementById('sl-notif-save').click();
    await flush();

    const call = hass.serviceCalls.find((c) => c.service === 'configure_notifications');
    expect(call.data.enabled).toBe(true);
    expect(call.data.targets).toEqual(['notify.mobile_app_phone']);
  });

  it('falls back to a text input when no notify services exist', async () => {
    const hass = new FakeHass(makeSnapshot());
    const card = await mountCard(hass);
    const fallback = card.shadowRoot.getElementById('sl-notif-targets-text');
    expect(fallback).toBeTruthy();
    fallback.value = 'notify.a, notify.b';
    card.shadowRoot.getElementById('sl-notif-enabled').click();
    card.shadowRoot.getElementById('sl-notif-save').click();
    await flush();
    const call = hass.serviceCalls.find((c) => c.service === 'configure_notifications');
    expect(call.data.targets).toEqual(['notify.a', 'notify.b']);
  });
});

/* ── Lights section ─────────────────────────────────────────────────────── */

describe('lights', () => {
  it('renders registered lights with brightness', async () => {
    const hass = new FakeHass(makeSnapshot({
      lights: [{ entity_id: 'light.desk', brightness: 128 }],
    }));
    const card = await mountCard(hass);
    const row = card.shadowRoot.querySelector('.light-row');
    expect(row.textContent).toContain('light.desk');
    expect(row.textContent).toContain('Brightness: 128');
  });

  it('removing a light requires confirmation then calls remove_light', async () => {
    const hass = new FakeHass(makeSnapshot());
    hass.onServiceCall = (d, s, data) => {
      if (s === 'remove_light') {
        hass.snapshot[0].lights = hass.snapshot[0].lights.filter((l) => l.entity_id !== data.entity_id);
      }
    };
    const card = await mountCard(hass);
    const btn = card.shadowRoot.querySelector('.light-row .btn-remove');
    btn.click();
    await flush();
    expect(hass.serviceCalls.filter((c) => c.service === 'remove_light')).toHaveLength(0);
    btn.click();
    await flush();
    const call = hass.serviceCalls.find((c) => c.service === 'remove_light');
    expect(call.data.entity_id).toBe('light.desk');
  });
});

/* ── Multi-entry support ────────────────────────────────────────────────── */

describe('multiple setups', () => {
  it('targets the entry selected via config_entry_id', async () => {
    const second = makeSnapshot()[0];
    second.entry_id = '01KM50NFDVH65G8ADNG8K0MST8';
    second.title = 'Second';
    second.signals = [makeSignal({ name: 'Other signal', trigger_type: 'event' })];
    const hass = new FakeHass([...makeSnapshot(), second]);
    const card = await mountCard(hass, { config_entry_id: second.entry_id });

    expect(card.shadowRoot.textContent).toContain('Other signal');
    card.shadowRoot.querySelector('.btn-trigger').click();
    await flush();
    const call = hass.serviceCalls.find((c) => c.service === 'trigger_signal');
    expect(call.data.config_entry_id).toBe(second.entry_id);
  });
});
