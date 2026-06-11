/**
 * Regression tests for reported GitHub issues.
 *
 * Issue #13 — "Can't save changes on the Lovelace card": pressing Save in the
 * signal edit panel appeared to do nothing. The WS update event arrives while
 * the edit form is open (the card ignores it to avoid disrupting the form),
 * and after the service call resolved the card never re-rendered — so the
 * panel stayed open showing stale data.
 *
 * Issue #12 — "Not able to add signal": `ha-entity-picker` is a lazy-loaded
 * HA element; on dashboards where nothing has loaded it, the picker renders
 * inert and no entity can be selected. Submitting then sends an empty
 * entity_id which the backend rejects with a cryptic voluptuous error.
 */
import { describe, it, expect, afterEach } from 'vitest';
import {
  FakeHass,
  makeSnapshot,
  makeSignal,
  mountCard,
  flush,
} from './helpers/fake-hass.js';

afterEach(() => {
  document.body.innerHTML = '';
});

/* ── Issue #13: Save in the signal edit panel ───────────────────────────── */

describe('issue #13 — saving signal edits from the card', () => {
  async function openEditForm(card) {
    card.shadowRoot.querySelector('.btn-edit[data-name="Door open"]').click();
    await flush();
    const form = card.shadowRoot.querySelector('.edit-signal-form-container');
    expect(form, 'edit form should open').toBeTruthy();
    return form;
  }

  it('closes the edit panel and shows the new color after Save', async () => {
    const hass = new FakeHass(makeSnapshot());
    // Emulate the backend applying an update_signal call.
    hass.onServiceCall = (domain, service, data) => {
      if (service !== 'update_signal') return;
      const sig = hass.snapshot[0].signals.find((s) => s.name === data.name);
      Object.assign(sig, {
        color: data.color,
        trigger_type: data.trigger_type,
        trigger_mode: data.trigger_mode,
        trigger_config: data.trigger_config,
      });
    };
    const card = await mountCard(hass);
    const form = await openEditForm(card);

    form.querySelector('#sl-edit-sig-color-r').value = '0';
    form.querySelector('#sl-edit-sig-color-g').value = '255';
    form.querySelector('#sl-edit-sig-color-b').value = '0';
    form.querySelector('#sl-edit-sig-save').click();
    await flush();

    // The service must have been called with the new color…
    const call = hass.serviceCalls.find((c) => c.service === 'update_signal');
    expect(call).toBeTruthy();
    expect(call.data.color).toEqual([0, 255, 0]);

    // …the edit panel must close…
    expect(card.shadowRoot.querySelector('.edit-signal-form-container')).toBeNull();

    // …and the signal row must show the updated color swatch.
    const swatch = card.shadowRoot.querySelector('.signal-row .color-swatch');
    expect(swatch.style.background).toBe('rgb(0, 255, 0)');
  });

  it('closes the edit panel and shows the new name after a rename', async () => {
    const hass = new FakeHass(makeSnapshot());
    hass.onServiceCall = (domain, service, data) => {
      if (service !== 'update_signal') return;
      const sig = hass.snapshot[0].signals.find((s) => s.name === data.name);
      if (data.new_name) sig.name = data.new_name;
    };
    const card = await mountCard(hass);
    const form = await openEditForm(card);

    form.querySelector('#sl-edit-sig-name').value = 'Back door open';
    form.querySelector('#sl-edit-sig-save').click();
    await flush();

    const call = hass.serviceCalls.find((c) => c.service === 'update_signal');
    expect(call.data.new_name).toBe('Back door open');
    expect(card.shadowRoot.querySelector('.edit-signal-form-container')).toBeNull();
    const names = [...card.shadowRoot.querySelectorAll('.signal-row .item-name')]
      .map((el) => el.textContent);
    expect(names.join(' ')).toContain('Back door open');
  });

  it('shows an error toast and keeps the form open when the backend rejects the save', async () => {
    const hass = new FakeHass(makeSnapshot());
    hass.serviceError = new Error('A signal named "Back door open" already exists');
    const card = await mountCard(hass);
    const form = await openEditForm(card);

    form.querySelector('#sl-edit-sig-name').value = 'Back door open';
    form.querySelector('#sl-edit-sig-save').click();
    await flush();

    const toast = card.shadowRoot.getElementById('sl-error-toast');
    expect(toast.style.display).not.toBe('none');
    expect(toast.textContent).toContain('already exists');
    // Form stays open so the user can correct the input.
    expect(card.shadowRoot.querySelector('.edit-signal-form-container')).toBeTruthy();
  });
});

/* ── Issue #13 (same root cause): add flows never refresh the list ──────── */

