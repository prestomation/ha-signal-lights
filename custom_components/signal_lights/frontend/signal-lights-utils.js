/**
 * Shared utility functions for Signal Lights card.
 * Extracted for testability — this file is used by the test suite.
 * The card (signal-lights-card.js) contains its own inline copies of these functions.
 * Keep both in sync when modifying.
 */

export function escapeHtml(str) {
  if (str == null) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

export function triggerDescription(signal) {
  const mode = signal.trigger_mode || 'template';
  const cfg = signal.trigger_config || {};
  switch (mode) {
    case 'entity_equals':
      return `${cfg.entity_id || '?'} = ${cfg.state || '?'}`;
    case 'entity_on':
      return `${cfg.entity_id || '?'} is on`;
    case 'numeric_threshold':
      return `${cfg.entity_id || '?'} ${cfg.direction || 'above'} ${cfg.threshold ?? '?'}`;
    case 'template':
      return 'Custom template';
    default:
      return mode;
  }
}

export function rgbToHex(color) {
  if (!Array.isArray(color) || color.length < 3) return '#ffffff';
  const [r, g, b] = color.map(c => Math.max(0, Math.min(255, parseInt(c) || 0)));
  return '#' + [r, g, b].map(c => c.toString(16).padStart(2, '0')).join('');
}

export function getActiveEntry(wsData, configEntryId) {
  if (!wsData || wsData.length === 0) return null;
  if (configEntryId) {
    return wsData.find(e => e.entry_id === configEntryId) || null;
  }
  return wsData[0] || null;
}

export function entryIdData(entry) {
  if (entry && entry.entry_id && /^[0-9A-Z]{26}$/.test(entry.entry_id)) {
    return { config_entry_id: entry.entry_id };
  }
  return {};
}

export function buildTriggerFieldsHtml(mode, config, signal, idPrefix, escFn) {
  const esc = escFn || escapeHtml;
  const cfg = config || {};
  switch (mode) {
    case 'entity_equals':
      return `
        <div class="form-row">
          <label>Entity</label>
          <div class="entity-picker-container" data-picker-mode="entity_equals"></div>
        </div>
        <div class="form-row">
          <label>Target state</label>
          <input type="text" id="${esc(idPrefix)}-state" value="${esc(cfg.state || '')}" placeholder="on" />
        </div>`;
    case 'entity_on':
      return `
        <div class="form-row">
          <label>Entity</label>
          <div class="entity-picker-container" data-picker-mode="entity_on"></div>
        </div>`;
    case 'numeric_threshold':
      return `
        <div class="form-row">
          <label>Sensor entity</label>
          <div class="entity-picker-container" data-picker-mode="numeric_threshold"></div>
        </div>
        <div class="form-row">
          <label>Threshold</label>
          <input type="number" id="${esc(idPrefix)}-threshold" value="${cfg.threshold ?? 0}" />
        </div>
        <div class="form-row">
          <label>Direction</label>
          <select id="${esc(idPrefix)}-direction">
            <option value="above" ${cfg.direction !== 'below' ? 'selected' : ''}>Above</option>
            <option value="below" ${cfg.direction === 'below' ? 'selected' : ''}>Below</option>
          </select>
        </div>`;
    case 'template':
      return `
        <div class="form-row">
          <label>Jinja2 Template</label>
          <textarea id="${esc(idPrefix)}-template" rows="3">${esc((signal && signal.template) || cfg.template || '')}</textarea>
        </div>`;
    default:
      return `<div class="form-row">Unknown trigger mode: ${esc(mode)}</div>`;
  }
}
