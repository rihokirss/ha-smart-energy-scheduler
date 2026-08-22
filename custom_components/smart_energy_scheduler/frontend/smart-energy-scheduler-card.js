class SmartEnergySchedulerCard extends HTMLElement {
  setConfig(config) {
    this.config = { title: "Smart Energy Scheduler", hours: 48, ...config };
    this.attachShadow({ mode: "open" });
    this.shadowRoot.innerHTML = `<ha-card><div class="loading">Laadin energiaplaani…</div></ha-card>`;
  }

  set hass(hass) {
    this._hass = hass;
    if (!this._loaded) {
      this._loaded = true;
      this._load();
    }
  }

  async _load() {
    try {
      const response = await this._hass.callWS({
        type: "smart_energy_scheduler/get_plan",
        ...(this.config.entry_id ? { entry_id: this.config.entry_id } : {}),
      });
      this.data = Array.isArray(response) ? response[0] : response;
      if (this._prepareData) await this._prepareData();
      this._render();
      this._unsubscribe = await this._hass.connection.subscribeMessage(
        async (data) => {
          this.data = data;
          if (this._prepareData) await this._prepareData();
          this._render();
        },
        {
          type: "smart_energy_scheduler/subscribe_plan",
          ...(this.config.entry_id ? { entry_id: this.config.entry_id } : {}),
        },
      );
    } catch (err) {
      this.shadowRoot.innerHTML = `<ha-card><div class="error">Plaani laadimine ebaõnnestus: ${this._escape(err.message || err)}</div></ha-card>`;
    }
  }

  disconnectedCallback() {
    if (this._unsubscribe) this._unsubscribe();
    if (this._hourCenterTimer) clearTimeout(this._hourCenterTimer);
  }

  getCardSize() { return 6; }

  static getStubConfig() { return { title: "Smart Energy Scheduler", hours: 48 }; }

  _escape(value) {
    return String(value ?? "").replace(/[&<>'"]/g, (char) => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;",
    })[char]);
  }

  _color(price, min, max) {
    const ratio = max === min ? 0.5 : Math.max(0, Math.min(1, (price - min) / (max - min)));
    return `hsl(${120 - ratio * 120} 70% 42%)`;
  }

  _useAmPm() {
    const locale = this._hass?.locale || {};
    if (locale.time_format === "12") return true;
    if (locale.time_format === "24") return false;
    const language = locale.time_format === "language" ? locale.language : undefined;
    return new Date("2023-01-01T22:00:00").toLocaleString(language).includes("10");
  }

  _formatTime(date) {
    return this._formatHour(date);
  }

  _formatHour(date) {
    const locale = this._hass?.locale || {};
    const options = { hour: "2-digit", hourCycle: "h23" };
    if (locale.time_zone === "server" && this._hass?.config?.time_zone) {
      options.timeZone = this._hass.config.time_zone;
    }
    return new Intl.DateTimeFormat(locale.language, options).format(date);
  }

  _formatClock(date) {
    const locale = this._hass?.locale || {};
    const options = { hour: "2-digit", minute: "2-digit", hourCycle: "h23" };
    if (locale.time_zone === "server" && this._hass?.config?.time_zone) {
      options.timeZone = this._hass.config.time_zone;
    }
    return new Intl.DateTimeFormat(locale.language, options).format(date);
  }

  _overlappingSlots(device, hour) {
    const start = new Date(hour.start).getTime();
    const end = new Date(hour.end || start + 3600000).getTime();
    return (device.plan?.hours || []).filter((slot) => {
      const slotStart = new Date(slot.start).getTime();
      const slotEnd = new Date(slot.end || slotStart + 3600000).getTime();
      return slotStart < end && slotEnd > start;
    });
  }

  _effectiveForHour(device, hour) {
    const slots = this._overlappingSlots(device, hour);
    if (!slots.length) return hour.import_eur_mwh;
    let weighted = 0, duration = 0;
    slots.forEach((slot) => {
      const start = new Date(slot.start).getTime();
      const end = new Date(slot.end || start + 3600000).getTime();
      const milliseconds = Math.max(0, end - start);
      weighted += Number(slot.effective_eur_mwh) * milliseconds;
      duration += milliseconds;
    });
    return duration ? weighted / duration : hour.import_eur_mwh;
  }

  _plannedRanges(device, hour) {
    const slots = this._overlappingSlots(device, hour).filter((slot) => slot.active);
    const ranges = [];
    slots.forEach((slot) => {
      const start = new Date(slot.start).getTime();
      const end = new Date(slot.end || start + 3600000).getTime();
      const previous = ranges.at(-1);
      if (previous && previous[1] === start) previous[1] = end;
      else ranges.push([start, end]);
    });
    return ranges.map(([start, end]) =>
      `${this._formatClock(new Date(start))}–${this._formatClock(new Date(end))}`
    ).join(", ");
  }

  _planGradient(device, hour) {
    const hourStart = new Date(hour.start).getTime();
    const hourEnd = new Date(hour.end || hourStart + 3600000).getTime();
    const duration = Math.max(1, hourEnd - hourStart);
    const stops = [];
    this._overlappingSlots(device, hour).forEach((slot) => {
      const start = Math.max(hourStart, new Date(slot.start).getTime());
      const end = Math.min(hourEnd, new Date(slot.end || start + 3600000).getTime());
      const left = (start - hourStart) / duration * 100;
      const right = (end - hourStart) / duration * 100;
      const color = slot.active ? "var(--primary-color,#03a9f4)" : "var(--divider-color,#ddd)";
      stops.push(`${color} ${left}%`, `${color} ${right}%`);
    });
    return stops.length ? `linear-gradient(to right,${stops.join(",")})` : "var(--divider-color,#ddd)";
  }

  async _override(deviceId, mode) {
    const data = { device_id: deviceId, mode, entry_id: this.data.entry_id };
    if (mode !== "auto") data.until = new Date(Date.now() + 2 * 3600000).toISOString();
    await this._hass.callService("smart_energy_scheduler", "set_override", data);
  }

  _scheduleHourCenter() {
    if (this._hourCenterTimer) clearTimeout(this._hourCenterTimer);
    const delay = 3600000 - Date.now() % 3600000 + 250;
    this._hourCenterTimer = setTimeout(() => {
      this._centeredHourKey = null;
      this._render();
    }, delay);
  }

  _centerCurrentHour(hours) {
    const now = Date.now();
    const currentHourKey = Math.floor(now / 3600000);
    if (this._centeredHourKey === currentHourKey) return;
    requestAnimationFrame(() => {
      const scroll = this.shadowRoot.querySelector(".scroll");
      const currentIndex = hours.findIndex((hour) => {
        const start = new Date(hour.start).getTime();
        return start <= now && now < start + 3600000;
      });
      if (scroll && currentIndex >= 0) {
        const current = scroll.querySelectorAll(".hour")[currentIndex];
        if (current) {
          scroll.scrollLeft = Math.max(
            0,
            current.offsetLeft + current.offsetWidth / 2 - scroll.clientWidth / 2,
          );
        }
      }
      this._centeredHourKey = currentHourKey;
    });
  }

  _render() {
    if (!this.data) return;
    const count = Math.max(1, Math.min(48, Number(this.config.hours) || 48));
    const hours = (this.data.hours || []).slice(0, count);
    const prices = hours.map((h) => h.import_eur_mwh);
    const min = Math.min(...prices, 0);
    const max = Math.max(...prices, 1);
    const columns = `repeat(${hours.length || 1}, minmax(8px, 1fr))`;
    const now = Date.now();
    const hourCells = hours.map((h) => {
      const date = new Date(h.start);
      const label = this._formatTime(date);
      const current = date.getTime() <= now && now < date.getTime() + 3600000;
      const title = `${date.toLocaleString()}\nOst ${h.import_eur_mwh.toFixed(1)} €/MWh\nMüük ${h.export_eur_mwh.toFixed(1)} €/MWh\nPV ${(h.pv_wh / 1000).toFixed(2)} kWh`;
      const pv = Math.min(100, h.pv_wh / Math.max(1, ...hours.map((x) => x.pv_wh)) * 100);
      const priceHeight = 22 + 30 * ((h.import_eur_mwh - min) / (max - min || 1));
      const pvHeight = pv * .28;
      return `<div class="hour ${current ? "current" : ""}" title="${this._escape(title)}">
        <div class="price" style="height:${priceHeight}px;background:${this._color(h.import_eur_mwh, min, max)}"></div>
        <div class="pv" style="height:${pvHeight}px"></div><span class="hour-label">${label}</span>
      </div>`;
    }).join("");
    const devices = Object.entries(this.data.devices || {}).map(([id, device]) => {
      const blocks = hours.map((h) => {
        const ranges = this._plannedRanges(device, h);
        return `<div class="block" style="background:${this._planGradient(device, h)}" title="${this._escape(ranges ? `Planeeritud ON ${ranges}` : "Planeeritud OFF")}"></div>`;
      }).join("");
      const actual = Object.values(device.state.actual_hours_by_day || {}).slice(-1)[0] || 0;
      return `<section class="device">
        <div class="device-head"><div><strong>${this._escape(device.name)}</strong><small>${actual.toFixed(1)} h · ${this._escape(device.state.reason)}</small></div>
        <div class="buttons"><ha-button size="s" variant="${device.state.override === "auto" ? "brand" : "neutral"}" appearance="${device.state.override === "auto" ? "filled" : "outlined"}" data-device="${id}" data-mode="auto">Auto</ha-button><ha-button size="s" variant="${device.state.override === "on" ? "brand" : "neutral"}" appearance="${device.state.override === "on" ? "filled" : "outlined"}" data-device="${id}" data-mode="on">ON 2h</ha-button><ha-button size="s" variant="${device.state.override === "off" ? "brand" : "neutral"}" appearance="${device.state.override === "off" ? "filled" : "outlined"}" data-device="${id}" data-mode="off">OFF 2h</ha-button></div></div>
        <div class="blocks" style="grid-template-columns:${columns}">${blocks}</div>
      </section>`;
    }).join("");
    const warnings = (this.data.warnings || []).map((item) => `<li>${this._escape(item)}</li>`).join("");
    this.shadowRoot.innerHTML = `<style>
      :host{display:block} ha-card{padding:var(--ha-space-4,16px);overflow:hidden}.top{display:flex;justify-content:space-between;align-items:center;gap:var(--ha-space-3,12px)}.card-title{color:var(--ha-card-header-color,var(--primary-text-color));font-family:var(--ha-card-header-font-family,inherit);font-size:var(--ha-card-header-font-size,var(--ha-font-size-2xl,24px));font-weight:var(--ha-font-weight-normal,400);letter-spacing:-.012em;line-height:var(--ha-line-height-expanded,1.5);margin:0}.badge{font-size:var(--ha-font-size-s,12px);padding:var(--ha-space-1,4px) var(--ha-space-2,8px);border-radius:var(--ha-border-radius-pill,999px);background:var(--warning-color,#f5a623);color:#111}.badge.live{background:var(--success-color,#43a047);color:#fff}.error{padding:var(--ha-space-4,16px);color:var(--error-color,#db4437)}.warnings{font-size:var(--ha-font-size-s,12px);color:var(--secondary-text-color);margin:var(--ha-space-2,8px) 0}.chart,.blocks{display:grid;gap:2px;min-width:480px}.scroll{overflow-x:auto;padding-bottom:var(--ha-space-1,4px)}.hour{box-sizing:border-box;height:104px;padding-bottom:22px;display:flex;flex-direction:column;justify-content:flex-end;align-items:stretch;position:relative}.price{min-height:3px;border-radius:3px 3px 0 0}.pv{background:#fbc02d;min-height:0}.hour .hour-label{position:absolute;left:50%;bottom:2px;transform:translateX(-50%) rotate(-90deg);transform-origin:center;font-size:11px;font-weight:var(--ha-font-weight-medium,500);line-height:1;white-space:nowrap;color:#000}.hour.current::before{content:"";position:absolute;top:0;left:50%;transform:translateX(-50%);border-left:5px solid transparent;border-right:5px solid transparent;border-top:8px solid var(--error-color,#e53935)}.device{margin-top:var(--ha-space-4,16px)}.device-head{display:flex;justify-content:flex-start;align-items:center;gap:var(--ha-space-3,12px);margin-bottom:var(--ha-space-2,8px);position:sticky;left:0;z-index:2;width:max-content;max-width:100%;padding:var(--ha-space-1,4px) var(--ha-space-2,8px) var(--ha-space-1,4px) 0;background:var(--ha-card-background,var(--card-background-color,#fff))}.device small{display:block;color:var(--secondary-text-color);margin-top:2px}.buttons{display:flex;gap:var(--ha-space-1,4px);flex-wrap:wrap}.block{height:22px;border-radius:var(--ha-border-radius-sm,4px);background:var(--divider-color,#ddd)}.block.active{background:var(--primary-color,#03a9f4)}.legend{font-size:var(--ha-font-size-s,12px);color:var(--secondary-text-color);margin-top:var(--ha-space-2,8px)}@media(max-width:600px){.device-head{align-items:flex-start;flex-direction:column}}
    </style><ha-card>
      <div class="top"><h1 class="card-title">${this._escape(this.config.title)}</h1><span class="badge ${this.data.shadow_mode ? "" : "live"}">${this.data.shadow_mode ? "VARIREŽIIM" : "JUHTIMINE AKTIIVNE"}</span></div>
      ${this.data.error ? `<div class="error">${this._escape(this.data.error)}</div>` : ""}
      ${warnings ? `<ul class="warnings">${warnings}</ul>` : ""}
      <div class="scroll"><div class="chart" style="grid-template-columns:${columns}">${hourCells}</div>${devices}</div>
      <div class="legend">Tulba värv: ostuhind · kollane: PV prognoos · sinine: seadme töötund</div>
    </ha-card>`;
    this.shadowRoot.querySelectorAll("ha-button[data-mode]").forEach((button) => {
      button.addEventListener("click", () => this._override(button.dataset.device, button.dataset.mode));
    });
    this._centerCurrentHour(hours);
    this._scheduleHourCenter();
  }
}

