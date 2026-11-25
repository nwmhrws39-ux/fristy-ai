export interface BridgeConfig {
  port: number;
  token: string;
  ready: boolean;
  error: string;
  platform: string;
  version: string;
  compact: boolean;
}

export interface FristyBridge {
  getConfig(): Promise<BridgeConfig>;
  minimize(): Promise<void>;
  maximize(): Promise<void>;
  close(): Promise<void>;
  setCompact(on: boolean): Promise<void>;
  applySettings(): Promise<void>;
  restartBackend(): Promise<boolean>;
  openExternal(url: string): Promise<void>;
  emergencyStop(): Promise<void>;
  pickFolder(): Promise<string | null>;
  show(): Promise<void>;
  on(channel: string, fn: (...args: any[]) => void): () => void;
}

declare global {
  interface Window {
    fristy?: FristyBridge;
  }
}

/** Browser fallback (vite dev without Electron): talks to a backend on FRISTY dev port 8765. */
const devBridge: FristyBridge = {
  async getConfig() {
    const params = new URLSearchParams(location.search);
    return { port: Number(params.get("port") || 8765), token: params.get("token") || "dev", ready: true, error: "",
             platform: "browser", version: "dev", compact: false };
  },
  async minimize() {}, async maximize() {}, async close() {}, async setCompact() {}, async applySettings() {},
  async restartBackend() { return false; },
  async openExternal(url) { window.open(url, "_blank", "noopener"); },
  async emergencyStop() {},
  async show() { window.focus(); },
  async pickFolder() { return window.prompt("Absolute folder path"); },
  on() { return () => {}; },
};

export const bridge: FristyBridge = window.fristy ?? devBridge;
export const inElectron = !!window.fristy;
