import { useSyncExternalStore } from "react";

export type OrbState = "idle" | "listening" | "thinking" | "speaking" | "executing" | "error";
export type Page = "chat" | "dashboard" | "automations" | "memory" | "history" | "settings";

export interface ActionEntry {
  id: string;
  name: string;
  arguments: Record<string, any>;
  ok?: boolean;
  message?: string;
  verified?: boolean | null;
  code?: string;
  data?: any;
  pending?: boolean;
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  streaming?: boolean;
  actions: ActionEntry[];
  warning?: string | null;
  plan?: any;
  images?: string[];
  mode?: string;
  runId?: string;
  ts: number;
  meta?: any;
}

export interface Confirmation {
  id: string;
  action: string;
  summary: string;
  risk: "low" | "medium" | "high";
  source: string;
  details: any;
  timeout: number;
  receivedAt: number;
}

export interface Toast {
  id: number;
  kind: "info" | "success" | "error" | "warning";
  text: string;
}

export interface AppState {
  backendReady: boolean;
  backendError: string;
  wsConnected: boolean;
  compact: boolean;
  page: Page;
  settings: any | null;
  status: any | null;
  models: any | null;
  conversations: any[];
  conversationId: string | null;
  messages: ChatMessage[];
  activeRun: { id: string; mode: string; paused: boolean; state: string; cloud?: boolean } | null;
  orb: OrbState;
  confirmations: Confirmation[];
  toasts: Toast[];
  micEnabled: boolean;
  listening: boolean;
  micLevel: number;
  speaking: boolean;
  screenActive: boolean;
  wakeListening: boolean;
  transcribing: boolean;
  metrics: any | null;
  warnings: string[];
  latency: { total_ms?: number; first_token_ms?: number } | null;
  shortcutFailures: string[];
  lastInputWasVoice?: boolean;
  pulls: Record<string, any>;
  localModels: any | null;
  update: any | null;
  updateOpen: boolean;
  updateChecking: boolean;
  updateInstalling: boolean;
  updateProgress: { received: number; total: number } | null;
}

const initial: AppState = {
  backendReady: false, backendError: "", wsConnected: false, compact: false, page: "chat",
  settings: null, status: null, models: null, conversations: [], conversationId: null, messages: [],
  activeRun: null, orb: "idle", confirmations: [], toasts: [], micEnabled: true, listening: false, micLevel: 0,
  speaking: false, screenActive: false, wakeListening: false, transcribing: false, metrics: null, warnings: [],
  latency: null, shortcutFailures: [], pulls: {}, localModels: null,
  update: null, updateOpen: false, updateChecking: false, updateInstalling: false, updateProgress: null,
};

let state: AppState = initial;
const listeners = new Set<() => void>();

export function getState(): AppState {
  return state;
}

export function setState(patch: Partial<AppState> | ((s: AppState) => Partial<AppState>)) {
  const p = typeof patch === "function" ? patch(state) : patch;
  state = { ...state, ...p };
  listeners.forEach((l) => l());
}

export function subscribe(l: () => void) {
  listeners.add(l);
  return () => listeners.delete(l);
}

export function useStore<T>(selector: (s: AppState) => T): T {
  return useSyncExternalStore(subscribe, () => selector(state));
}

let toastId = 1;
export function toast(text: string, kind: Toast["kind"] = "info", ms = 4500) {
  const id = toastId++;
  setState((s) => ({ toasts: [...s.toasts, { id, kind, text }] }));
  window.setTimeout(() => setState((s) => ({ toasts: s.toasts.filter((t) => t.id !== id) })), ms);
}

export function resetForTests() {
  state = initial;
}