customElements.define("smart-energy-scheduler-card", SmartEnergySchedulerCard);
window.customCards = window.customCards || [];
window.customCards.push({
  type: "smart-energy-scheduler-card",
  name: "Smart Energy Scheduler",
  description: "48-hour price, solar, and controlled-device plan",
  preview: true,
});

class SmartEnergyPricePlanCard extends SmartEnergySchedulerCard {
  setConfig(config) {
    super.setConfig({ title: "Hind ja tööplaan", hours: 48, ...config });
  }

  _selectedDevice() {
    const entries = Object.entries(this.data?.devices || {});
    return entries.find(([id, device]) =>
      id === this.config.device_id ||
      device.name === this.config.device ||
      device.target_entity === this.config.target_entity
    ) || entries[0];
  }

  async _prepareData() {
    const selected = this._selectedDevice();
    const firstHour = this.data?.hours?.[0]?.start;
    if (!selected || !firstHour) {
      this._history = {};
      return;
    }
    const targetEntity = selected[1].power_sensor || selected[1].feedback_entity || selected[1].target_entity;
    this._historyEntity = targetEntity;
    try {
      this._history = await this._hass.callWS({
        type: "history/history_during_period",
        start_time: new Date(firstHour).toISOString(),
        end_time: new Date().toISOString(),
        entity_ids: [targetEntity],
        minimal_response: true,
        no_attributes: true,
      });
    } catch (_err) {
      this._history = {};
    }
  }

