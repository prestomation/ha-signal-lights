/**
 * Signal Lights Card — Configuration and status dashboard for Home Assistant
 * Bundled with the Signal Lights integration — no manual setup required.
 * Version: 1.1.0
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

/* ── Editor element ─────────────────────────────────────────────────────── */
class SignalLightsCardEditor extends HTMLElement {
  constructor() {
    super();
    this._config = {};
  }

  setConfig(config) {
    this._config = { ...config };
    this._render();
  }

  set hass(h) {
    this.__hass = h;
    this._render();
  }

  /** Detect Signal Lights config entry IDs by scanning known sensor entities. */
  _detectEntries() {
    if (!this.__hass) return [];
    const states = this.__hass.states;
    const seen = new Map(); // entry_id -> label
    for (const eid of Object.keys(states)) {
      // Sensors are named sensor.<entry_title_slug>_active_signal
      if (eid.endsWith('_active_signal')) {
        const attrs = states[eid].attributes;
        // entry_id is stored in the device identifiers — not directly visible here.
        // Use a heuristic: collect entity IDs that match _active_signal and try to
        // derive a display label from the entity name.
        const label = attrs.friendly_name || eid;
        seen.set(eid, label);
      }
    }
    return Array.from(seen.entries()).map(([eid, label]) => ({ eid, label }));
  }

  _render() {
    if (!this.shadowRoot) this.attachShadow({ mode: 'open' });
    const entries = this._detectEntries();
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
        <div class="hint">${showSelector ? 'Multiple Signal Lights setups detected. Select which one to display.' : 'No additional configuration needed. The card automatically connects to the Signal Lights integration.'}</div>
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
    this._lastDataHash = null;
    this._dragSrcIndex = null;
    this._showAddSignal = false;
    this._showAddLight = false;
    this._addSignalMode = 'entity_equals';
    this._confirmDelete = null; // { type: 'signal'|'light', name: string }
    this._timers = [];
  }

  static getConfigElement() {
    return document.createElement('signal-lights-card-editor');
  }

  static getStubConfig() {
    return { type: 'custom:signal-lights-card' };
  }

  setConfig(config) {
    this._config = { ...config };
  }

  set hass(hass) {
    this._hass = hass;
    const hash = this._dataHash();
    if (hash !== this._lastDataHash) {
      this._lastDataHash = hash;
      if (!this._showAddSignal && !this._showAddLight) {
        this._render();
      }
    }
  }

  disconnectedCallback() {
    for (const id of this._timers) clearTimeout(id);
    this._timers = [];
  }

  _setTimeout(fn, delay) {
    const id = setTimeout(() => {
      this._timers = this._timers.filter(t => t !== id);
      fn();
    }, delay);
    this._timers.push(id);
    return id;
  }

  _dataHash() {
    if (!this._hass) return '';
    // Find any signal_lights sensor to get coordinator data
    const states = this._hass.states;
    const parts = [];
    for (const eid of Object.keys(states)) {
      if (eid.startsWith('sensor.signal_lights_') || eid.startsWith('binary_sensor.signal_lights_')) {
        parts.push(eid + '=' + states[eid].state);
        const attrs = states[eid].attributes;
        if (attrs.active_signals) parts.push(JSON.stringify(attrs.active_signals));
      }
    }
    return parts.join('|');
  }

  _getCoordData() {
    // Get data from the active_signal sensor's attributes and coordinator data.
    // If config_entry_id is set in card config, use it to filter to the right entity.
    if (!this._hass) return null;
    const states = this._hass.states;
    const configEntryId = this._config.config_entry_id || null;
    let activeEntity = null;
    for (const eid of Object.keys(states)) {
      if (eid.endsWith('_active_signal')) {
        // If we have a config_entry_id, match it via entry_id attribute (if present)
        const attrs = states[eid].attributes || {};
        if (configEntryId) {
          if (attrs.entry_id === configEntryId || eid === configEntryId) {
            activeEntity = states[eid];
            break;
          }
        } else {
          activeEntity = states[eid];
          break;
        }
      }
    }
    return activeEntity;
  }

  /** Return the config_entry_id to include in service calls (or empty object). */
  _entryIdData() {
    const id = this._config.config_entry_id;
    return id ? { config_entry_id: id } : {};
  }

