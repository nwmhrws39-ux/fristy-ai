import { wsUrl } from "./api";

export type BackendEvent = { type: string; ts: number; [k: string]: any };
type Handler = (ev: BackendEvent) => void;

/** Reconnecting WebSocket for backend events. */
export class EventStream {
  private ws: WebSocket | null = null;
  private handlers = new Set<Handler>();
  private retry = 0;
  private timer: number | undefined;
  private pingTimer: number | undefined;
  private closed = false;
  onStatus: (connected: boolean) => void = () => {};

  connect() {
    this.closed = false;
    try {
      this.ws = new WebSocket(wsUrl());
    } catch {
      this.schedule();
      return;
    }
    this.ws.onopen = () => {
      this.retry = 0;
      this.onStatus(true);
      this.pingTimer = window.setInterval(() => this.ws?.readyState === 1 && this.ws.send("ping"), 15000);
    };
    this.ws.onmessage = (m) => {
      if (m.data === "pong") return;
      try {
        const ev = JSON.parse(m.data) as BackendEvent;
        this.handlers.forEach((h) => h(ev));
      } catch {
        /* ignore */
      }
    };
    this.ws.onclose = () => {
      window.clearInterval(this.pingTimer);
      this.onStatus(false);
      if (!this.closed) this.schedule();
    };
    this.ws.onerror = () => this.ws?.close();
  }

  private schedule() {
    window.clearTimeout(this.timer);
    const delay = Math.min(10000, 500 * 2 ** this.retry++);
    this.timer = window.setTimeout(() => this.connect(), delay);
  }

  close() {
    this.closed = true;
    window.clearTimeout(this.timer);
    this.ws?.close();
  }

  subscribe(h: Handler) {
    this.handlers.add(h);
    return () => this.handlers.delete(h);
  }
}

export const events = new EventStream();