  _actualActivity(hour, device) {
    const start = new Date(hour.start).getTime();
    const end = Math.min(start + 3600000, Date.now());
    if (start >= Date.now()) return null;
    const events = this._history?.[this._historyEntity] || [];
    let state = null;
    let cursor = start;
    let activeMs = 0;
    const segments = [];
    for (const event of events) {
      const stamp = Number(event.lu ?? event.lc) * 1000 || Date.parse(event.last_changed || "");
      const eventState = event.s ?? event.state;
      if (!Number.isFinite(stamp)) continue;
      if (stamp <= start) {
        state = eventState;
        continue;
      }
      if (stamp >= end) break;
      if (this._historyStateActive(state, device)) {
        activeMs += stamp - cursor;
        segments.push([cursor, stamp]);
      }
      cursor = stamp;
      state = eventState;
    }
    if (this._historyStateActive(state, device)) {
      activeMs += Math.max(0, end - cursor);
      segments.push([cursor, end]);
    }
    return state === null ? null : { active: activeMs > 0, minutes: activeMs / 60000, segments };
  }

  _historyStateActive(state, device) {
    if (device.power_sensor && this._historyEntity === device.power_sensor) {
      return Number(state) * Number(device.power_multiplier || 1) > 10;
    }
    if (device.feedback_entity && this._historyEntity === device.feedback_entity) {
      return ["on", "open", "opening", "heat", "heating", "active"].includes(state);
    }
    if (state !== "on" && state !== "off") return false;
    return device.inverted ? state === "off" : state === "on";
  }

