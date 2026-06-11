/**
 * Entity picker loading behavior (issue #12).
 *
 * Separate test file: customElements.define is irreversible within a jsdom
 * environment, so the "picker available" scenarios live here while the
 * fallback scenarios live in card-issues.test.js.
 */
import { describe, it, expect, afterEach } from 'vitest';
import { FakeHass, makeSnapshot, mountCard, flush } from './helpers/fake-hass.js';

afterEach(() => {
  document.body.innerHTML = '';
  delete window.loadCardHelpers;
});

function defineStubPicker() {
  if (!customElements.get('ha-entity-picker')) {
    customElements.define('ha-entity-picker', class extends HTMLElement {});
  }
}

describe('entity picker lazy-load upgrade', () => {
  it('starts with the fallback input, then swaps in ha-entity-picker once loaded, preserving typed value', async () => {
    expect(customElements.get('ha-entity-picker')).toBeUndefined();

    // Emulate HA's card helpers: loading the entities-card editor registers
    // ha-entity-picker.
    window.loadCardHelpers = async () => ({
      createCardElement: async () => ({
        constructor: {
          getConfigElement: async () => {
            defineStubPicker();
          },
        },
      }),
    });

    const hass = new FakeHass(makeSnapshot());
    const card = await mountCard(hass);
    card.shadowRoot.getElementById('sl-add-signal-btn').click();

    // Immediately after opening, the fallback input is present and usable.
    const form = card.shadowRoot.getElementById('sl-add-signal-form');
    const input = form.querySelector('#sl-sig-entity');
    expect(input.tagName).toBe('INPUT');
    input.value = 'binary_sensor.typed_by_user';

    await flush();

    // After the helpers resolve, the real picker replaces the fallback and
    // keeps the user's typed value.
    const upgraded = form.querySelector('#sl-sig-entity');
    expect(upgraded.tagName).toBe('HA-ENTITY-PICKER');
    expect(upgraded.value).toBe('binary_sensor.typed_by_user');
  });

  it('uses ha-entity-picker directly when it is already registered', async () => {
    defineStubPicker();
    const hass = new FakeHass(makeSnapshot());
    const card = await mountCard(hass);

    card.shadowRoot.getElementById('sl-add-signal-btn').click();
    await flush();
    const form = card.shadowRoot.getElementById('sl-add-signal-form');
    const picker = form.querySelector('#sl-sig-entity');
    expect(picker.tagName).toBe('HA-ENTITY-PICKER');
    expect(picker.allowCustomEntity).toBe(true);
  });

  it('pre-populates the picker with the existing entity in the edit form', async () => {
    defineStubPicker();
    const hass = new FakeHass(makeSnapshot());
    const card = await mountCard(hass);

    card.shadowRoot.querySelector('.btn-edit').click();
    await flush();
    const form = card.shadowRoot.querySelector('.edit-signal-form-container');
    const picker = form.querySelector('#sl-edit-sig-entity');
    expect(picker.tagName).toBe('HA-ENTITY-PICKER');
    expect(picker.value).toBe('binary_sensor.front_door');
  });
});
