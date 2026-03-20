/**
 * Signal Lights Card — Configuration and status dashboard for Home Assistant
 * Bundled with the Signal Lights integration — no manual setup required.
 * Version: 2.0.0
 *
 * Data layer: uses custom WebSocket commands (signal_lights/subscribe,
 * signal_lights/config) instead of scanning HA entity states.
 */

/* ── Card picker registration ───────────────────────────────────────────── */
window.customCards = window.customCards || [];
window.customCards.push({
  type: 'signal-lights-card',
  name: 'Signal Lights',
  description: 'Configure and monitor Signal Lights — manage lights, signals, and priorities',
  preview: true,
});

/* ── Utilities ──────────────────────────────────────────────────────────── */

function _esc(str) {
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#x27;');
}

function _rgbToHex(rgb) {
  if (!Array.isArray(rgb) || rgb.length < 3) return '#ffffff';
  return '#' + rgb.map(c => Math.max(0, Math.min(255, c)).toString(16).padStart(2, '0')).join('');
}

function _hexToRgb(hex) {
  const m = /^#?([0-9a-f]{2})([0-9a-f]{2})([0-9a-f]{2})$/i.exec(hex);
  if (!m) return [255, 255, 255];
  return [parseInt(m[1], 16), parseInt(m[2], 16), parseInt(m[3], 16)];
}

function _triggerDescription(signal) {
  const mode = signal.trigger_mode || 'template';
  const cfg = signal.trigger_config || {};
  switch (mode) {
    case 'entity_equals':
      return _esc(cfg.entity_id || '?') + ' = ' + _esc(cfg.state || '?');
    case 'entity_on':
      return _esc(cfg.entity_id || '?') + ' is on';
    case 'numeric_threshold': {
      const dir = cfg.direction === 'below' ? '<' : '>';
      return _esc(cfg.entity_id || '?') + ' ' + dir + ' ' + _esc(String(cfg.threshold || 0));
    }
    case 'template':
    default:
      return 'Template';
  }
}

/* ── Shared form builder helpers ────────────────────────────────────────── */

/**
 * Returns the HTML string for trigger-specific form fields.
 * @param {string} mode - trigger_mode value
 * @param {object} cfg - trigger_config object
 * @param {object} signal - full signal object (for template value)
 * @param {string} idPrefix - prefix for element IDs (e.g. 'sl-sig' or 'sl-edit-sig')
 */
function _buildTriggerFieldsHtml(mode, cfg, signal, idPrefix) {
  switch (mode) {
    case 'entity_equals':
      return `
        <div class="form-row">
          <label>Entity</label>
          <div id="${idPrefix}-entity-container" class="entity-picker-container"></div>
        </div>
        <div class="form-row">
          <label>Target state</label>
          <input type="text" id="${idPrefix}-state" value="${_esc(cfg.state || '')}" placeholder="on" />
        </div>
      `;
    case 'entity_on':
      return `
        <div class="form-row">
          <label>Entity</label>
          <div id="${idPrefix}-entity-container" class="entity-picker-container"></div>
        </div>
      `;
    case 'numeric_threshold':
      return `
        <div class="form-row">
          <label>Sensor entity</label>
          <div id="${idPrefix}-entity-container" class="entity-picker-container"></div>
        </div>
        <div class="form-row">
          <label>Threshold</label>
          <input type="number" id="${idPrefix}-threshold" value="${_esc(String(cfg.threshold !== undefined ? cfg.threshold : 0))}" />
        </div>
        <div class="form-row">
          <label>Direction</label>
          <select id="${idPrefix}-direction">
            <option value="above" ${cfg.direction !== 'below' ? 'selected' : ''}>Above</option>
            <option value="below" ${cfg.direction === 'below' ? 'selected' : ''}>Below</option>
          </select>
        </div>
      `;
    case 'template':
    default:
      return `
        <div class="form-row">
          <label>Jinja2 Template</label>
          <textarea id="${idPrefix}-template" rows="3">${_esc((signal && (signal.template || (signal.trigger_config || {}).template)) || '')}</textarea>
        </div>
      `;
  }
}

/**
 * Reads trigger form values from the container and returns { triggerConfig, template }.
 * @param {Element} container - DOM element containing the form fields
 * @param {string} idPrefix - prefix for element IDs
 * @param {string} mode - trigger_mode value
 */
function _readTriggerConfig(container, idPrefix, mode) {
  let triggerConfig = {};
  let template = '';

  switch (mode) {
    case 'entity_equals': {
      const picker = container.querySelector(`#${idPrefix}-entity`);
      const entityId = picker ? (picker.value || '').trim() : '';
      const stateEl = container.querySelector(`#${idPrefix}-state`);
      const state = stateEl ? stateEl.value.trim() : '';
      triggerConfig = { entity_id: entityId, state };
      break;
    }
    case 'entity_on': {
      const picker = container.querySelector(`#${idPrefix}-entity`);
      const entityId = picker ? (picker.value || '').trim() : '';
      triggerConfig = { entity_id: entityId };
      break;
    }
    case 'numeric_threshold': {
      const picker = container.querySelector(`#${idPrefix}-entity`);
      const entityId = picker ? (picker.value || '').trim() : '';
      const threshEl = container.querySelector(`#${idPrefix}-threshold`);
      const threshold = parseFloat((threshEl ? threshEl.value : null) || '0');
      const dirEl = container.querySelector(`#${idPrefix}-direction`);
      const direction = dirEl ? dirEl.value : 'above';
      triggerConfig = { entity_id: entityId, threshold, direction };
      break;
    }
    case 'template': {
      const tmplEl = container.querySelector(`#${idPrefix}-template`);
      template = tmplEl ? tmplEl.value.trim() : '';
      triggerConfig = { template };
      break;
    }
  }

  return { triggerConfig, template };
}

/**
 * Creates and injects a ha-entity-picker into the container placeholder.
 * @param {Element} container - DOM element containing the form
 * @param {string} idPrefix - prefix for element IDs
 * @param {string} mode - trigger_mode (controls domain filter)
 * @param {object} hass - HA hass object
 * @param {string} currentValue - pre-populated entity ID
 */
function _injectEntityPicker(container, idPrefix, mode, hass, currentValue) {
  const placeholder = container.querySelector(`#${idPrefix}-entity-container`);
  if (!placeholder) return;

  const picker = document.createElement('ha-entity-picker');
  picker.hass = hass;
  picker.allowCustomEntity = true;
  picker.id = `${idPrefix}-entity`;

  if (mode === 'entity_on') {
    picker.includeDomains = ['binary_sensor', 'switch', 'light', 'input_boolean'];
  } else if (mode === 'numeric_threshold') {
    picker.includeDomains = ['sensor'];
  }

  picker.value = currentValue || '';
  placeholder.appendChild(picker);
}

/* ── Editor element ─────────────────────────────────────────────────────── */
class SignalLightsCardEditor extends HTMLElement {
  constructor() {
    super();
    this._config = {};
    this.__hass = null;
  }