  _render() {
    if (!this.data) return;
    const selected = this._selectedDevice();
    if (!selected) {
      this.shadowRoot.innerHTML = `<ha-card><div class="error">Ühtegi juhitavat seadet ei ole seadistatud.</div></ha-card>`;
      return;
    }
    const [deviceId, device] = selected;
    const count = Math.max(1, Math.min(48, Number(this.config.hours) || 48));
    const hours = (this.data.hours || []).slice(0, count);
    const values = hours.flatMap((hour) => {
      const slotValues = this._overlappingSlots(device, hour)
        .map((slot) => Number(slot.effective_eur_mwh))
        .filter(Number.isFinite);
      return [hour.import_eur_mwh, ...slotValues];
    });
    const minimum = Math.min(0, ...values);
    const maximum = Math.max(1, ...values);
    const width = Math.max(440, hours.length * 17);
    const chartHeight = 280;
    const left = 32, right = 8, top = 32, bottom = 8;
    const plotWidth = width - left - right;
    const plotHeight = chartHeight - top - bottom;
    const step = plotWidth / Math.max(1, hours.length);
    const y = (value) => top + (maximum - value) / (maximum - minimum || 1) * plotHeight;
    const baseline = y(0);
    const now = Date.now();
    const bars = hours.map((hour, index) => {
      const start = new Date(hour.start).getTime();
      const end = new Date(hour.end || start + 3600000).getTime();
      const historical = end <= now;
      const actual = start < now ? this._actualActivity(hour, device) : null;
      const planSlots = this._overlappingSlots(device, hour);
      const barWidth = Math.max(3, step * .86);
      const x = left + index * step + (step - barWidth) / 2;
      const valueY = y(hour.import_eur_mwh);
      const rectY = Math.min(valueY, baseline);
      const rectHeight = Math.max(1, Math.abs(baseline - valueY));
      const current = start <= now && now < end;
      const plannedRanges = this._plannedRanges(device, hour);
      const status = historical
        ? (actual?.active ? `Tegelikult ON (${actual.minutes.toFixed(0)} min)` : "Tegelikult OFF")
        : (plannedRanges ? `Planeeritud ON ${plannedRanges}` : "Planeeritud OFF");
      const tooltip = `${new Date(hour.start).toLocaleString()}\n${status}\nOstuhind ${hour.import_eur_mwh.toFixed(1)} €/MWh\nEfektiivhind ${this._effectiveForHour(device, hour).toFixed(1)} €/MWh\nPV ${(hour.pv_wh / 1000).toFixed(2)} kWh`;
      const segmentRect = (segmentStart, segmentEnd, fill) => {
        const clippedStart = Math.max(start, segmentStart);
        const clippedEnd = Math.min(end, segmentEnd);
        if (clippedEnd <= clippedStart) return "";
        const segmentX = x + (clippedStart - start) / (end - start) * barWidth;
        const segmentWidth = Math.max(.6, (clippedEnd - clippedStart) / (end - start) * barWidth);
        return `<rect x="${segmentX}" y="${rectY}" width="${segmentWidth}" height="${rectHeight}" fill="${fill}"/>`;
      };
      const actualSegments = (actual?.segments || []).map(([from, to]) =>
        segmentRect(from, to, "#157347")
      ).join("");
      const plannedSegments = planSlots.map((slot) => {
        const slotStart = Math.max(now, new Date(slot.start).getTime());
        const slotEnd = new Date(slot.end || slotStart + 3600000).getTime();
        return segmentRect(slotStart, slotEnd, slot.active ? "#25a244" : "#f59e0b");
      }).join("");
      const markerX = left + index * step + step / 2;
      const marker = current
        ? `<path class="current-marker" d="M ${markerX - 6} ${top + 2} H ${markerX + 6} L ${markerX} ${top + 12} Z"><title>Praegune tund</title></path>`
        : "";
      return `<g><title>${this._escape(tooltip)}</title><rect x="${x}" y="${rectY}" width="${barWidth}" height="${rectHeight}" rx="2" fill="${start < now ? "#9e9e9e" : "#f59e0b"}"/>${actualSegments}${plannedSegments}</g>${marker}`;
    }).join("");
    const points = hours.flatMap((hour, index) => {
      const hourStart = new Date(hour.start).getTime();
      const hourEnd = new Date(hour.end || hourStart + 3600000).getTime();
      const slots = this._overlappingSlots(device, hour);
      if (!slots.length) {
        return [`${left + index * step + step / 2},${y(hour.import_eur_mwh)}`];
      }
      return slots.map((slot) => {
        const slotStart = new Date(slot.start).getTime();
        const slotEnd = new Date(slot.end || slotStart + 3600000).getTime();
        const midpoint = (slotStart + slotEnd) / 2;
        const x = left + index * step + (midpoint - hourStart) / (hourEnd - hourStart) * step;
        return `${x},${y(Number(slot.effective_eur_mwh))}`;
      });
    }).join(" ");
    const grid = [0, .25, .5, .75, 1].map((ratio) => {
      const lineY = top + ratio * plotHeight;
      return `<line x1="${left}" y1="${lineY}" x2="${width - right}" y2="${lineY}" stroke="var(--divider-color,#ddd)" stroke-dasharray="3 3"/>`;
    }).join("");
    const yAxisLabels = [0, .25, .5, .75, 1].map((ratio) => {
      const value = maximum - ratio * (maximum - minimum);
      const lineY = top + ratio * plotHeight;
      return `<span style="top:${lineY}px">${value.toFixed(0)}</span>`;
    }).join("");
    const labels = hours.map((hour, index) => {
      const stamp = new Date(hour.start);
      const hourLabel = this._formatHour(stamp);
      const x = left + index * step + step / 2;
      const valueY = y(hour.import_eur_mwh);
      const barBottom = Math.max(valueY, baseline);
      const labelY = barBottom - 10;
      const labelOnBar = Math.abs(baseline - valueY) >= 18;
      return `<text class="hour-label ${labelOnBar ? "on-bar" : "off-bar"}" x="${x}" y="${labelY}" text-anchor="middle" dominant-baseline="central" transform="rotate(-90 ${x} ${labelY})">${hourLabel}</text>`;
    }).join("");
    const stateText = device.state.observed_active === true ? "praegu sees" : device.state.observed_active === false ? "praegu väljas" : "tegelik olek teadmata";
    const solarText = this.data.solar_source === "fallback" ? "PV varuplaan" : this.data.solar_source === "forecast" ? "PV prognoos" : "ilma PV-ta";
    this.shadowRoot.innerHTML = `<style>
      :host{display:block}ha-card{padding:var(--ha-space-4,16px);overflow:hidden}.head{display:flex;justify-content:space-between;align-items:flex-start;gap:var(--ha-space-3,12px)}.card-title{color:var(--ha-card-header-color,var(--primary-text-color));font-family:var(--ha-card-header-font-family,inherit);font-size:var(--ha-card-header-font-size,var(--ha-font-size-2xl,24px));font-weight:var(--ha-font-weight-normal,400);letter-spacing:-.012em;line-height:var(--ha-line-height-expanded,1.5);margin:0 0 var(--ha-space-1,4px)}.sub{color:var(--secondary-text-color);font-size:var(--ha-font-size-m,14px)}.chart-wrap{position:relative;margin:var(--ha-space-3,12px) 0 0 -8px;width:calc(100% + 8px)}.scroll{overflow-x:auto;padding-bottom:var(--ha-space-1,4px)}svg{display:block;height:auto;max-width:none}svg text{font-family:var(--ha-font-family-body,inherit);font-size:var(--ha-font-size-s,12px);fill:var(--secondary-text-color)}svg .hour-label{font-size:12px;font-weight:var(--ha-font-weight-medium,500);fill:#fff}svg .hour-label.off-bar{fill:#000}.current-marker{fill:var(--error-color,#e53935)}.y-axis{position:absolute;z-index:2;left:0;top:0;width:28px;height:${chartHeight}px;pointer-events:none;background:var(--ha-card-background,var(--card-background-color,#fff))}.y-axis span{position:absolute;right:2px;transform:translateY(-50%);font-size:11px;font-weight:var(--ha-font-weight-medium,500);color:var(--secondary-text-color)}.legend{display:flex;gap:var(--ha-space-4,16px);flex-wrap:wrap;font-size:var(--ha-font-size-m,14px);margin-top:var(--ha-space-3,12px);color:var(--secondary-text-color)}.key{display:inline-flex;gap:var(--ha-space-1,4px);align-items:center}.swatch{width:12px;height:12px;border-radius:var(--ha-border-radius-sm,4px)}.line{width:20px;border-top:3px solid #2196f3}.badge{font-size:var(--ha-font-size-s,12px);padding:var(--ha-space-1,4px) var(--ha-space-2,8px);border-radius:var(--ha-border-radius-pill,999px);background:var(--warning-color,#f5a623);color:#111}.badge.live{background:var(--success-color,#43a047);color:white}.error{padding:var(--ha-space-4,16px);color:var(--error-color,#db4437)}
    </style><ha-card>
      <div class="head"><div><h1 class="card-title">${this._escape(this.config.title)}</h1><div class="sub">${this._escape(device.name)} · ${stateText} · ${solarText} · ${this._escape(device.state.reason)}</div></div><span class="badge ${this.data.shadow_mode ? "" : "live"}">${this.data.shadow_mode ? "VARIREŽIIM" : "AKTIIVNE"}</span></div>
      ${this.data.error ? `<div class="error">${this._escape(this.data.error)}</div>` : ""}
      <div class="chart-wrap"><div class="y-axis" aria-label="Hinnaskaala eurot megavatt-tunni kohta">${yAxisLabels}</div><div class="scroll"><svg style="width:${width}px" viewBox="0 0 ${width} ${chartHeight}" role="img" aria-label="Elektrihinna ja seadme tööplaani graafik">${grid}<line x1="${left}" y1="${baseline}" x2="${width - right}" y2="${baseline}" stroke="var(--primary-text-color)"/>${bars}<polyline points="${points}" fill="none" stroke="#2196f3" stroke-width="3" stroke-linejoin="round" stroke-linecap="round"/>${labels}</svg></div></div>
      <div class="legend"><span class="key"><i class="swatch" style="background:#157347"></i>tegelikult ON</span><span class="key"><i class="swatch" style="background:#9e9e9e"></i>möödunud OFF</span><span class="key"><i class="swatch" style="background:#25a244"></i>planeeritud ON</span><span class="key"><i class="swatch" style="background:#f59e0b"></i>planeeritud OFF</span><span class="key"><i class="line"></i>efektiivhind koos PV-ga</span></div>
    </ha-card>`;
    const currentHourKey = Math.floor(now / 3600000);
    if (this._centeredHourKey !== currentHourKey) {
      requestAnimationFrame(() => {
        const scroll = this.shadowRoot.querySelector(".scroll");
        const currentIndex = hours.findIndex((hour) => {
          const start = new Date(hour.start).getTime();
          return start <= now && now < start + 3600000;
        });
        if (scroll && currentIndex >= 0) {
          const currentX = left + currentIndex * step + step / 2;
          scroll.scrollLeft = Math.max(0, currentX - scroll.clientWidth / 2);
        }
        this._centeredHourKey = currentHourKey;
      });
    }
    this._scheduleHourCenter();
  }
}