  async _callService(domain, service, data) {
    if (!this._hass) return;
    try {
      await this._hass.callService(domain, service, data);
    } catch (err) {
      console.error(`Signal Lights: ${domain}.${service} failed:`, err);
    }
  }

  /* ── Rendering ─────────────────────────────────────────────────────── */

  _render() {
    const root = this.shadowRoot;
    const title = this._config.title || 'Signal Lights';

    // Get current state
    const activeEntity = this._getCoordData();
    const activeSignal = activeEntity ? activeEntity.state : 'none';
    const activeSignals = activeEntity ? (activeEntity.attributes.active_signals || []) : [];

    // Get config data from sensor attributes (populated by coordinator)
    // We'll fetch fresh data via service response pattern — but since services
    // don't return data easily in cards, we use the sensor attributes.
    // The coordinator pushes signals/lights/notifications into the data.

    // For the card, we need to fetch from HA states. The coordinator data
    // is available via sensor attributes. Let's check what we have.
    let signals = [];
    let lights = [];
    let notifications = { enabled: false, targets: [] };

    // Try to get full data from queue depth sensor (it has all data in coordinator)
    // Actually, we need to get this from the REST API or use the sensor.
    // For simplicity, the coordinator data is attached to the sensor.
    // We'll look for extra attributes on the active signal sensor.
    if (activeEntity && activeEntity.attributes) {
      // These are set by the coordinator via _build_data
      // But standard HA sensors may not expose all coordinator data as attributes.
      // We'll use a fallback: call services and re-render.
    }

    // Build the card HTML
    root.innerHTML = `
      <style>${this._styles()}</style>
      <ha-card header="${_esc(title)}">
        <div class="card-content" id="sl-content">
          <div class="status-bar">
            <div class="status-indicator ${activeSignal !== 'none' ? 'active' : 'inactive'}">
              <span class="status-dot" style="background: ${activeSignal !== 'none' ? 'var(--success-color, #4CAF50)' : 'var(--disabled-color, #9E9E9E)'}"></span>
              <span class="status-text">${activeSignal !== 'none' ? _esc(activeSignal) : 'No active signal'}</span>
            </div>
            ${activeSignals.length > 1 ? `<span class="queue-badge">${activeSignals.length} in queue</span>` : ''}
          </div>

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

    // Populate dynamic sections
    this._renderLights();
    this._renderSignals(activeSignals);
    this._renderNotifications();

    // Bind top-level events
    root.getElementById('sl-add-light-btn').addEventListener('click', () => this._toggleAddLight());
    root.getElementById('sl-add-signal-btn').addEventListener('click', () => this._toggleAddSignal());
  }

  _renderLights() {
    const container = this.shadowRoot.getElementById('sl-lights-list');
    if (!container || !this._hass) return;

    // Fetch lights from service call isn't practical in a card.
    // Instead, we'll try to read from the HA storage via the coordinator.
    // Workaround: use the REST API to read the storage, or just provide
    // an "add light" form and let the user manage via the card.
    // For now, show entities that have been registered by checking what
    // entities the integration controls. We can detect this from the
    // sensor attributes.

    // Actually, let's just render an empty state with the add form.
    // The data will come from re-reading after service calls.
    // For a real deployment, the coordinator data is available.

    // Simple approach: scan for light entities and show registered ones
    // We'll store the known state in the card DOM after service calls.
    if (this._lightsCache) {
      this._renderLightsList(container, this._lightsCache);
    } else {
      container.innerHTML = '<div class="empty-state">Loading lights...</div>';
      this._fetchConfig();
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
            this._fetchConfig();
          });
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

  _renderSignals(activeSignals) {
    const container = this.shadowRoot.getElementById('sl-signals-list');
    if (!container) return;

    if (this._signalsCache) {
      this._renderSignalsList(container, this._signalsCache, activeSignals);
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

      return `
        <div class="item-row signal-row ${isActive ? 'signal-active' : ''}"
             draggable="true" data-index="${i}" data-name="${_esc(s.name)}">
          <span class="drag-handle" title="Drag to reorder">⠿</span>
          <span class="color-swatch" style="background: ${color}" title="${_esc(color)}"></span>
          <div class="signal-info">
            <span class="item-name ${isActive ? 'bold' : ''}">#${i + 1} ${_esc(s.name)}</span>
            <span class="item-detail">${typeBadge} ${_esc(s.trigger_type)} · ${triggerDesc}</span>
          </div>
          <div class="signal-actions">
            ${s.trigger_type === 'event' ? `<button class="btn-small btn-trigger" data-name="${_esc(s.name)}" title="Trigger">▶</button>` : ''}
            ${isActive ? `<button class="btn-small btn-dismiss" data-name="${_esc(s.name)}" title="Dismiss">⏹</button>` : ''}
            <button class="btn-remove" data-name="${_esc(s.name)}" title="Remove signal">✕</button>
          </div>
        </div>
      `;
    }).join('');

    // Drag-to-reorder events
    const rows = container.querySelectorAll('.signal-row[draggable]');
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
          this._callService('signal_lights', 'reorder_signals', { order: names, ...this._entryIdData() }).then(() => {
            this._fetchConfig();
          });
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

    container.querySelectorAll('.btn-remove').forEach(btn => {
      btn.addEventListener('click', (e) => {
        const name = e.currentTarget.dataset.name;
        if (this._confirmDelete && this._confirmDelete.type === 'signal' && this._confirmDelete.name === name) {
          this._callService('signal_lights', 'remove_signal', { name, ...this._entryIdData() }).then(() => {
            this._confirmDelete = null;
            this._fetchConfig();
          });
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

  _renderNotifications() {
    const container = this.shadowRoot.getElementById('sl-notifications-config');
    if (!container) return;

    const notif = this._notificationsCache || { enabled: false, targets: [] };
    const targets = (notif.targets || []).join(', ');

    container.innerHTML = `
      <div class="notif-form">
        <label class="toggle-row">
          <span>Enable notifications</span>
          <input type="checkbox" id="sl-notif-enabled" ${notif.enabled ? 'checked' : ''} />
        </label>
        <div class="notif-targets" style="${notif.enabled ? '' : 'opacity: 0.5; pointer-events: none;'}">
          <label>Notify targets (comma-separated)</label>
          <input type="text" id="sl-notif-targets" value="${_esc(targets)}"
                 placeholder="notify.mobile_app_phone" />
          <div class="hint">e.g., notify.mobile_app_phone, notify.mobile_app_tablet</div>
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
      const targetsRaw = container.querySelector('#sl-notif-targets').value;
      const targetsList = targetsRaw.split(',').map(t => t.trim()).filter(Boolean);
      this._callService('signal_lights', 'configure_notifications', {
        enabled,
        targets: targetsList,
        ...this._entryIdData(),
      }).then(() => {
        this._notificationsCache = { enabled, targets: targetsList };
        const btn = container.querySelector('#sl-notif-save');
        btn.textContent = '✓ Saved';
        this._setTimeout(() => { btn.textContent = 'Save'; }, 2000);
      });
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

      // Create HA entity picker programmatically
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
          this._fetchConfig();
        });
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

    // Use placeholder divs for entity pickers — we'll inject ha-entity-picker after innerHTML
    let triggerFields = '';
    switch (mode) {
      case 'entity_equals':
        triggerFields = `
          <div class="form-row">
            <label>Entity</label>
            <div id="sl-sig-entity-container" class="entity-picker-container"></div>
          </div>
          <div class="form-row">
            <label>Target state</label>
            <input type="text" id="sl-sig-state" placeholder="on" />
          </div>
        `;
        break;
      case 'entity_on':
        triggerFields = `
          <div class="form-row">
            <label>Entity</label>
            <div id="sl-sig-entity-container" class="entity-picker-container"></div>
          </div>
        `;
        break;
      case 'numeric_threshold':
        triggerFields = `
          <div class="form-row">
            <label>Sensor entity</label>
            <div id="sl-sig-entity-container" class="entity-picker-container"></div>
          </div>
          <div class="form-row">
            <label>Threshold</label>
            <input type="number" id="sl-sig-threshold" placeholder="20" />
          </div>
          <div class="form-row">
            <label>Direction</label>
            <select id="sl-sig-direction">
              <option value="above">Above</option>
              <option value="below">Below</option>
            </select>
          </div>
        `;
        break;
      case 'template':
        triggerFields = `
          <div class="form-row">
            <label>Jinja2 Template</label>
            <textarea id="sl-sig-template" rows="3" placeholder="{{ is_state('sensor.x', 'on') }}"></textarea>
          </div>
        `;
        break;
    }

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

    // Inject ha-entity-picker into the placeholder container if present
    const entityContainer = form.querySelector('#sl-sig-entity-container');
    if (entityContainer) {
      const entityPicker = document.createElement('ha-entity-picker');
      entityPicker.hass = this._hass;
      entityPicker.allowCustomEntity = true;
      entityPicker.id = 'sl-sig-entity';
      if (mode === 'entity_on') {
        entityPicker.includeDomains = ['binary_sensor', 'switch', 'light', 'input_boolean'];
      } else if (mode === 'numeric_threshold') {
        entityPicker.includeDomains = ['sensor'];
      }
      entityContainer.appendChild(entityPicker);
    }

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

      let triggerConfig = {};
      let template = '';

      switch (triggerMode) {
        case 'entity_equals': {
          const entityId = (form.querySelector('#sl-sig-entity').value || '').trim();
          const state = form.querySelector('#sl-sig-state').value.trim();
          triggerConfig = { entity_id: entityId, state };
          break;
        }
        case 'entity_on': {
          const entityId = (form.querySelector('#sl-sig-entity').value || '').trim();
          triggerConfig = { entity_id: entityId };
          break;
        }
        case 'numeric_threshold': {
          const entityId = (form.querySelector('#sl-sig-entity').value || '').trim();
          const threshold = parseFloat(form.querySelector('#sl-sig-threshold').value || '0');
          const direction = form.querySelector('#sl-sig-direction').value;
          triggerConfig = { entity_id: entityId, threshold, direction };
          break;
        }
        case 'template': {
          template = form.querySelector('#sl-sig-template').value.trim();
          triggerConfig = { template };
          break;
        }
      }

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
        this._fetchConfig();
      });
    });

    form.querySelector('#sl-add-signal-cancel').addEventListener('click', () => {
      this._showAddSignal = false;
      form.style.display = 'none';
    });
  }

  /* ── Fetch config from HA ──────────────────────────────────────────── */

  async _fetchConfig() {
    if (!this._hass) return;

    // Use the WebSocket API to read the storage file
    try {
      // Try to read coordinator data via a refresh + sensor attributes
      // The simplest approach: call refresh service, then read sensor state
      await this._callService('signal_lights', 'refresh', { ...this._entryIdData() });

      // Wait a tick for state to update
      await new Promise(r => setTimeout(r, 200));

      // Now try to read from the HA REST API for the storage
      // Since we can't easily access .storage from a card,
      // we'll read the coordinator data from sensor attributes.
      // The coordinator pushes data to sensors via async_set_updated_data.

      // Find the active signal sensor and check for our enriched attributes
      if (this._hass.states) {
        for (const eid of Object.keys(this._hass.states)) {
          if (eid.includes('signal_lights_active_signal')) {
            const entity = this._hass.states[eid];
            // The coordinator now includes signals, lights, notifications in data
            // but HA sensors only expose what's in extra_state_attributes.
            // We need to add these to the sensor's attributes.
            break;
          }
        }
      }

      // Fallback: use WS API to get config entry data
      // hass.callWS is available in Lovelace cards
      if (this._hass.callWS) {
        try {
          const entries = await this._hass.callWS({
            type: 'config_entries/get',
            domain: 'signal_lights',
          });
          if (entries && entries.length > 0) {
            // Try to get the stored data via the signal_lights domain data
            // This requires a custom WS handler — let's use a simpler approach
          }
        } catch (e) {
          // Older HA versions may not support this
        }
      }

      // Simplest reliable approach: read the sensor attributes
      // The active_signal sensor has active_signals in attributes
      // We'll enhance the sensor to expose full config data
      // For now, rebuild from what the card can see

      // Actually — the coordinator builds data with signals, lights, notifications
      // We just need the sensor to expose these. Let's check the sensor entity.
      const activeEntity = this._getCoordData();
      if (activeEntity && activeEntity.attributes) {
        // Check if our enriched data is in attributes
        if (activeEntity.attributes.signals) {
          this._signalsCache = activeEntity.attributes.signals;
        }
        if (activeEntity.attributes.lights) {
          this._lightsCache = activeEntity.attributes.lights;
        }
        if (activeEntity.attributes.notifications) {
          this._notificationsCache = activeEntity.attributes.notifications;
        }
      }

      this._render();
    } catch (err) {
      console.error('Signal Lights: failed to fetch config:', err);
    }
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
      .notif-targets label {
        display: block;
        font-size: 12px;
        color: var(--secondary-text-color);
        margin-bottom: 4px;
      }
      .notif-targets input {
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