  setConfig(config) {
    this._config = { ...config };
    if (this.__hass) this._render();
  }

  set hass(h) {
    const prev = this.__hass;
    this.__hass = h;
    if (!this._config) return;
    if (!prev && h) this._render(); // first hass set — trigger render
  }

  /** Detect Signal Lights config entries via WebSocket. Returns a Promise. */
  async _detectEntries() {
    if (!this.__hass) return [];
    try {
      const entries = await this.__hass.callWS({ type: 'signal_lights/config' });
      return entries.map(e => ({ eid: e.entry_id, label: e.title || e.entry_id }));
    } catch (err) {
      return [];
    }
  }

  async _render() {
    // Guard against concurrent renders (e.g. hass set + setConfig racing).
    // Use a pending-render pattern so no render is silently dropped.
    if (this._rendering) {
      this._pendingRender = true;
      return;
    }
    this._rendering = true;
    try {
      do {
        this._pendingRender = false;
        await this._renderInner();
      } while (this._pendingRender);
    } finally {
      this._rendering = false;
    }
  }

  async _renderInner() {
    if (!this.shadowRoot) this.attachShadow({ mode: 'open' });

    const entries = await this._detectEntries();
    const showSelector = entries.length > 1;
    const currentEntry = this._config.config_entry_id || '';

    let selectorHtml = '';
    if (showSelector) {
      const options = entries.map(e =>
        `<option value="${_esc(e.eid)}" ${currentEntry === e.eid ? 'selected' : ''}>${_esc(e.label)}</option>`
      ).join('');
      selectorHtml = `
        <div>
          <label>Setup (which Signal Lights instance to show)</label>
          <select name="config_entry_id">
            <option value="">Auto-detect (first found)</option>
            ${options}
          </select>
        </div>
      `;
    }

    this.shadowRoot.innerHTML = `
      <style>
        .form { display: flex; flex-direction: column; gap: 12px; padding: 8px 0; }
        label { font-size: 12px; color: var(--secondary-text-color); margin-bottom: 2px; display: block; }
        input, select {
          width: 100%; box-sizing: border-box; padding: 8px 10px;
          border: 1px solid var(--divider-color); border-radius: 6px;
          background: var(--card-background-color); color: var(--primary-text-color); font-size: 14px;
        }
        .hint { font-size: 11px; color: var(--secondary-text-color); margin-top: 2px; }
      </style>
      <div class="form">
        <div>
          <label>Title (optional)</label>
          <input name="title" value="${_esc(this._config.title || '')}" placeholder="Signal Lights" />
        </div>
        ${selectorHtml}
        <div class="hint">${showSelector ? 'Multiple Signal Lights setups detected. Select which one to display.' : ''}</div>
      </div>
    `;
    this.shadowRoot.querySelectorAll('input, select').forEach(el => {
      el.addEventListener('change', () => this._valueChanged());
    });
  }

  _valueChanged() {
    const newConfig = { ...this._config };
    const titleEl = this.shadowRoot.querySelector('input[name="title"]');
    if (titleEl && titleEl.value.trim()) {
      newConfig.title = titleEl.value.trim();
    } else {
      delete newConfig.title;
    }
    const entryEl = this.shadowRoot.querySelector('select[name="config_entry_id"]');
    if (entryEl) {
      if (entryEl.value) {
        newConfig.config_entry_id = entryEl.value;
      } else {
        delete newConfig.config_entry_id;
      }
    }
    this.dispatchEvent(new CustomEvent('config-changed', {
      detail: { config: newConfig }, bubbles: true, composed: true,
    }));
  }
}

customElements.define('signal-lights-card-editor', SignalLightsCardEditor);

