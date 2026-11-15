// Ship sounds made with the Web Audio API (no sound files):
// a low engine hum, a rising whoosh during warp, and a chime on arrival.
// Starts only from a click (browsers block sound before that).

export class ShipAudio {
  private ctx: AudioContext | null = null;
  private master: GainNode | null = null;
  private humOsc: OscillatorNode[] = [];
  private noiseGain: GainNode | null = null;
  private noiseFilter: BiquadFilterNode | null = null;

  get on(): boolean {
    return this.ctx !== null;
  }

  start(): void {
    if (this.ctx) return;
    const ctx = new AudioContext();
    const master = ctx.createGain();
    master.gain.value = 0.5;
    master.connect(ctx.destination);

    // Engine hum: two slightly detuned saws through a low-pass filter.
    const humFilter = ctx.createBiquadFilter();
    humFilter.type = "lowpass";
    humFilter.frequency.value = 150;
    const humGain = ctx.createGain();
    humGain.gain.value = 0.06;
    humFilter.connect(humGain).connect(master);
    this.humOsc = [55, 55.6].map((f) => {
      const o = ctx.createOscillator();
      o.type = "sawtooth";
      o.frequency.value = f;
      o.connect(humFilter);
      o.start();
      return o;
    });

    // Warp whoosh: looping white noise through a band-pass, silent until warp.
    const buffer = ctx.createBuffer(1, ctx.sampleRate * 2, ctx.sampleRate);
    const data = buffer.getChannelData(0);
    for (let i = 0; i < data.length; i++) data[i] = Math.random() * 2 - 1;
    const noise = ctx.createBufferSource();
    noise.buffer = buffer;
    noise.loop = true;
    const filter = ctx.createBiquadFilter();
    filter.type = "bandpass";
    filter.frequency.value = 300;
    filter.Q.value = 0.9;
    const gain = ctx.createGain();
    gain.gain.value = 0;
    noise.connect(filter).connect(gain).connect(master);
    noise.start();

    this.ctx = ctx;
    this.master = master;
    this.noiseGain = gain;
    this.noiseFilter = filter;
  }

  stop(): void {
    void this.ctx?.close();
    this.ctx = null;
    this.master = null;
    this.humOsc = [];
    this.noiseGain = null;
    this.noiseFilter = null;
  }

  // Whoosh rises while warping, fades when we drop out of warp.
  setWarp(on: boolean): void {
    const ctx = this.ctx;
    if (!ctx || !this.noiseGain || !this.noiseFilter) return;
    const t = ctx.currentTime;
    this.noiseGain.gain.cancelScheduledValues(t);
    this.noiseGain.gain.setTargetAtTime(on ? 0.14 : 0, t, on ? 0.4 : 0.25);
    this.noiseFilter.frequency.cancelScheduledValues(t);
    this.noiseFilter.frequency.setTargetAtTime(on ? 1600 : 300, t, on ? 1.5 : 0.3);
    for (const o of this.humOsc) o.frequency.setTargetAtTime((on ? 1.5 : 1) * (o === this.humOsc[0] ? 55 : 55.6), t, 0.8);
  }

  // One short tone with a quick fade.
  private tone(freq: number, at: number, dur: number, type: OscillatorType = "sine", vol = 0.16): void {
    const ctx = this.ctx;
    if (!ctx || !this.master) return;
    const t = ctx.currentTime + at;
    const o = ctx.createOscillator();
    const g = ctx.createGain();
    o.type = type;
    o.frequency.value = freq;
    g.gain.setValueAtTime(0, t);
    g.gain.linearRampToValueAtTime(vol, t + 0.01);
    g.gain.exponentialRampToValueAtTime(0.0001, t + dur);
    o.connect(g).connect(this.master);
    o.start(t);
    o.stop(t + dur + 0.05);
  }

  // Target locked: three quick rising beeps.
  lockOn(): void {
    [660, 990, 1480].forEach((f, i) => this.tone(f, i * 0.07, 0.12, "square", 0.07));
  }

  // Missed: a short low buzz.
  miss(): void {
    this.tone(110, 0, 0.25, "sawtooth", 0.09);
  }

  // Mission complete or promotion: a bright arpeggio.
  fanfare(): void {
    [523.25, 659.25, 783.99, 1046.5].forEach((f, i) => this.tone(f, i * 0.09, 0.5, "triangle", 0.14));
  }

  // Two-note chime when a result arrives.
  chime(): void {
    const ctx = this.ctx;
    if (!ctx || !this.master) return;
    [880, 1318.5].forEach((f, i) => {
      const t = ctx.currentTime + i * 0.12;
      const o = ctx.createOscillator();
      const g = ctx.createGain();
      o.type = "sine";
      o.frequency.value = f;
      g.gain.setValueAtTime(0, t);
      g.gain.linearRampToValueAtTime(0.18, t + 0.02);
      g.gain.exponentialRampToValueAtTime(0.0001, t + 0.9);
      o.connect(g).connect(this.master!);
      o.start(t);
      o.stop(t + 1);
    });
  }
}
