class PulseAudioMeter extends HTMLElement {
  set hass(hass) {
    this._hass = hass;
  }

  get hass() {
    return this._hass;
  }

  setConfig(config) {
    this.config = config || {};

    if (this.shadowRoot) {
      this.shadowRoot.innerHTML = '';
    }

    this.attachShadow({ mode: 'open' });

    this.shadowRoot.innerHTML = `
      <style>
        ha-card {
          padding: 16px;
        }

        .title {
          font-size: 18px;
          font-weight: 600;
          margin-bottom: 12px;
        }

        .section {
          margin-top: 8px;
        }

        .label {
          font-weight: 600;
          margin-bottom: 5px;
        }

        .row {
          margin: 14px 0;
        }

        .bar {
          height: 22px;
          border-radius: 6px;
          background: #333;
          overflow: hidden;
        }

        .fill {
          height: 100%;
          width: 0%;
          transition: width 0.12s linear;
        }

        .peak {
          background: linear-gradient(
            90deg,
            #4caf50 0%,
            #8bc34a 60%,
            #ffc107 80%,
            #f44336 100%
          );
        }

        .rms {
          background: linear-gradient(
            90deg,
            #2196f3,
            #00bcd4,
            #4caf50
          );
        }

        .stats {
          display: flex;
          justify-content: space-between;
          font-size: 13px;
          margin: 5px 0 10px;
        }

        .controls {
          display: flex;
          align-items: center;
          gap: 10px;
          margin-top: 10px;
        }

        .controls input {
          flex: 1;
        }

        .mute {
          min-width: 80px;
        }

        .sep {
          border-top: 1px solid var(--divider-color, #444);
          margin: 18px 0;
        }

        .small {
          font-size: 12px;
          opacity: 0.75;
        }

        .device {
          font-size: 11px;
          opacity: 0.6;
          margin-top: 8px;
          word-break: break-all;
        }

        .error {
          color: var(--error-color, #f44336);
          font-size: 13px;
          margin-top: 10px;
        }
      </style>

      <ha-card>
        <div class="title">PulseAudio</div>

        <div class="section">
          <div class="label">🎙 Input</div>

          <div class="stats">
            <span>
              RMS <b id="ir">-60</b> dBFS
            </span>

            <span>
              Peak <b id="ip">-60</b> dBFS
            </span>
          </div>

          <div class="bar">
            <div id="irm" class="fill rms"></div>
          </div>

          <div class="small">RMS</div>

          <div class="bar">
            <div id="ipm" class="fill peak"></div>
          </div>

          <div class="small">Peak</div>

          <div class="controls">
            <input
              id="iv"
              type="range"
              min="0"
              max="100"
              step="1"
            >

            <span id="ivt">0%</span>

            <button id="im" class="mute">
              Mute
            </button>
          </div>

          <div id="idev" class="device"></div>
        </div>

        <div class="sep"></div>

        <div class="section">
          <div class="label">🔊 Output</div>

          <div class="stats">
            <span>
              RMS <b id="or">-60</b> dBFS
            </span>

            <span>
              Peak <b id="op">-60</b> dBFS
            </span>
          </div>

          <div class="bar">
            <div id="orm" class="fill rms"></div>
          </div>

          <div class="small">RMS</div>

          <div class="bar">
            <div id="opm" class="fill peak"></div>
          </div>

          <div class="small">Peak</div>

          <div class="controls">
            <input
              id="ov"
              type="range"
              min="0"
              max="100"
              step="1"
            >

            <span id="ovt">0%</span>

            <button id="om" class="mute">
              Mute
            </button>
          </div>

          <div id="odev" class="device"></div>
        </div>

        <div id="error" class="error"></div>
      </ha-card>
    `;

    this.stateUrl = 'pulse_audio_meter/state';
    this.controlUrl = 'pulse_audio_meter/control';

    this.timer = null;
    this.busy = false;

    this.setupControls();
    this.startPolling();
  }