customElements.define("smart-energy-price-plan-card", SmartEnergyPricePlanCard);
window.customCards.push({
  type: "smart-energy-price-plan-card",
  name: "Smart Energy Price & Device Plan",
  description: "Price bars colored by planned device activity",
  preview: true,
});

class SmartEnergyHeatingCurveCard extends SmartEnergySchedulerCard {
  setConfig(config) {
    super.setConfig({ title: "Soojuspumba küttekõver", ...config });
  }

  _selectedDevice() {
    const entries = Object.entries(this.data?.devices || {});
    return entries.find(([id, device]) =>
      id === this.config.device_id ||
      device.name === this.config.device ||
      device.target_entity === this.config.target_entity
    ) || entries[0];
  }

  _curveHours(temperature, settings) {
    const calculated = Number(settings.base_hours) +
      (Number(settings.reference_temperature) - temperature) * Number(settings.hours_per_degree);
    return Math.max(Number(settings.min_hours), Math.min(Number(settings.max_hours), Math.round(calculated)));
  }

  async _saveSettings(deviceId) {
    const payload = { device_id: deviceId, entry_id: this.data.entry_id };
    this.shadowRoot.querySelectorAll("[data-setting]").forEach((input) => {
      const enable = this.shadowRoot.querySelector(`[data-enable="${input.dataset.setting}"]`);
      if (enable) {
        payload[`${input.dataset.setting.replace("_eur_mwh", "")}_enabled`] = enable.checked;
        if (!enable.checked) return;
      }
      payload[input.dataset.setting] = input.localName === "ha-switch" ? input.checked : Number(input.value);
    });
    this.shadowRoot.querySelectorAll("[data-choice-setting]").forEach((choice) => {
      payload[choice.dataset.choiceSetting] = Number(choice.dataset.value);
    });
    const status = this.shadowRoot.querySelector(".save-status");
    if (payload.min_hours > payload.max_hours) {
      status.textContent = "Miinimum ei tohi olla maksimumist suurem.";
      status.classList.add("error");
      return;
    }
    if (payload.always_on_below_enabled && payload.always_off_above_enabled &&
        payload.always_on_below_eur_mwh >= payload.always_off_above_eur_mwh) {
      status.textContent = "Alati-ON hinnapiir peab olema madalam kui alati-OFF hinnapiir.";
      status.classList.add("error");
      return;
    }
    status.textContent = "Salvestan…";
    status.classList.remove("error");
    try {
      await this._hass.callService("smart_energy_scheduler", "update_device_settings", payload);
      status.textContent = "Salvestatud. Uus plaan arvutatakse…";
    } catch (err) {
      status.textContent = `Salvestamine ebaõnnestus: ${err.message || err}`;
      status.classList.add("error");
    }
  }