describe('issue #13 — add signal/light flows refresh the card', () => {
  it('shows the newly added signal in the list after Add Signal', async () => {
    const hass = new FakeHass(makeSnapshot());
    hass.onServiceCall = (domain, service, data) => {
      if (service !== 'add_signal') return;
      hass.snapshot[0].signals.push(makeSignal({
        name: data.name,
        sort_order: hass.snapshot[0].signals.length,
        trigger_mode: data.trigger_mode,
        trigger_config: data.trigger_config,
      }));
    };
    const card = await mountCard(hass);

    card.shadowRoot.getElementById('sl-add-signal-btn').click();
    await flush();
    const form = card.shadowRoot.getElementById('sl-add-signal-form');
    form.querySelector('#sl-sig-name').value = 'Garage open';
    const entityField = form.querySelector('#sl-sig-entity');
    entityField.value = 'binary_sensor.garage';
    form.querySelector('#sl-sig-state').value = 'on';
    form.querySelector('#sl-add-signal-submit').click();
    await flush();

    const call = hass.serviceCalls.find((c) => c.service === 'add_signal');
    expect(call).toBeTruthy();
    expect(call.data.trigger_config.entity_id).toBe('binary_sensor.garage');

    const names = [...card.shadowRoot.querySelectorAll('.signal-row .item-name')]
      .map((el) => el.textContent).join(' ');
    expect(names).toContain('Garage open');
  });

  it('shows the newly added light in the list after Add Light', async () => {
    const hass = new FakeHass(makeSnapshot());
    hass.onServiceCall = (domain, service, data) => {
      if (service !== 'add_light') return;
      hass.snapshot[0].lights.push({ entity_id: data.entity_id, brightness: data.brightness });
    };
    const card = await mountCard(hass);

    card.shadowRoot.getElementById('sl-add-light-btn').click();
    await flush();
    const form = card.shadowRoot.getElementById('sl-add-light-form');
    form.querySelector('#sl-new-light-entity').value = 'light.kitchen';
    form.querySelector('#sl-add-light-submit').click();
    await flush();

    const rows = [...card.shadowRoot.querySelectorAll('.light-row .item-name')]
      .map((el) => el.textContent).join(' ');
    expect(rows).toContain('light.kitchen');
  });
});

/* ── Issue #12: entity picker unavailable / empty entity submitted ──────── */

describe('issue #12 — adding a signal when ha-entity-picker is unavailable', () => {
  it('renders a usable text input fallback when ha-entity-picker is not registered', async () => {
    // jsdom (like an HA dashboard that never lazy-loaded the picker) has no
    // ha-entity-picker definition.
    expect(customElements.get('ha-entity-picker')).toBeUndefined();

    const hass = new FakeHass(makeSnapshot());
    hass.states = {
      'binary_sensor.garage': { entity_id: 'binary_sensor.garage', attributes: {} },
      'light.kitchen': { entity_id: 'light.kitchen', attributes: {} },
    };
    const card = await mountCard(hass);

    card.shadowRoot.getElementById('sl-add-signal-btn').click();
    await flush();
    const form = card.shadowRoot.getElementById('sl-add-signal-form');
    const entityField = form.querySelector('#sl-sig-entity');
    expect(entityField, 'entity field should exist').toBeTruthy();
    // Must be a native input the user can actually type into — not an inert
    // unknown element.
    expect(entityField.tagName).toBe('INPUT');
  });

  it('offers known entities as suggestions in the fallback input', async () => {
    const hass = new FakeHass(makeSnapshot());
    hass.states = {
      'binary_sensor.garage': { entity_id: 'binary_sensor.garage', attributes: {} },
      'sensor.temperature': { entity_id: 'sensor.temperature', attributes: {} },
    };
    const card = await mountCard(hass);

    card.shadowRoot.getElementById('sl-add-signal-btn').click();
    await flush();
    const form = card.shadowRoot.getElementById('sl-add-signal-form');
    const options = [...form.querySelectorAll('datalist option')].map((o) => o.value);
    expect(options).toContain('binary_sensor.garage');
  });

  it('shows a clear validation error instead of calling the service when no entity is set', async () => {
    const hass = new FakeHass(makeSnapshot());
    const card = await mountCard(hass);

    card.shadowRoot.getElementById('sl-add-signal-btn').click();
    await flush();
    const form = card.shadowRoot.getElementById('sl-add-signal-form');
    form.querySelector('#sl-sig-name').value = 'My signal';
    // Entity intentionally left empty.
    form.querySelector('#sl-add-signal-submit').click();
    await flush();

    expect(hass.serviceCalls.filter((c) => c.service === 'add_signal')).toHaveLength(0);
    const toast = card.shadowRoot.getElementById('sl-error-toast');
    expect(toast.style.display).not.toBe('none');
    expect(toast.textContent.toLowerCase()).toContain('entity');
  });

  it('shows a clear validation error when saving an edit with the entity cleared', async () => {
    const hass = new FakeHass(makeSnapshot());
    const card = await mountCard(hass);

    card.shadowRoot.querySelector('.btn-edit[data-name="Door open"]').click();
    await flush();
    const form = card.shadowRoot.querySelector('.edit-signal-form-container');
    form.querySelector('#sl-edit-sig-entity').value = '';
    form.querySelector('#sl-edit-sig-save').click();
    await flush();

    expect(hass.serviceCalls.filter((c) => c.service === 'update_signal')).toHaveLength(0);
    const toast = card.shadowRoot.getElementById('sl-error-toast');
    expect(toast.style.display).not.toBe('none');
    expect(toast.textContent.toLowerCase()).toContain('entity');
  });
});