  setupControls() {
    const iv = this.shadowRoot.getElementById('iv');
    const ov = this.shadowRoot.getElementById('ov');
    const im = this.shadowRoot.getElementById('im');
    const om = this.shadowRoot.getElementById('om');

    iv.addEventListener('change', () => {
      this.setVolume('input', Number(iv.value));
    });

    ov.addEventListener('change', () => {
      this.setVolume('output', Number(ov.value));
    });

    im.addEventListener('click', () => {
      const muted =
        im.dataset.muted === 'true';

      this.setMute('input', !muted);
    });

    om.addEventListener('click', () => {
      const muted =
        om.dataset.muted === 'true';

      this.setMute('output', !muted);
    });
  }

  startPolling() {
    this.stopPolling();

    this.updateState();

    this.timer = setInterval(
      () => this.updateState(),
      500
    );
  }

  stopPolling() {
    if (this.timer) {
      clearInterval(this.timer);
      this.timer = null;
    }
  }

  async updateState() {
    try {
      const state = await this._hass.callApi(
        'GET',
        this.stateUrl
      );

      this.updateMeter(
        'ir',
        'irm',
        state.input_rms
      );

      this.updateMeter(
        'ip',
        'ipm',
        state.input_peak
      );

      this.updateMeter(
        'or',
        'orm',
        state.output_rms
      );

      this.updateMeter(
        'op',
        'opm',
        state.output_peak
      );

      this.updateVolume(
        'iv',
        'ivt',
        state.input_volume
      );

      this.updateVolume(
        'ov',
        'ovt',
        state.output_volume
      );

      this.updateMute(
        'im',
        state.input_mute
      );

      this.updateMute(
        'om',
        state.output_mute
      );

      this.shadowRoot.getElementById('idev')
        .textContent =
        state.input_device || '';

      this.shadowRoot.getElementById('odev')
        .textContent =
        state.output_device || '';

      this.shadowRoot.getElementById('error')
        .textContent = '';

    } catch (error) {
      console.error(
        'PulseAudio Meter:',
        error
      );

      this.shadowRoot.getElementById('error')
        .textContent =
        `Errore collegamento: ${error.message}`;
    }
  }

  updateMeter(valueId, barId, value) {
    const valueElement =
      this.shadowRoot.getElementById(valueId);

    const barElement =
      this.shadowRoot.getElementById(barId);

    const numeric =
      Number.isFinite(Number(value))
        ? Number(value)
        : -60;

    valueElement.textContent =
      numeric.toFixed(1);

    /*
     * -60 dBFS = 0%
     *   0 dBFS = 100%
     */
    const percent =
      Math.max(
        0,
        Math.min(
          100,
          ((numeric + 60) / 60) * 100
        )
      );

    barElement.style.width =
      `${percent}%`;
  }

  updateVolume(sliderId, textId, value) {
    const slider =
      this.shadowRoot.getElementById(sliderId);

    const text =
      this.shadowRoot.getElementById(textId);

    const numeric =
      Math.max(
        0,
        Math.min(
          100,
          Number(value) || 0
        )
      );

    /*
     * Non modificare lo slider mentre
     * l'utente lo sta trascinando.
     */
    if (document.activeElement !== slider) {
      slider.value = numeric;
    }

    text.textContent =
      `${Math.round(numeric)}%`;
  }

  updateMute(buttonId, muted) {
    const button =
      this.shadowRoot.getElementById(buttonId);

    const state =
      Boolean(muted);

    button.dataset.muted =
      state ? 'true' : 'false';

    button.textContent =
      state ? 'Unmute' : 'Mute';
  }

  async setVolume(target, volume) {
    try {
      await this._hass.callApi(
        'POST',
        this.controlUrl,
        {
          target,
          volume
        }
      );

      await this.updateState();

    } catch (error) {
      console.error(
        'PulseAudio volume:',
        error
      );
    }
  }

  async setMute(target, mute) {
    try {
      await this._hass.callApi(
        'POST',
        this.controlUrl,
        {
          target,
          mute
        }
      );

      await this.updateState();

    } catch (error) {
      console.error(
        'PulseAudio mute:',
        error
      );
    }
  }

  disconnectedCallback() {
    this.stopPolling();
  }
}

customElements.define(
  'pulse-audio-meter',
  PulseAudioMeter
);

window.customCards =
  window.customCards || [];

window.customCards.push({
  type: 'pulse-audio-meter',
  name: 'PulseAudio Meter',
  description:
    'Live PulseAudio input/output meter and controls'
});