/* ── Main card element ──────────────────────────────────────────────────── */
class SignalLightsCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: 'open' });
    this._config = {};
    this._hass = null;
    this._wsData = null;        // array of entry objects from WS subscription
    this._wsUnsub = null;       // unsubscribe function from WS subscription
    this._subscribing = false;  // guard flag to prevent double WS subscription race
    this._dragSrcIndex = null;
    this._showAddSignal = false;
    this._showAddLight = false;
    this._addSignalMode = 'entity_equals';
    this._confirmDelete = null; // { type: 'signal'|'light', name: string }
    this._editingSignal = null; // name of signal being edited (or null)
    this._editSignalMode = 'entity_equals'; // trigger_mode for the edit form
    this._timers = [];
    // Data caches — populated from WS updates
    this._signalsCache = null;
    this._lightsCache = null;
    this._notificationsCache = null;
    this._activeSignal = 'none';
    this._activeColor = '#000000';
    this._activeSignalNames = [];
    this._queueDepth = 0;
    this._isActive = false;
  }

  static getConfigElement() {
    return document.createElement('signal-lights-card-editor');
  }

  static getStubConfig() {
    return { type: 'custom:signal-lights-card' };
  }

  setConfig(config) {
    const prevEntryId = this._config ? this._config.config_entry_id : undefined;
    this._config = { ...config };
    if (prevEntryId !== config.config_entry_id && this._wsUnsub) {
      this._wsUnsub();
      this._wsUnsub = null;
      this._wsData = null;
      if (this._hass) this._subscribeToUpdates();
    }
  }

  set hass(hass) {
    const first = !this._hass;
    this._hass = hass;
    // Subscribe when hass becomes available (lazy init).
    if (!this._wsUnsub && !this._subscribing && hass) {
      this._subscribeToUpdates();
    }
    // Show loading spinner immediately on first hass set
    if (first && hass && this._config && !this._wsData) {
      this._render();
    }
  }

  async connectedCallback() {
    if (this._hass && !this._wsUnsub && !this._subscribing) {
      await this._subscribeToUpdates();
    }
  }

  disconnectedCallback() {
    for (const id of this._timers) clearTimeout(id);
    this._timers = [];
    if (this._wsUnsub) {
      this._wsUnsub();
      this._wsUnsub = null;
    }
  }

  _setTimeout(fn, delay) {
    const id = setTimeout(() => {
      this._timers = this._timers.filter(t => t !== id);
      fn();
    }, delay);
    this._timers.push(id);
    return id;
  }

  /* ── WebSocket subscription ─────────────────────────────────────────── */

  async _subscribeToUpdates() {
    // Guard against concurrent calls from set hass + connectedCallback racing.
    if (!this._hass || this._wsUnsub || this._subscribing) return;
    this._subscribing = true;

    const entryId = this._config.config_entry_id || null;
    const msg = { type: 'signal_lights/subscribe' };
    if (entryId) msg.entry_id = entryId;

    try {
      const unsub = await this._hass.connection.subscribeMessage(
        (event) => {
          this._wsData = event;
          this._updateFromWsData();
        },
        msg
      );
      if (!this.isConnected) {
        unsub();
        return;
      }
      this._wsUnsub = unsub;
    } catch (err) {
      console.error('Signal Lights: WS subscribe failed:', err);
    } finally {
      this._subscribing = false;
    }
  }

  _updateFromWsData() {
    if (!this._wsData || this._wsData.length === 0) return;
    const entry = this._getActiveEntry();
    if (!entry) {
      // config_entry_id is set but the entry was not found — show empty state
      this.shadowRoot.innerHTML = `
        <style>:host { display: block; } ha-card { padding: 16px; }</style>
        <ha-card><div style="padding:16px;color:var(--secondary-text-color);font-size:13px;">
          Signal Lights entry not found. Check your card configuration.
        </div></ha-card>
      `;
      return;
    }

    // Detect structural changes that require a full DOM rebuild.
    const signalsChanged = JSON.stringify(entry.signals) !== JSON.stringify(this._signalsCache);
    const lightsChanged = JSON.stringify(entry.lights) !== JSON.stringify(this._lightsCache);
    const notifChanged = JSON.stringify(entry.notifications) !== JSON.stringify(this._notificationsCache);

    // Update all caches.
    this._signalsCache = entry.signals;
    this._lightsCache = entry.lights;
    this._notificationsCache = entry.notifications;
    this._activeSignal = entry.active_signal;
    this._activeColor = entry.active_color;
    this._activeSignalNames = entry.active_signal_names || [];
    this._queueDepth = entry.queue_depth;
    this._isActive = entry.is_active;

    // Don't disrupt active editing forms.
    if (this._editingSignal || this._showAddSignal || this._showAddLight) return;

    const prevActiveNames = this._prevActiveNames || [];
    const activeChanged = JSON.stringify(this._activeSignalNames) !== JSON.stringify(prevActiveNames);
    this._prevActiveNames = [...(this._activeSignalNames || [])];

    if (signalsChanged || lightsChanged || notifChanged) {
      // Structural change — full rebuild needed.
      this._render();
    } else if (activeChanged) {
      // Active signals changed (trigger/dismiss) — update status + signal list for button swap (▶/⏹)
      this._renderStatusBar();
      this._renderSignals();
    } else {
      // Status-only change (color, queue_depth) — just the status bar.
      this._renderStatusBar();
    }
  }

  _getActiveEntry() {
    if (!this._wsData || this._wsData.length === 0) return null;
    const entryId = this._config.config_entry_id;  // set by editor dropdown
    if (entryId) {
      return this._wsData.find(e => e.entry_id === entryId) || null;
    }
    return this._wsData[0] || null;
  }

  /** Return { config_entry_id } for service calls, or empty object. */
  _entryIdData() {
    const entry = this._getActiveEntry();
    if (entry) return { config_entry_id: entry.entry_id };
    return {};
  }

  async _callService(domain, service, data) {
    if (!this._hass) return;
    try {
      await this._hass.callService(domain, service, data);
      // WS subscription will push the update automatically
    } catch (err) {
      console.error(`Signal Lights: ${service} failed:`, err);
      throw err;  // re-throw so callers can handle
    }
  }

  /* ── Rendering ─────────────────────────────────────────────────────── */

  _render() {
    const root = this.shadowRoot;
    const title = this._config.title || 'Signal Lights';

    // Show loading state until WS data arrives
    if (!this._wsData) {
      root.innerHTML = `
        <style>${this._styles()}</style>
        <ha-card header="${_esc(title)}">
          <div class="card-content">
            <div class="loading-state">
              <div class="loading-spinner"></div>
              <span>Connecting...</span>
            </div>
          </div>
        </ha-card>
      `;
      return;
    }

    root.innerHTML = `
      <style>${this._styles()}</style>
      <ha-card header="${_esc(title)}">
        <div class="card-content" id="sl-content">
          <div id="sl-status-bar"></div>

          <div class="section" id="sl-lights-section">
            <div class="section-header">
              <h3>💡 Lights</h3>
              <button class="btn-icon" id="sl-add-light-btn" title="Add light">+</button>
            </div>
            <div id="sl-lights-list" class="item-list"></div>
            <div id="sl-add-light-form" class="inline-form" style="display:none"></div>
          </div>

          <div class="section" id="sl-signals-section">
            <div class="section-header">
              <h3>🚦 Signals</h3>
              <button class="btn-icon" id="sl-add-signal-btn" title="Add signal">+</button>
            </div>
            <div id="sl-signals-list" class="item-list"></div>
            <div id="sl-add-signal-form" class="inline-form" style="display:none"></div>
          </div>

          <div class="section" id="sl-notifications-section">
            <div class="section-header">
              <h3>🔔 Notifications</h3>
            </div>
            <div id="sl-notifications-config"></div>
          </div>
        </div>
      </ha-card>
    `;

    this._renderStatusBar();
    this._renderLights();
    this._renderSignals();
    this._renderNotifications();

    root.getElementById('sl-add-light-btn').addEventListener('click', () => this._toggleAddLight());
    root.getElementById('sl-add-signal-btn').addEventListener('click', () => this._toggleAddSignal());
  }

  _renderStatusBar() {
    const container = this.shadowRoot.getElementById('sl-status-bar');
    if (!container) return;

    const activeSignal = this._activeSignal || 'none';
    const activeSignalNames = this._activeSignalNames || [];

    container.innerHTML = `
      <div class="status-bar">
        <div class="status-indicator ${activeSignal !== 'none' ? 'active' : 'inactive'}">
          <span class="status-dot" style="background: ${activeSignal !== 'none' ? _esc(this._activeColor || '#4CAF50') : 'var(--disabled-color, #9E9E9E)'}"></span>
          <span class="status-text">${activeSignal !== 'none' ? _esc(activeSignal) : 'No active signal'}</span>
        </div>
        ${activeSignalNames.length > 1 ? `<span class="queue-badge">${activeSignalNames.length} in queue</span>` : ''}
      </div>
    `;
  }

  _renderLights() {
    const container = this.shadowRoot.getElementById('sl-lights-list');
    if (!container) return;

    if (this._lightsCache) {
      this._renderLightsList(container, this._lightsCache);
    } else {
      container.innerHTML = '<div class="empty-state">Loading lights...</div>';
    }
  }

  _renderLightsList(container, lights) {
    if (!lights || lights.length === 0) {
      container.innerHTML = '<div class="empty-state">No lights registered. Click + to add one.</div>';
      return;
    }
    container.innerHTML = lights.map(l => `
      <div class="item-row light-row">
        <span class="item-icon">💡</span>
        <span class="item-name">${_esc(l.entity_id)}</span>
        <span class="item-detail">Brightness: ${l.brightness || 255}</span>
        <button class="btn-remove" data-entity="${_esc(l.entity_id)}" title="Remove light">✕</button>
      </div>
    `).join('');

    container.querySelectorAll('.btn-remove').forEach(btn => {
      btn.addEventListener('click', (e) => {
        const entityId = e.currentTarget.dataset.entity;
        if (this._confirmDelete && this._confirmDelete.type === 'light' && this._confirmDelete.name === entityId) {
          this._callService('signal_lights', 'remove_light', { entity_id: entityId, ...this._entryIdData() }).then(() => {
            this._confirmDelete = null;
          }).catch(err => console.error('Signal Lights: remove_light failed:', err));
        } else {
          this._confirmDelete = { type: 'light', name: entityId };
          e.currentTarget.textContent = '⚠️';
          e.currentTarget.title = 'Click again to confirm removal';
          this._setTimeout(() => {
            this._confirmDelete = null;
            e.currentTarget.textContent = '✕';
            e.currentTarget.title = 'Remove light';
          }, 3000);
        }
      });
    });
  }

  _renderSignals() {
    const container = this.shadowRoot.getElementById('sl-signals-list');
    if (!container) return;

    if (this._signalsCache) {
      this._renderSignalsList(container, this._signalsCache, this._activeSignalNames || []);
    } else {
      container.innerHTML = '<div class="empty-state">Loading signals...</div>';
    }
  }

  _renderSignalsList(container, signals, activeSignals) {
    if (!signals || signals.length === 0) {
      container.innerHTML = '<div class="empty-state">No signals defined. Click + to add one.</div>';
      return;
    }

    const activeSet = new Set(activeSignals || []);

    container.innerHTML = signals.map((s, i) => {
      const isActive = activeSet.has(s.name);
      const color = _rgbToHex(s.color || [255, 255, 255]);
      const typeBadge = s.trigger_type === 'event' ? '⚡' : '🔄';
      const triggerDesc = _triggerDescription(s);
      const isEditing = this._editingSignal === s.name;

      return `
        <div class="item-row signal-row ${isActive ? 'signal-active' : ''} ${isEditing ? 'signal-editing' : ''}"
             draggable="${isEditing ? 'false' : 'true'}" data-index="${i}" data-name="${_esc(s.name)}">
          <span class="drag-handle" title="Drag to reorder">⠿</span>
          <span class="color-swatch" style="background: ${color}" title="${_esc(color)}"></span>
          <div class="signal-info">
            <span class="item-name ${isActive ? 'bold' : ''}">#${i + 1} ${_esc(s.name)}</span>
            <span class="item-detail">${typeBadge} ${_esc(s.trigger_type)} · ${triggerDesc}</span>
          </div>
          <div class="signal-actions">
            ${s.trigger_type === 'event' && !isActive ? `<button class="btn-small btn-trigger" data-name="${_esc(s.name)}" title="Trigger">▶</button>` : ''}
            ${isActive ? `<button class="btn-small btn-dismiss" data-name="${_esc(s.name)}" title="Dismiss">⏹</button>` : ''}
            <button class="btn-small btn-edit" data-name="${_esc(s.name)}" title="Edit signal">✏️</button>
            <button class="btn-remove" data-name="${_esc(s.name)}" title="Remove signal">✕</button>
          </div>
        </div>
        ${isEditing ? `<div class="edit-signal-form-container" data-edit-name="${_esc(s.name)}"></div>` : ''}
      `;
    }).join('');

    // Inject edit form for the signal being edited
    if (this._editingSignal) {
      const editSignal = signals.find(s => s.name === this._editingSignal);
      const formContainer = container.querySelector(`.edit-signal-form-container[data-edit-name="${CSS.escape(this._editingSignal)}"]`);
      if (editSignal && formContainer) {
        this._renderEditSignalForm(formContainer, editSignal);
      }
    }

    // Drag-to-reorder events
    const rows = container.querySelectorAll('.signal-row[draggable="true"]');
    rows.forEach(row => {
      row.addEventListener('dragstart', (e) => {
        this._dragSrcIndex = parseInt(e.currentTarget.dataset.index);
        e.currentTarget.classList.add('dragging');
        e.dataTransfer.effectAllowed = 'move';
        e.dataTransfer.setData('text/plain', e.currentTarget.dataset.index);
      });

      row.addEventListener('dragover', (e) => {
        e.preventDefault();
        e.dataTransfer.dropEffect = 'move';
        e.currentTarget.classList.add('drag-over');
      });

      row.addEventListener('dragleave', (e) => {
        e.currentTarget.classList.remove('drag-over');
      });

      row.addEventListener('dragend', (e) => {
        e.currentTarget.classList.remove('dragging');
        container.querySelectorAll('.drag-over').forEach(el => el.classList.remove('drag-over'));
      });

      row.addEventListener('drop', (e) => {
        e.preventDefault();
        e.currentTarget.classList.remove('drag-over');
        const fromIndex = this._dragSrcIndex;
        const toIndex = parseInt(e.currentTarget.dataset.index);
        if (fromIndex !== null && fromIndex !== toIndex && this._signalsCache) {
          const names = this._signalsCache.map(s => s.name);
          const [moved] = names.splice(fromIndex, 1);
          names.splice(toIndex, 0, moved);
          this._callService('signal_lights', 'reorder_signals', { order: names, ...this._entryIdData() });
        }
        this._dragSrcIndex = null;
      });
    });

    // Action buttons
    container.querySelectorAll('.btn-trigger').forEach(btn => {
      btn.addEventListener('click', (e) => {
        this._callService('signal_lights', 'trigger_signal', { name: e.currentTarget.dataset.name, ...this._entryIdData() });
      });
    });

    container.querySelectorAll('.btn-dismiss').forEach(btn => {
      btn.addEventListener('click', (e) => {
        this._callService('signal_lights', 'dismiss_signal', { name: e.currentTarget.dataset.name, ...this._entryIdData() });
      });
    });

    container.querySelectorAll('.btn-edit').forEach(btn => {
      btn.addEventListener('click', (e) => {
        const name = e.currentTarget.dataset.name;
        if (this._editingSignal === name) {
          this._editingSignal = null;
        } else {
          const sig = signals.find(s => s.name === name);
          this._editingSignal = name;
          this._editSignalMode = sig ? (sig.trigger_mode || 'entity_equals') : 'entity_equals';
        }
        this._renderSignals();
      });
    });

    container.querySelectorAll('.btn-remove').forEach(btn => {
      btn.addEventListener('click', (e) => {
        const name = e.currentTarget.dataset.name;
        if (this._confirmDelete && this._confirmDelete.type === 'signal' && this._confirmDelete.name === name) {
          this._callService('signal_lights', 'remove_signal', { name, ...this._entryIdData() }).then(() => {
            this._confirmDelete = null;
            this._editingSignal = null;
          }).catch(err => console.error('Signal Lights: remove_signal failed:', err));
        } else {
          this._confirmDelete = { type: 'signal', name };
          e.currentTarget.textContent = '⚠️';
          e.currentTarget.title = 'Click again to confirm';
          this._setTimeout(() => {
            this._confirmDelete = null;
            e.currentTarget.textContent = '✕';
            e.currentTarget.title = 'Remove signal';
          }, 3000);
        }
      });
    });
  }

  /* ── Edit signal form ──────────────────────────────────────────────── */

  _renderEditSignalForm(container, signal) {
    const mode = this._editSignalMode;
    const cfg = signal.trigger_config || {};

    const editName = signal._editName !== undefined ? signal._editName : signal.name;
    const editColor = signal._editColor || signal.color || [255, 0, 0];
    const color = editColor;
    const hexColor = _rgbToHex(color);

    const triggerFields = _buildTriggerFieldsHtml(mode, cfg, signal, 'sl-edit-sig');

    const isEvent = signal.trigger_type === 'event';

    container.innerHTML = `
      <div class="edit-form-inner">
        <div class="form-row">
          <label>Signal name</label>
          <input type="text" id="sl-edit-sig-name" value="${_esc(editName)}" />
        </div>
        <div class="form-row">
          <label>Color</label>
          <div class="color-picker-row">
            <div id="sl-edit-sig-color-preview" class="color-preview" style="background:${_esc(hexColor)}"></div>
            <label>R</label><input type="number" id="sl-edit-sig-color-r" min="0" max="255" value="${_esc(String(color[0]))}" class="rgb-input" />
            <label>G</label><input type="number" id="sl-edit-sig-color-g" min="0" max="255" value="${_esc(String(color[1]))}" class="rgb-input" />
            <label>B</label><input type="number" id="sl-edit-sig-color-b" min="0" max="255" value="${_esc(String(color[2]))}" class="rgb-input" />
          </div>
        </div>
        <div class="form-row">
          <label>Trigger type</label>
          <select id="sl-edit-sig-trigger-type">
            <option value="condition" ${signal.trigger_type === 'condition' ? 'selected' : ''}>Condition (active while true)</option>
            <option value="event" ${signal.trigger_type === 'event' ? 'selected' : ''}>Event (fires for a duration)</option>
          </select>
        </div>
        <div class="form-row">
          <label>Trigger mode</label>
          <select id="sl-edit-sig-trigger-mode">
            <option value="entity_equals" ${mode === 'entity_equals' ? 'selected' : ''}>Entity equals state</option>
            <option value="entity_on" ${mode === 'entity_on' ? 'selected' : ''}>Entity is on</option>
            <option value="numeric_threshold" ${mode === 'numeric_threshold' ? 'selected' : ''}>Numeric above/below</option>
            <option value="template" ${mode === 'template' ? 'selected' : ''}>Template (advanced)</option>
          </select>
        </div>
        ${triggerFields}
        <div class="form-row" id="sl-edit-sig-duration-row" style="display:${isEvent ? 'block' : 'none'}">
          <label>Duration (seconds)</label>
          <input type="number" id="sl-edit-sig-duration" value="${signal.duration || 60}" min="1" max="86400" />
        </div>
        <div class="form-actions">
          <button class="btn-primary" id="sl-edit-sig-save">Save</button>
          <button class="btn-secondary" id="sl-edit-sig-cancel">Cancel</button>
        </div>
      </div>
    `;

    _injectEntityPicker(container, 'sl-edit-sig', mode, this._hass, cfg.entity_id || '');

    // Trigger mode change — re-render form with new mode, preserving edits
    container.querySelector('#sl-edit-sig-trigger-mode').addEventListener('change', (e) => {
      this._editSignalMode = e.target.value;
      const updatedSignal = { ...signal };
      const nameEl = container.querySelector('#sl-edit-sig-name');
      if (nameEl) updatedSignal._editName = nameEl.value;
      const rEl = container.querySelector('#sl-edit-sig-color-r');
      const gEl = container.querySelector('#sl-edit-sig-color-g');
      const bEl = container.querySelector('#sl-edit-sig-color-b');
      if (rEl && gEl && bEl) {
        updatedSignal._editColor = [
          parseInt(rEl.value) || 0,
          parseInt(gEl.value) || 0,
          parseInt(bEl.value) || 0,
        ];
      }
      this._renderEditSignalForm(container, updatedSignal);
    });

    // Trigger type change — show/hide duration
    const typeSelect = container.querySelector('#sl-edit-sig-trigger-type');
    const durationRow = container.querySelector('#sl-edit-sig-duration-row');
    typeSelect.addEventListener('change', () => {
      durationRow.style.display = typeSelect.value === 'event' ? 'block' : 'none';
    });

    // Live color preview
    const colorPreview = container.querySelector('#sl-edit-sig-color-preview');
    ['r', 'g', 'b'].forEach(ch => {
      container.querySelector(`#sl-edit-sig-color-${ch}`).addEventListener('input', () => {
        const r = container.querySelector('#sl-edit-sig-color-r').value || 0;
        const g = container.querySelector('#sl-edit-sig-color-g').value || 0;
        const b = container.querySelector('#sl-edit-sig-color-b').value || 0;
        colorPreview.style.background = `rgb(${r},${g},${b})`;
      });
    });

    // Save handler
    container.querySelector('#sl-edit-sig-save').addEventListener('click', () => {
      const newName = container.querySelector('#sl-edit-sig-name').value.trim();
      if (!newName) return;

      const newColor = [
        parseInt(container.querySelector('#sl-edit-sig-color-r').value) || 0,
        parseInt(container.querySelector('#sl-edit-sig-color-g').value) || 0,
        parseInt(container.querySelector('#sl-edit-sig-color-b').value) || 0,
      ];
      const newTriggerType = container.querySelector('#sl-edit-sig-trigger-type').value;
      const newTriggerMode = container.querySelector('#sl-edit-sig-trigger-mode').value;
      const newDuration = newTriggerType === 'event'
        ? parseInt(container.querySelector('#sl-edit-sig-duration').value || '60')
        : 0;

      const { triggerConfig: newTriggerConfig, template: newTemplate } = _readTriggerConfig(container, 'sl-edit-sig', newTriggerMode);

      const serviceData = {
        name: signal.name,
        color: newColor,
        trigger_type: newTriggerType,
        trigger_mode: newTriggerMode,
        trigger_config: newTriggerConfig,
        duration: newDuration,
        ...this._entryIdData(),
      };
      if (newTriggerMode === 'template') {
        serviceData.template = newTemplate;
      }
      if (newName !== signal.name) {
        serviceData.new_name = newName;
      }

      this._callService('signal_lights', 'update_signal', serviceData).then(() => {
        this._editingSignal = null;
        // WS subscription will push the update
      }).catch(err => console.error('Signal Lights: update_signal failed:', err));
    });

    // Cancel handler
    container.querySelector('#sl-edit-sig-cancel').addEventListener('click', () => {
      this._editingSignal = null;
      this._renderSignals();
    });
  }

  _renderNotifications() {
    const container = this.shadowRoot.getElementById('sl-notifications-config');
    if (!container) return;

    const notif = this._notificationsCache || { enabled: false, targets: [] };
    const currentTargets = new Set(notif.targets || []);

    // Discover available notify.* services from hass
    const notifyServices = [];
    if (this._hass && this._hass.services && this._hass.services.notify) {
      for (const svc of Object.keys(this._hass.services.notify).sort()) {
        const target = `notify.${svc}`;
        notifyServices.push(target);
      }
    }

    const optionsHtml = notifyServices.map(t =>
      `<label class="target-option"><input type="checkbox" value="${_esc(t)}" ${currentTargets.has(t) ? 'checked' : ''} /> <span>${_esc(t)}</span></label>`
    ).join('');

    const fallbackHtml = notifyServices.length === 0
      ? `<input type="text" id="sl-notif-targets-text" value="${_esc([...currentTargets].join(', '))}" placeholder="notify.mobile_app_phone" /><div class="hint">No notify services detected — enter manually (comma-separated)</div>`
      : '';

    container.innerHTML = `
      <div class="notif-form">
        <label class="toggle-row">
          <span>Enable notifications</span>
          <input type="checkbox" id="sl-notif-enabled" ${notif.enabled ? 'checked' : ''} />
        </label>
        <div class="notif-targets" style="${notif.enabled ? '' : 'opacity: 0.5; pointer-events: none;'}">
          <label>Notify targets</label>
          ${notifyServices.length > 0 ? `<div class="target-list" id="sl-notif-targets">${optionsHtml}</div>` : fallbackHtml}
        </div>
        <button class="btn-save" id="sl-notif-save">Save</button>
      </div>
    `;

    const enabledCheckbox = container.querySelector('#sl-notif-enabled');
    enabledCheckbox.addEventListener('change', () => {
      const targetsDiv = container.querySelector('.notif-targets');
      if (enabledCheckbox.checked) {
        targetsDiv.style.opacity = '';
        targetsDiv.style.pointerEvents = '';
      } else {
        targetsDiv.style.opacity = '0.5';
        targetsDiv.style.pointerEvents = 'none';
      }
    });

    container.querySelector('#sl-notif-save').addEventListener('click', () => {
      const enabled = enabledCheckbox.checked;
      let targetsList;
      const checkboxContainer = container.querySelector('#sl-notif-targets');
      const textFallback = container.querySelector('#sl-notif-targets-text');
      if (checkboxContainer) {
        targetsList = [...checkboxContainer.querySelectorAll('input[type="checkbox"]:checked')].map(cb => cb.value);
      } else if (textFallback) {
        targetsList = textFallback.value.split(',').map(t => t.trim()).filter(Boolean);
      } else {
        targetsList = [];
      }
      this._callService('signal_lights', 'configure_notifications', {
        enabled,
        targets: targetsList,
        ...this._entryIdData(),
      }).then(() => {
        this._notificationsCache = { enabled, targets: targetsList };
        const btn = container.querySelector('#sl-notif-save');
        btn.textContent = '✓ Saved';
        this._setTimeout(() => { btn.textContent = 'Save'; }, 2000);
      }).catch(err => console.error('Signal Lights: configure_notifications failed:', err));
    });
  }

  /* ── Add light form ────────────────────────────────────────────────── */

  _toggleAddLight() {
    this._showAddLight = !this._showAddLight;
    const form = this.shadowRoot.getElementById('sl-add-light-form');
    if (!form) return;

    if (this._showAddLight) {
      form.style.display = 'block';
      form.innerHTML = `
        <div class="inline-form-inner">
          <div class="form-row">
            <label>Light entity</label>
            <div id="sl-new-light-entity-container"></div>
          </div>
          <div class="form-row">
            <label>Brightness (1-255)</label>
            <input type="range" id="sl-new-light-brightness" min="1" max="255" value="255" />
            <span id="sl-brightness-val">255</span>
          </div>
          <div class="form-actions">
            <button class="btn-primary" id="sl-add-light-submit">Add Light</button>
            <button class="btn-secondary" id="sl-add-light-cancel">Cancel</button>
          </div>
        </div>
      `;

      const lightPicker = document.createElement('ha-entity-picker');
      lightPicker.hass = this._hass;
      lightPicker.includeDomains = ['light'];
      lightPicker.allowCustomEntity = true;
      lightPicker.id = 'sl-new-light-entity';
      form.querySelector('#sl-new-light-entity-container').appendChild(lightPicker);

      const slider = form.querySelector('#sl-new-light-brightness');
      const valSpan = form.querySelector('#sl-brightness-val');
      slider.addEventListener('input', () => { valSpan.textContent = slider.value; });

      form.querySelector('#sl-add-light-submit').addEventListener('click', () => {
        const entityId = lightPicker.value || '';
        const brightness = parseInt(slider.value);
        if (!entityId) return;
        this._callService('signal_lights', 'add_light', {
          entity_id: entityId,
          brightness,
          ...this._entryIdData(),
        }).then(() => {
          this._showAddLight = false;
          form.style.display = 'none';
        }).catch(err => console.error('Signal Lights: add_light failed:', err));
      });

      form.querySelector('#sl-add-light-cancel').addEventListener('click', () => {
        this._showAddLight = false;
        form.style.display = 'none';
      });
    } else {
      form.style.display = 'none';
    }
  }

  /* ── Add signal form ───────────────────────────────────────────────── */

  _toggleAddSignal() {
    this._showAddSignal = !this._showAddSignal;
    const form = this.shadowRoot.getElementById('sl-add-signal-form');
    if (!form) return;

    if (this._showAddSignal) {
      form.style.display = 'block';
      this._renderAddSignalForm(form);
    } else {
      form.style.display = 'none';
    }
  }

  _renderAddSignalForm(form) {
    const mode = this._addSignalMode;
    const triggerFields = _buildTriggerFieldsHtml(mode, {}, null, 'sl-sig');

    form.innerHTML = `
      <div class="inline-form-inner">
        <div class="form-row">
          <label>Signal name</label>
          <input type="text" id="sl-sig-name" placeholder="Front door open" />
        </div>
        <div class="form-row">
          <label>Color</label>
          <div class="color-picker-row">
            <div id="sl-sig-color-preview" class="color-preview" style="background:#ff0000"></div>
            <label>R</label><input type="number" id="sl-sig-color-r" min="0" max="255" value="255" class="rgb-input" />
            <label>G</label><input type="number" id="sl-sig-color-g" min="0" max="255" value="0" class="rgb-input" />
            <label>B</label><input type="number" id="sl-sig-color-b" min="0" max="255" value="0" class="rgb-input" />
          </div>
        </div>
        <div class="form-row">
          <label>Trigger type</label>
          <select id="sl-sig-trigger-type">
            <option value="condition">Condition (active while true)</option>
            <option value="event">Event (fires for a duration)</option>
          </select>
        </div>
        <div class="form-row">
          <label>Trigger mode</label>
          <select id="sl-sig-trigger-mode">
            <option value="entity_equals" ${mode === 'entity_equals' ? 'selected' : ''}>Entity equals state</option>
            <option value="entity_on" ${mode === 'entity_on' ? 'selected' : ''}>Entity is on</option>
            <option value="numeric_threshold" ${mode === 'numeric_threshold' ? 'selected' : ''}>Numeric above/below</option>
            <option value="template" ${mode === 'template' ? 'selected' : ''}>Template (advanced)</option>
          </select>
        </div>
        ${triggerFields}
        <div class="form-row" id="sl-sig-duration-row" style="display:none">
          <label>Duration (seconds)</label>
          <input type="number" id="sl-sig-duration" value="60" min="1" max="86400" />
        </div>
        <div class="form-actions">
          <button class="btn-primary" id="sl-add-signal-submit">Add Signal</button>
          <button class="btn-secondary" id="sl-add-signal-cancel">Cancel</button>
        </div>
      </div>
    `;

    // Mode change handler
    form.querySelector('#sl-sig-trigger-mode').addEventListener('change', (e) => {
      this._addSignalMode = e.target.value;
      this._renderAddSignalForm(form);
    });

    _injectEntityPicker(form, 'sl-sig', mode, this._hass, '');

    // Show duration for event type
    const typeSelect = form.querySelector('#sl-sig-trigger-type');
    const durationRow = form.querySelector('#sl-sig-duration-row');
    typeSelect.addEventListener('change', () => {
      durationRow.style.display = typeSelect.value === 'event' ? 'block' : 'none';
    });

    // Live color preview update
    const colorPreview = form.querySelector('#sl-sig-color-preview');
    ['r', 'g', 'b'].forEach(ch => {
      form.querySelector(`#sl-sig-color-${ch}`).addEventListener('input', () => {
        const r = form.querySelector('#sl-sig-color-r').value || 0;
        const g = form.querySelector('#sl-sig-color-g').value || 0;
        const b = form.querySelector('#sl-sig-color-b').value || 0;
        colorPreview.style.background = `rgb(${r},${g},${b})`;
      });
    });

    // Submit handler
    form.querySelector('#sl-add-signal-submit').addEventListener('click', () => {
      const name = form.querySelector('#sl-sig-name').value.trim();
      if (!name) return;

      const color = [
        parseInt(form.querySelector('#sl-sig-color-r').value) || 0,
        parseInt(form.querySelector('#sl-sig-color-g').value) || 0,
        parseInt(form.querySelector('#sl-sig-color-b').value) || 0,
      ];
      const triggerType = typeSelect.value;
      const triggerMode = this._addSignalMode;
      const duration = triggerType === 'event' ? parseInt(form.querySelector('#sl-sig-duration').value || '60') : 0;

      const { triggerConfig, template } = _readTriggerConfig(form, 'sl-sig', triggerMode);

      this._callService('signal_lights', 'add_signal', {
        name,
        color,
        trigger_type: triggerType,
        trigger_mode: triggerMode,
        trigger_config: triggerConfig,
        template,
        duration,
        ...this._entryIdData(),
      }).then(() => {
        this._showAddSignal = false;
        form.style.display = 'none';
      }).catch(err => console.error('Signal Lights: add_signal failed:', err));
    });

    form.querySelector('#sl-add-signal-cancel').addEventListener('click', () => {
      this._showAddSignal = false;
      form.style.display = 'none';
    });
  }

  /* ── Styles ────────────────────────────────────────────────────────── */

  _styles() {
    return `
      :host {
        --sl-radius: 8px;
        --sl-gap: 12px;
      }
      ha-card {
        overflow: hidden;
      }
      .card-content {
        padding: 0 16px 16px;
      }
      .status-bar {
        display: flex;
        align-items: center;
        justify-content: space-between;
        padding: 12px 0;
        border-bottom: 1px solid var(--divider-color, #e0e0e0);
        margin-bottom: var(--sl-gap);
      }
      .status-indicator {
        display: flex;
        align-items: center;
        gap: 8px;
        font-size: 14px;
        font-weight: 500;
      }
      .status-indicator.active { color: var(--primary-text-color); }
      .status-indicator.inactive { color: var(--secondary-text-color); }
      .status-dot {
        width: 10px; height: 10px;
        border-radius: 50%;
        display: inline-block;
        flex-shrink: 0;
      }
      .queue-badge {
        font-size: 11px;
        padding: 2px 8px;
        border-radius: 10px;
        background: var(--primary-color, #03A9F4);
        color: var(--text-primary-color, #fff);
      }

      .section {
        margin-bottom: var(--sl-gap);
      }
      .section-header {
        display: flex;
        align-items: center;
        justify-content: space-between;
        margin-bottom: 8px;
      }
      .section-header h3 {
        margin: 0;
        font-size: 14px;
        font-weight: 500;
        color: var(--primary-text-color);
      }

      .btn-icon {
        width: 28px; height: 28px;
        border-radius: 50%;
        border: 1px solid var(--divider-color, #e0e0e0);
        background: var(--card-background-color, #fff);
        color: var(--primary-color, #03A9F4);
        font-size: 18px;
        cursor: pointer;
        display: flex;
        align-items: center;
        justify-content: center;
        line-height: 1;
        padding: 0;
        transition: background 0.2s;
      }
      .btn-icon:hover {
        background: var(--primary-color, #03A9F4);
        color: var(--text-primary-color, #fff);
      }

      .item-list {
        display: flex;
        flex-direction: column;
        gap: 4px;
      }
      .item-row {
        display: flex;
        align-items: center;
        gap: 8px;
        padding: 8px 10px;
        border-radius: var(--sl-radius);
        background: var(--secondary-background-color, #f5f5f5);
        transition: background 0.15s;
      }
      .item-row:hover {
        background: var(--primary-background-color, #eee);
      }
      .item-icon { font-size: 16px; flex-shrink: 0; }
      .item-name {
        font-size: 13px;
        color: var(--primary-text-color);
        flex: 1;
        min-width: 0;
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
      }
      .item-name.bold { font-weight: 600; }
      .item-detail {
        font-size: 11px;
        color: var(--secondary-text-color);
        flex-shrink: 0;
      }

      .signal-row {
        position: relative;
        cursor: default;
      }
      .signal-row.signal-active {
        background: color-mix(in srgb, var(--primary-color, #03A9F4) 10%, var(--secondary-background-color, #f5f5f5));
        border: 1px solid var(--primary-color, #03A9F4);
      }
      .signal-row.dragging {
        opacity: 0.4;
      }
      .signal-row.drag-over {
        border-top: 2px solid var(--primary-color, #03A9F4);
      }

      .drag-handle {
        cursor: grab;
        font-size: 14px;
        color: var(--secondary-text-color);
        user-select: none;
        flex-shrink: 0;
      }
      .drag-handle:active { cursor: grabbing; }

      .color-swatch {
        width: 16px; height: 16px;
        border-radius: 4px;
        flex-shrink: 0;
        border: 1px solid var(--divider-color, #e0e0e0);
      }

      .signal-info {
        flex: 1;
        min-width: 0;
        display: flex;
        flex-direction: column;
        gap: 2px;
      }
      .signal-info .item-name {
        flex: none;
      }
      .signal-info .item-detail {
        flex: none;
      }

      .signal-actions {
        display: flex;
        gap: 4px;
        flex-shrink: 0;
      }

      .btn-small {
        padding: 2px 6px;
        font-size: 11px;
        border: 1px solid var(--divider-color, #e0e0e0);
        border-radius: 4px;
        background: var(--card-background-color, #fff);
        color: var(--primary-text-color);
        cursor: pointer;
        transition: background 0.15s;
      }
      .btn-small:hover {
        background: var(--primary-color, #03A9F4);
        color: var(--text-primary-color, #fff);
      }

      .btn-remove {
        padding: 2px 6px;
        font-size: 12px;
        border: none;
        background: transparent;
        color: var(--error-color, #F44336);
        cursor: pointer;
        border-radius: 4px;
        transition: background 0.15s;
      }
      .btn-remove:hover {
        background: var(--error-color, #F44336);
        color: var(--text-primary-color, #fff);
      }

      .empty-state {
        font-size: 12px;
        color: var(--secondary-text-color);
        text-align: center;
        padding: 16px 0;
        font-style: italic;
      }
      .loading-state {
        display: flex;
        align-items: center;
        justify-content: center;
        gap: 12px;
        padding: 32px 0;
        color: var(--secondary-text-color);
        font-size: 14px;
      }
      .loading-spinner {
        width: 24px;
        height: 24px;
        border: 3px solid var(--divider-color, #e0e0e0);
        border-top-color: var(--primary-color, #03a9f4);
        border-radius: 50%;
        animation: sl-spin 0.8s linear infinite;
      }
      @keyframes sl-spin {
        to { transform: rotate(360deg); }
      }

      .inline-form {
        margin-top: 8px;
      }
      .inline-form-inner {
        padding: 12px;
        border-radius: var(--sl-radius);
        background: var(--secondary-background-color, #f5f5f5);
        border: 1px solid var(--divider-color, #e0e0e0);
      }
      .form-row {
        margin-bottom: 10px;
      }
      .form-row label {
        display: block;
        font-size: 12px;
        color: var(--secondary-text-color);
        margin-bottom: 4px;
      }
      .form-row input[type="text"],
      .form-row input[type="number"],
      .form-row textarea,
      .form-row select {
        width: 100%;
        box-sizing: border-box;
        padding: 8px 10px;
        border: 1px solid var(--divider-color, #e0e0e0);
        border-radius: 6px;
        background: var(--card-background-color, #fff);
        color: var(--primary-text-color);
        font-size: 13px;
        font-family: inherit;
      }
      .color-picker-row {
        display: flex;
        align-items: center;
        gap: 6px;
      }
      .color-picker-row label {
        font-size: 12px;
        color: var(--secondary-text-color);
        min-width: auto;
        margin: 0;
      }
      .color-preview {
        width: 32px;
        height: 32px;
        border-radius: 50%;
        border: 2px solid var(--divider-color, #e0e0e0);
        flex-shrink: 0;
      }
      .rgb-input {
        width: 52px;
        padding: 4px 6px;
        border: 1px solid var(--divider-color, #e0e0e0);
        border-radius: 4px;
        background: var(--card-background-color, #fff);
        color: var(--primary-text-color);
        font-size: 13px;
        text-align: center;
      }
      .rgb-input:focus {
        outline: none;
        border-color: var(--primary-color);
      }
      .form-row input[type="color"] {
        width: 48px; height: 32px;
        border: 1px solid var(--divider-color, #e0e0e0);
        border-radius: 6px;
        padding: 2px;
        cursor: pointer;
        background: var(--card-background-color, #fff);
      }
      .form-row input[type="range"] {
        width: calc(100% - 40px);
        vertical-align: middle;
      }

      .form-actions {
        display: flex;
        gap: 8px;
        margin-top: 12px;
      }
      .btn-primary, .btn-save {
        padding: 8px 16px;
        border: none;
        border-radius: 6px;
        background: var(--primary-color, #03A9F4);
        color: var(--text-primary-color, #fff);
        font-size: 13px;
        cursor: pointer;
        transition: opacity 0.15s;
      }
      .btn-primary:hover, .btn-save:hover { opacity: 0.85; }
      .btn-secondary {
        padding: 8px 16px;
        border: 1px solid var(--divider-color, #e0e0e0);
        border-radius: 6px;
        background: var(--card-background-color, #fff);
        color: var(--primary-text-color);
        font-size: 13px;
        cursor: pointer;
      }

      .signal-editing {
        border: 1px solid var(--primary-color, #03A9F4) !important;
        background: color-mix(in srgb, var(--primary-color, #03A9F4) 5%, var(--secondary-background-color, #f5f5f5)) !important;
      }
      .edit-signal-form-container {
        margin: 2px 0 4px 0;
      }
      .edit-form-inner {
        padding: 12px;
        border-radius: var(--sl-radius);
        background: var(--secondary-background-color, #f5f5f5);
        border: 1px solid var(--primary-color, #03A9F4);
        border-top: none;
        border-radius: 0 0 var(--sl-radius) var(--sl-radius);
      }

      .notif-form {
        padding: 12px;
        border-radius: var(--sl-radius);
        background: var(--secondary-background-color, #f5f5f5);
      }
      .toggle-row {
        display: flex;
        align-items: center;
        justify-content: space-between;
        font-size: 13px;
        color: var(--primary-text-color);
        margin-bottom: 10px;
      }
      .toggle-row input[type="checkbox"] {
        width: 18px; height: 18px;
        cursor: pointer;
      }
      .notif-targets > label {
        display: block;
        font-size: 12px;
        color: var(--secondary-text-color);
        margin-bottom: 4px;
      }
      .target-list {
        max-height: 200px;
        overflow-y: auto;
        border: 1px solid var(--divider-color, #e0e0e0);
        border-radius: 6px;
        padding: 6px 8px;
        background: var(--card-background-color);
      }
      .target-option {
        display: flex;
        align-items: center;
        gap: 8px;
        padding: 4px 0;
        font-size: 13px;
        color: var(--primary-text-color);
        cursor: pointer;
      }
      .target-option input[type="checkbox"] {
        width: auto;
        margin: 0;
      }
      .notif-targets input[type="text"] {
        width: 100%;
        box-sizing: border-box;
        padding: 8px 10px;
        border: 1px solid var(--divider-color, #e0e0e0);
        border-radius: 6px;
        background: var(--card-background-color, #fff);
        color: var(--primary-text-color);
        font-size: 13px;
      }
      .hint {
        font-size: 11px;
        color: var(--secondary-text-color);
        margin-top: 4px;
      }
    `;
  }
}

customElements.define('signal-lights-card', SignalLightsCard);
