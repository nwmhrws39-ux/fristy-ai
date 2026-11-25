import type { BridgeConfig } from "./bridge";

let cfg: BridgeConfig | null = null;

export function setApiConfig(c: BridgeConfig) {
  cfg = c;
}

export function apiBase(): string {
  return `http://127.0.0.1:${cfg?.port ?? 8765}`;
}

export function wsUrl(): string {
  return `ws://127.0.0.1:${cfg?.port ?? 8765}/ws?token=${encodeURIComponent(cfg?.token ?? "")}`;
}

export class ApiError extends Error {
  constructor(message: string, public status: number, public code?: string) {
    super(message);
  }
}

export async function api<T = any>(path: string, opts: { method?: string; body?: unknown; raw?: BodyInit; headers?: Record<string, string>; signal?: AbortSignal; blob?: boolean } = {}): Promise<T> {
  const headers: Record<string, string> = { Authorization: `Bearer ${cfg?.token ?? ""}`, ...(opts.headers || {}) };
  let body: BodyInit | undefined = opts.raw;
  if (opts.body !== undefined) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(opts.body);
  }
  let res: Response;
  try {
    res = await fetch(apiBase() + path, { method: opts.method || (body ? "POST" : "GET"), headers, body, signal: opts.signal });
  } catch (e) {
    throw new ApiError("FRISTY backend is not reachable.", 0);
  }
  if (!res.ok) {
    let msg = res.statusText, code: string | undefined;
    try {
      const j = await res.json();
      msg = typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail);
      code = j.code;
    } catch {
      /* not json */
    }
    throw new ApiError(msg, res.status, code);
  }
  if (opts.blob) return (await res.blob()) as T;
  const text = await res.text();
  return (text ? JSON.parse(text) : null) as T;
}
