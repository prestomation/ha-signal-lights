import { describe, it, expect } from 'vitest';
import {
  escapeHtml,
  triggerDescription,
  rgbToHex,
  getActiveEntry,
  entryIdData,
  buildTriggerFieldsHtml,
} from '../../custom_components/signal_lights/frontend/signal-lights-utils.js';

describe('escapeHtml', () => {
  it('escapes &, <, >, ", \'', () => {
    expect(escapeHtml('a & b < c > d " e \' f')).toBe('a &amp; b &lt; c &gt; d &quot; e &#39; f');
  });
  it('handles null/undefined', () => {
    expect(escapeHtml(null)).toBe('');
    expect(escapeHtml(undefined)).toBe('');
  });
  it('handles numbers', () => {
    expect(escapeHtml(42)).toBe('42');
  });
  it('handles empty string', () => {
    expect(escapeHtml('')).toBe('');
  });
  it('passes through safe strings', () => {
    expect(escapeHtml('hello world')).toBe('hello world');
  });
});

describe('triggerDescription', () => {
  it('entity_equals shows entity = state', () => {
    expect(triggerDescription({
      trigger_mode: 'entity_equals',
      trigger_config: { entity_id: 'sensor.temp', state: 'hot' },
    })).toBe('sensor.temp = hot');
  });
  it('entity_on shows entity is on', () => {
    expect(triggerDescription({
      trigger_mode: 'entity_on',
      trigger_config: { entity_id: 'switch.lamp' },
    })).toBe('switch.lamp is on');
  });
  it('numeric_threshold shows direction', () => {
    expect(triggerDescription({
      trigger_mode: 'numeric_threshold',
      trigger_config: { entity_id: 'sensor.temp', direction: 'above', threshold: 30 },
    })).toBe('sensor.temp above 30');
  });
  it('numeric_threshold below', () => {
    expect(triggerDescription({
      trigger_mode: 'numeric_threshold',
      trigger_config: { entity_id: 'sensor.temp', direction: 'below', threshold: 10 },
    })).toBe('sensor.temp below 10');
  });
  it('template mode', () => {
    expect(triggerDescription({ trigger_mode: 'template' })).toBe('Custom template');
  });
  it('missing config shows ?', () => {
    expect(triggerDescription({ trigger_mode: 'entity_equals', trigger_config: {} })).toBe('? = ?');
  });
  it('missing trigger_mode defaults to template', () => {
    expect(triggerDescription({})).toBe('Custom template');
  });
});

describe('rgbToHex', () => {
  it('converts [255, 0, 0] to #ff0000', () => {
    expect(rgbToHex([255, 0, 0])).toBe('#ff0000');
  });
  it('converts [0, 255, 42] to #00ff2a', () => {
    expect(rgbToHex([0, 255, 42])).toBe('#00ff2a');
  });
  it('clamps values above 255', () => {
    expect(rgbToHex([300, 0, 0])).toBe('#ff0000');
  });
  it('clamps negative values to 0', () => {
    expect(rgbToHex([-10, 0, 0])).toBe('#000000');
  });
  it('handles non-array input', () => {
    expect(rgbToHex(null)).toBe('#ffffff');
    expect(rgbToHex('red')).toBe('#ffffff');
    expect(rgbToHex([1])).toBe('#ffffff');
  });
  it('handles string numbers in array', () => {
    expect(rgbToHex(['128', '0', '128'])).toBe('#800080');
  });
});

describe('getActiveEntry', () => {
  const entries = [
    { entry_id: 'AAA', title: 'First' },
    { entry_id: 'BBB', title: 'Second' },
  ];

  it('returns first entry when no config_entry_id', () => {
    expect(getActiveEntry(entries, null)).toEqual(entries[0]);
    expect(getActiveEntry(entries, undefined)).toEqual(entries[0]);
    expect(getActiveEntry(entries, '')).toEqual(entries[0]);
  });
  it('returns matching entry by config_entry_id', () => {
    expect(getActiveEntry(entries, 'BBB')).toEqual(entries[1]);
  });
  it('returns null for unknown config_entry_id', () => {
    expect(getActiveEntry(entries, 'CCC')).toBeNull();
  });
  it('returns null for empty/null wsData', () => {
    expect(getActiveEntry(null, null)).toBeNull();
    expect(getActiveEntry([], null)).toBeNull();
  });
});

describe('entryIdData', () => {
  it('returns config_entry_id for valid ULID', () => {
    expect(entryIdData({ entry_id: '01KM50NFDVH65G8ADNG8K0MST9' }))
      .toEqual({ config_entry_id: '01KM50NFDVH65G8ADNG8K0MST9' });
  });
  it('returns empty object for null entry', () => {
    expect(entryIdData(null)).toEqual({});
  });
  it('returns empty object for invalid entry_id', () => {
    expect(entryIdData({ entry_id: 'not-a-ulid' })).toEqual({});
    expect(entryIdData({ entry_id: '' })).toEqual({});
  });
  it('returns empty object for lowercase entry_id', () => {
    expect(entryIdData({ entry_id: '01km50nfdvh65g8adng8k0mst9' })).toEqual({});
  });
});

describe('buildTriggerFieldsHtml', () => {
  it('entity_equals includes state input', () => {
    const html = buildTriggerFieldsHtml('entity_equals', { state: 'on' }, {}, 'test');
    expect(html).toContain('Target state');
    expect(html).toContain('value="on"');
    expect(html).toContain('entity-picker-container');
  });
  it('entity_on has entity picker only', () => {
    const html = buildTriggerFieldsHtml('entity_on', {}, {}, 'test');
    expect(html).toContain('entity-picker-container');
    expect(html).not.toContain('Target state');
  });
  it('numeric_threshold has threshold and direction', () => {
    const html = buildTriggerFieldsHtml('numeric_threshold', { threshold: 30, direction: 'below' }, {}, 'test');
    expect(html).toContain('Threshold');
    expect(html).toContain('Direction');
    expect(html).toContain('value="30"');
  });
  it('template has textarea', () => {
    const html = buildTriggerFieldsHtml('template', {}, { template: '{{ true }}' }, 'test');
    expect(html).toContain('textarea');
    expect(html).toContain('{{ true }}');
  });
  it('unknown mode shows error', () => {
    const html = buildTriggerFieldsHtml('unknown_mode', {}, {}, 'test');
    expect(html).toContain('Unknown trigger mode');
  });
  it('escapes HTML in config values', () => {
    const html = buildTriggerFieldsHtml('entity_equals', { state: '<script>alert(1)</script>' }, {}, 'test');
    expect(html).toContain('&lt;script&gt;');
    expect(html).not.toContain('<script>');
  });
});
