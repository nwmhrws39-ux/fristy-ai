/** Microphone capture -> 16 kHz mono WAV, with a simple energy VAD. */

export const TARGET_SR = 16000;

export function downsample(input: Float32Array, fromRate: number, toRate = TARGET_SR): Float32Array {
  if (fromRate === toRate) return input;
  const ratio = fromRate / toRate;
  const outLen = Math.floor(input.length / ratio);
  const out = new Float32Array(outLen);
  for (let i = 0; i < outLen; i++) {
    const start = Math.floor(i * ratio);
    const end = Math.min(input.length, Math.floor((i + 1) * ratio));
    let sum = 0;
    for (let j = start; j < end; j++) sum += input[j];
    out[i] = sum / Math.max(1, end - start);
  }
  return out;
}

export function encodeWav(samples: Float32Array, sampleRate = TARGET_SR): ArrayBuffer {
  const buf = new ArrayBuffer(44 + samples.length * 2);
  const v = new DataView(buf);
  const w = (o: number, s: string) => { for (let i = 0; i < s.length; i++) v.setUint8(o + i, s.charCodeAt(i)); };
  w(0, "RIFF"); v.setUint32(4, 36 + samples.length * 2, true); w(8, "WAVE"); w(12, "fmt ");
  v.setUint32(16, 16, true); v.setUint16(20, 1, true); v.setUint16(22, 1, true); v.setUint32(24, sampleRate, true);
  v.setUint32(28, sampleRate * 2, true); v.setUint16(32, 2, true); v.setUint16(34, 16, true); w(36, "data");
  v.setUint32(40, samples.length * 2, true);
  for (let i = 0; i < samples.length; i++) {
    const s = Math.max(-1, Math.min(1, samples[i]));
    v.setInt16(44 + i * 2, s < 0 ? s * 0x8000 : s * 0x7fff, true);
  }
  return buf;
}

export function rms(frame: Float32Array): number {
  let s = 0;
  for (let i = 0; i < frame.length; i++) s += frame[i] * frame[i];
  return Math.sqrt(s / Math.max(1, frame.length));
}

function concat(chunks: Float32Array[]): Float32Array {
  const total = chunks.reduce((n, c) => n + c.length, 0);
  const out = new Float32Array(total);
  let o = 0;
  for (const c of chunks) { out.set(c, o); o += c.length; }
  return out;
}

export interface MicOptions {
  deviceId?: string;
  onLevel?: (level: number) => void;
}

/** Owns the microphone stream. Frames are delivered at 16 kHz. */
export class Microphone {
  private stream: MediaStream | null = null;
  private ctx: AudioContext | null = null;
  private node: ScriptProcessorNode | null = null;
  private source: MediaStreamAudioSourceNode | null = null;
  private frameHandlers = new Set<(f: Float32Array) => void>();
  active = false;

  async open(opts: MicOptions = {}) {
    if (this.active) return;
    this.stream = await navigator.mediaDevices.getUserMedia({
      audio: { deviceId: opts.deviceId ? { exact: opts.deviceId } : undefined, echoCancellation: true,
               noiseSuppression: true, autoGainControl: true, channelCount: 1 },
    });
    this.ctx = new AudioContext();
    this.source = this.ctx.createMediaStreamSource(this.stream);
    this.node = this.ctx.createScriptProcessor(4096, 1, 1);
    const rate = this.ctx.sampleRate;
    this.node.onaudioprocess = (e) => {
      const frame = downsample(new Float32Array(e.inputBuffer.getChannelData(0)), rate);
      opts.onLevel?.(Math.min(1, rms(frame) * 6));
      this.frameHandlers.forEach((h) => h(frame));
    };
    this.source.connect(this.node);
    this.node.connect(this.ctx.destination);
    this.active = true;
  }

  onFrame(h: (f: Float32Array) => void) {
    this.frameHandlers.add(h);
    return () => this.frameHandlers.delete(h);
  }

  close() {
    this.node?.disconnect();
    this.source?.disconnect();
    this.stream?.getTracks().forEach((t) => t.stop());
    void this.ctx?.close();
    this.node = null; this.source = null; this.stream = null; this.ctx = null;
    this.frameHandlers.clear();
    this.active = false;
  }
}

/** Records until stop() or (with autoStop) until the speaker goes silent. */
export class Recording {
  private chunks: Float32Array[] = [];
  private off: () => void;
  private heardSpeech = false;
  private silentMs = 0;
  private totalMs = 0;
  done: Promise<Float32Array>;
  private resolve!: (s: Float32Array) => void;

  constructor(mic: Microphone, opts: { autoStop?: boolean; silenceMs?: number; maxMs?: number; threshold?: number } = {}) {
    const { autoStop = true, silenceMs = 1300, maxMs = 30000, threshold = 0.012 } = opts;
    this.done = new Promise((r) => (this.resolve = r));
    this.off = mic.onFrame((f) => {
      this.chunks.push(f);
      const ms = (f.length / TARGET_SR) * 1000;
      this.totalMs += ms;
      if (rms(f) > threshold) { this.heardSpeech = true; this.silentMs = 0; } else this.silentMs += ms;
      if ((autoStop && this.heardSpeech && this.silentMs > silenceMs) || this.totalMs > maxMs) this.stop();
      if (autoStop && !this.heardSpeech && this.totalMs > 8000) this.stop();
    });
  }

  stop() {
    this.off();
    this.resolve(concat(this.chunks));
  }
}

/** Continuous VAD that emits short speech segments (for local wake-word checks). */
export class SegmentDetector {
  private pre: Float32Array[] = [];
  private seg: Float32Array[] = [];
  private inSpeech = false;
  private speechMs = 0;
  private silenceMs = 0;
  private off: () => void;

  constructor(mic: Microphone, onSegment: (samples: Float32Array) => void, threshold = 0.018) {
    this.off = mic.onFrame((f) => {
      const ms = (f.length / TARGET_SR) * 1000;
      const loud = rms(f) > threshold;
      if (!this.inSpeech) {
        this.pre.push(f);
        if (this.pre.length > 2) this.pre.shift();
        if (loud) { this.inSpeech = true; this.seg = [...this.pre, ]; this.speechMs = 0; this.silenceMs = 0; }
        return;
      }
      this.seg.push(f);
      this.speechMs += ms;
      this.silenceMs = loud ? 0 : this.silenceMs + ms;
      if (this.silenceMs > 700 || this.speechMs > 5000) {
        const samples = concat(this.seg);
        this.inSpeech = false; this.seg = []; this.pre = [];
        if (this.speechMs - this.silenceMs > 250) onSegment(samples);
      }
    });
  }

  stop() { this.off(); }
}