  _render() {
    if (!this.data) return;
    const selected = this._selectedDevice();
    if (!selected) {
      this.shadowRoot.innerHTML = `<ha-card><div class="error">Ühtegi juhitavat seadet ei ole seadistatud.</div></ha-card>`;
      return;
    }
    const [deviceId, device] = selected;
    const settings = device.settings || {};
    const plan = device.plan || {};
    const temperatures = plan.apparent_temperatures || {};
    const required = plan.required_hours || {};
    const width = 680, height = 310, left = 52, right = 18, top = 28, bottom = 52;
    const minimumTemperature = Number(this.config.min_temperature ?? -25);
    const maximumTemperature = Number(this.config.max_temperature ?? 25);
    const maximumHours = 25;
    const x = (temperature) => left +
      (temperature - minimumTemperature) / (maximumTemperature - minimumTemperature) *
      (width - left - right);
    const y = (hours) => top + (maximumHours - hours) / maximumHours * (height - top - bottom);
    const curve = [];
    for (let temperature = minimumTemperature; temperature <= maximumTemperature; temperature += .5) {
      curve.push(`${x(temperature)},${y(this._curveHours(temperature, settings))}`);
    }
    const horizontalGrid = [0, 6, 12, 18, 24].map((hours) =>
      `<line x1="${left}" y1="${y(hours)}" x2="${width - right}" y2="${y(hours)}" stroke="var(--divider-color,#ddd)" stroke-dasharray="3 3"/><text class="axis-label" x="${left - 8}" y="${y(hours) + 5}" text-anchor="end">${hours} h</text>`
    ).join("");
    const verticalGrid = [-20, -10, 0, 10, 20].filter((value) =>
      value >= minimumTemperature && value <= maximumTemperature
    ).map((temperature) =>
      `<line x1="${x(temperature)}" y1="${top}" x2="${x(temperature)}" y2="${height - bottom}" stroke="var(--divider-color,#ddd)" stroke-dasharray="3 3"/><text class="axis-label" x="${x(temperature)}" y="${height - bottom + 25}" text-anchor="middle">${temperature} °C</text>`
    ).join("");
    const forecastPoints = Object.entries(temperatures).map(([day, temperature], index) => {
      const hours = required[day] ?? this._curveHours(Number(temperature), settings);
      const color = index === 0 ? "#ef6c00" : "#7b1fa2";
      const pointX = x(Number(temperature));
      const pointY = y(Number(hours));
      const labelOnLeft = pointX > width - 210;
      const labelX = pointX + (labelOnLeft ? -12 : 12);
      const labelY = Math.max(top + 14, Math.min(height - bottom - 8,
        pointY + (index % 2 === 0 ? -13 : 23)));
      return `<g><circle cx="${pointX}" cy="${pointY}" r="7" fill="${color}" stroke="var(--card-background-color,#fff)" stroke-width="2"><title>${this._escape(day)}: ${Number(temperature).toFixed(1)} °C → ${hours} h</title></circle><text x="${labelX}" y="${labelY}" text-anchor="${labelOnLeft ? "end" : "start"}" class="point-label">${this._escape(day)} · ${Number(temperature).toFixed(1)}° · ${hours}h</text></g>`;
    }).join("");
    const fields = [
      ["base_hours", "Baastunnid", 0, 25, 1, "h"],
      ["reference_temperature", "Referentstemperatuur", -30, 30, .5, "°C"],
      ["hours_per_degree", "Mõju kraadi kohta", 0, 5, .1, "h/°C"],
      ["min_hours", "Miinimum", 0, 25, 1, "h"],
      ["max_hours", "Maksimum", 0, 25, 1, "h"],
      ["weather_lookahead_hours", "Keskmistamise aken", 1, 48, 1, "h"],
      ["preheat_hours", "Prognoosiakna nihe tulevikku", 0, 24, 1, "h"],
    ].map(([key, label, min, max, step, unit]) => {
      const value = Number(settings[key] ?? 0);
      return `<label class="slider"><span><b>${label}</b><output data-value="${key}">${value} ${unit}</output></span><ha-slider data-setting="${key}" data-value="${value}" data-unit="${unit}" min="${min}" max="${max}" step="${step}" value="${value}" with-tooltip></ha-slider></label>`;
    }).join("");
    const planningStep = Number(settings.planning_step_minutes) === 15 ? 15 : 60;
    const planningStepChoice = `<div class="step-choice" data-choice-setting="planning_step_minutes" data-value="${planningStep}"><span>Planeerimise samm</span><div class="step-buttons"><ha-button data-planning-step="15" variant="${planningStep === 15 ? "brand" : "neutral"}" appearance="${planningStep === 15 ? "filled" : "outlined"}">15 min</ha-button><ha-button data-planning-step="60" variant="${planningStep === 60 ? "brand" : "neutral"}" appearance="${planningStep === 60 ? "filled" : "outlined"}">60 min</ha-button></div></div>`;
    const priceFields = [
      ["always_on_below_eur_mwh", "Alati sees hinnaga kuni", 0, 1000, 5, "€/MWh", 0],
      ["always_off_above_eur_mwh", "Alati väljas hinnaga alates", 0, 1000, 5, "€/MWh", 500],
    ].map(([key, label, min, max, step, unit, fallback]) => {
      const enabled = settings[key] !== null && settings[key] !== undefined;
      const value = enabled ? Number(settings[key]) : fallback;
      return `<label class="slider optional-price"><span><b>${label}</b><span class="price-value"><ha-switch data-enable="${key}" ${enabled ? "checked" : ""}></ha-switch><output data-value="${key}">${value} ${unit}</output></span></span><ha-slider data-setting="${key}" data-value="${value}" data-unit="${unit}" min="${min}" max="${max}" step="${step}" value="${value}" ${enabled ? "" : "disabled"} with-tooltip></ha-slider></label>`;
    }).join("");
    const realFeelMode = `<ha-switch class="check" data-setting="legacy_wind_chill" ${settings.legacy_wind_chill !== false ? "checked" : ""}>Kasuta varasema YAML-i tuulekülma arvutust</ha-switch>`;
    const summary = Object.entries(temperatures).map(([day, temperature]) =>
      `${day}: ${Number(temperature).toFixed(1)} °C → ${required[day] ?? "–"} h`
    ).join(" · ");
    this.shadowRoot.innerHTML = `<style>
      :host{display:block;min-width:0}ha-card{padding:var(--ha-space-4,16px);overflow:hidden}.head{display:flex;justify-content:space-between;gap:var(--ha-space-3,12px);align-items:flex-start}.card-title{color:var(--ha-card-header-color,var(--primary-text-color));font-family:var(--ha-card-header-font-family,inherit);font-size:var(--ha-card-header-font-size,var(--ha-font-size-2xl,24px));font-weight:var(--ha-font-weight-normal,400);letter-spacing:-.012em;line-height:var(--ha-line-height-expanded,1.5);margin:0 0 var(--ha-space-1,4px)}.sub,.note,.save-status{font-size:var(--ha-font-size-m,14px);color:var(--secondary-text-color)}.chart{overflow:hidden;margin-top:var(--ha-space-3,12px);width:100%;min-width:0}svg{display:block;width:100%;max-width:100%;min-width:0;height:auto}svg text{font-family:var(--ha-font-family-body,inherit);font-size:12px;fill:var(--secondary-text-color)}svg .axis-label{font-size:16px;font-weight:var(--ha-font-weight-normal,400);fill:var(--primary-text-color)}svg .point-label{font-size:14px;font-weight:var(--ha-font-weight-medium,500);fill:var(--primary-text-color)}.curve-legend{display:flex;flex-wrap:wrap;gap:var(--ha-space-2,8px) var(--ha-space-4,16px);font-size:var(--ha-font-size-s,12px);color:var(--secondary-text-color);margin:-4px 0 var(--ha-space-2,8px)}.curve-legend span{display:flex;align-items:center;gap:var(--ha-space-2,8px)}.curve-legend i{display:inline-block;width:24px;height:0;border-top:3px solid #2196f3}.curve-legend .saved-line{border-top-color:var(--secondary-text-color,#777);border-top-style:dashed}.settings{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:var(--ha-space-4,16px);margin-top:var(--ha-space-4,16px)}.slider,.step-choice{display:block;min-width:0}.slider>span{display:flex;justify-content:space-between;align-items:baseline;gap:var(--ha-space-2,8px);font-size:var(--ha-font-size-s,12px);color:var(--secondary-text-color);margin-bottom:var(--ha-space-1,4px)}.slider b{font-weight:var(--ha-font-weight-normal,400)}.slider output{color:var(--primary-text-color);white-space:nowrap}.slider ha-slider{display:block;width:100%;min-width:0}.step-choice>span{display:block;font-size:var(--ha-font-size-s,12px);color:var(--secondary-text-color);margin-bottom:var(--ha-space-2,8px)}.step-buttons{display:flex;gap:var(--ha-space-2,8px)}.step-buttons ha-button{flex:1}.price-value{display:flex;align-items:center;gap:var(--ha-space-2,8px)}.price-value ha-switch{transform:scale(.85)}.settings .check{grid-column:1/-1;color:var(--primary-text-color);font-size:var(--ha-font-size-m,14px)}.actions{display:flex;align-items:center;gap:var(--ha-space-3,12px);margin-top:var(--ha-space-4,16px)}.save-status.error,.error{color:var(--error-color,#db4437)}.formula{font-family:var(--ha-font-family-code,monospace);font-size:var(--ha-font-size-m,14px);color:var(--secondary-text-color);margin-top:var(--ha-space-2,8px)}.badge{font-size:var(--ha-font-size-s,12px);padding:var(--ha-space-1,4px) var(--ha-space-2,8px);border-radius:var(--ha-border-radius-pill,999px);background:var(--warning-color,#f5a623);color:#111}.badge.live{background:var(--success-color,#43a047);color:#fff}@media(max-width:600px){ha-card{padding:var(--ha-space-3,12px)}.settings{grid-template-columns:minmax(0,1fr)}.head{gap:var(--ha-space-2,8px)}}
    </style><ha-card>
      <div class="head"><div><h1 class="card-title">${this._escape(this.config.title)}</h1><div class="sub">${this._escape(device.name)} · ${this._escape(summary || "prognoos puudub")}</div><div class="formula">tunnid = ${Number(settings.base_hours)} + (${Number(settings.reference_temperature)} − temperatuur) × ${Number(settings.hours_per_degree)}</div></div><span class="badge ${this.data.shadow_mode ? "" : "live"}">${this.data.shadow_mode ? "VARIREŽIIM" : "AKTIIVNE"}</span></div>
      <div class="chart"><svg viewBox="0 0 ${width} ${height}" role="img" aria-label="Küttekõver: töötunnid sõltuvalt näivast välistemperatuurist">${horizontalGrid}${verticalGrid}<polyline class="saved-curve" points="${curve.join(" ")}" fill="none" stroke="var(--secondary-text-color,#777)" stroke-width="3" stroke-dasharray="8 7" stroke-linejoin="round"/><polyline class="preview-curve" points="${curve.join(" ")}" fill="none" stroke="#2196f3" stroke-width="4" stroke-linejoin="round"/>${forecastPoints}</svg></div>
      <div class="curve-legend"><span><i class="preview-line"></i>liugurite eelvaade</span><span><i class="saved-line"></i>salvestatud kõver</span></div>
      <div class="note">RealFeel-keskmine: ${Number(settings.weather_lookahead_hours)} h prognoosiaken, algus ${Number(settings.preheat_hours)} h ettepoole. Oranž/lilla punkt näitab prognoosist arvutatud vajadust.</div>
      <div class="settings">${fields}${planningStepChoice}${priceFields}${realFeelMode}</div>
      <div class="note">Planeerimise samm 15 min lubab algusi :00/:15/:30/:45; 60 min lubab ainult täistunde. Minimaalne ON/OFF kestus jääb tundidesse. Hinnapiirid kasutavad seadme efektiivhinda koos tariifide, käibemaksu ja PV prognoosiga. Päeva miinimumtunnid võivad alati-väljas piiri ohutuse huvides ületada.</div>
      <div class="actions"><ha-button class="save" variant="brand" appearance="filled">Rakenda ja arvuta plaan uuesti</ha-button><span class="save-status"></span></div>
    </ha-card>`;
    const legacySwitch = this.shadowRoot.querySelector("ha-switch[data-setting]");
    if (legacySwitch) legacySwitch.checked = settings.legacy_wind_chill !== false;
    this.shadowRoot.querySelector("ha-button.save").addEventListener("click", () =>
      this._saveSettings(deviceId)
    );
    this.shadowRoot.querySelectorAll("ha-slider[data-setting]").forEach((input) => {
      input.min = Number(input.getAttribute("min"));
      input.max = Number(input.getAttribute("max"));
      input.step = Number(input.getAttribute("step"));
      input.value = Number(input.dataset.value);
      input.addEventListener("input", () => {
        const output = this.shadowRoot.querySelector(`output[data-value="${input.dataset.setting}"]`);
        if (output) output.textContent = `${input.value} ${input.dataset.unit}`;
        if (["base_hours", "reference_temperature", "hours_per_degree", "min_hours", "max_hours"].includes(input.dataset.setting)) {
          const previewSettings = { ...settings };
          ["base_hours", "reference_temperature", "hours_per_degree", "min_hours", "max_hours"].forEach((key) => {
            const slider = this.shadowRoot.querySelector(`ha-slider[data-setting="${key}"]`);
            if (slider) previewSettings[key] = Number(slider.value);
          });
          const previewCurve = [];
          for (let temperature = minimumTemperature; temperature <= maximumTemperature; temperature += .5) {
            previewCurve.push(`${x(temperature)},${y(this._curveHours(temperature, previewSettings))}`);
          }
          this.shadowRoot.querySelector(".preview-curve")?.setAttribute("points", previewCurve.join(" "));
        }
      });
    });
    this.shadowRoot.querySelectorAll("ha-button[data-planning-step]").forEach((button) => {
      button.addEventListener("click", () => {
        const choice = button.closest("[data-choice-setting]");
        choice.dataset.value = button.dataset.planningStep;
        choice.querySelectorAll("ha-button[data-planning-step]").forEach((item) => {
          const selected = item.dataset.planningStep === choice.dataset.value;
          item.variant = selected ? "brand" : "neutral";
          item.appearance = selected ? "filled" : "outlined";
        });
      });
    });
    this.shadowRoot.querySelectorAll("ha-switch[data-enable]").forEach((enable) => {
      enable.checked = enable.hasAttribute("checked");
      const slider = this.shadowRoot.querySelector(
        `ha-slider[data-setting="${enable.dataset.enable}"]`
      );
      if (slider) slider.disabled = !enable.checked;
      enable.addEventListener("change", () => {
        if (slider) slider.disabled = !enable.checked;
      });
    });
  }
}

customElements.define("smart-energy-heating-curve-card", SmartEnergyHeatingCurveCard);
window.customCards.push({
  type: "smart-energy-heating-curve-card",
  name: "Smart Energy Heating Curve",
  description: "Editable weather-to-runtime curve with forecast points",
  preview: true,
});
