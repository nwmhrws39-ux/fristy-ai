/** App controller: bootstraps the backend connection and turns backend events into UI state. */
import { api, ApiError, setApiConfig } from "./api";
import { bridge } from "./bridge";
import { BackendEvent, events } from "./events";
import { Microphone, Recording, SegmentDetector, encodeWav } from "./audio";
import { ChatMessage, getState, setState, toast } from "./store";
import { speak, stopSpeaking } from "./tts";
import { translate } from "./i18n";

const t = (k: Parameters<typeof translate>[1], v?: Record<string, string | number>) =>
  translate(getState().settings?.ui?.language === "he" ? "he" : "en", k, v);

let statusTimer: number | undefined;
let started = false;

export async function boot() {
  if (started) return;
  started = true;
  const cfg = await bridge.getConfig();
  setApiConfig(cfg);
  setState({ compact: cfg.compact, backendError: cfg.error });
  bridge.on("backend:status", (s: { ready: boolean; error?: string }) => {
    setState({ backendReady: s.ready, backendError: s.error || "" });
    if (s.ready) void onBackendReady();
  });
  bridge.on("emergency-stop", () => onEmergencyStop());
  bridge.on("push-to-talk", () => void pushToTalk());
  bridge.on("window:compact", (c: boolean) => setState({ compact: c }));
  bridge.on("shortcuts:status", (s: { failed: string[] }) => setState({ shortcutFailures: s.failed || [] }));
  events.subscribe(handleEvent);
  events.onStatus = (c) => setState({ wsConnected: c });
  window.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && getState().speaking) stopSpeaking();
  });
  if (cfg.ready) await onBackendReady();
  else void pollHealth();
}

async function pollHealth() {
  for (let i = 0; i < 150 && !getState().backendReady; i++) {
    try {
      const r = await fetch(`http://127.0.0.1:${(await bridge.getConfig()).port}/health`);
      if (r.ok) return onBackendReady();
    } catch {
      /* not yet */
    }
    await new Promise((r) => setTimeout(r, 400));
  }
}

async function onBackendReady() {
  if (getState().settings && getState().backendReady && getState().wsConnected) return;
  setState({ backendReady: true, backendError: "" });
  events.close();
  events.connect();
  try {
    const [settings, conversations] = await Promise.all([api("/api/settings"), api("/api/conversations")]);
    setState({ settings, conversations });
    applyTheme(settings);
    await refreshStatus();
    void refreshModels(false);
    window.clearInterval(statusTimer);
    statusTimer = window.setInterval(() => void refreshStatus(), 10000);
    syncWakeListener();
  } catch (e) {
    setState({ backendError: (e as Error).message });
  }
}

export function applyTheme(settings: any) {
  const hex = settings?.ui?.accent_color || "#a855f7";
  const n = parseInt(hex.slice(1), 16);
  const rgb = `${(n >> 16) & 255} ${(n >> 8) & 255} ${n & 255}`;
  const root = document.documentElement;
  root.style.setProperty("--accent", rgb);
  const lighter = [(n >> 16) & 255, (n >> 8) & 255, n & 255].map((c) => Math.min(255, Math.round(c + (255 - c) * 0.45)));
  root.style.setProperty("--accent-2", lighter.join(" "));
  const he = settings?.ui?.language === "he";
  root.setAttribute("dir", he ? "rtl" : "ltr");
  root.setAttribute("lang", he ? "he" : "en");
  root.classList.toggle("reduce-motion", !!settings?.ui?.reduce_motion);
}

export async function refreshStatus() {
  try {
    const status = await api("/api/status");
    setState({ status, confirmations: mergeConfirmations(status.pending_confirmations || []), micEnabled: status.voice?.mic_enabled ?? true });
  } catch {
    /* transient */
  }
}

function mergeConfirmations(pending: any[]) {
  const existing = getState().confirmations;
  const ids = new Set(existing.map((c) => c.id));
  const add = pending.filter((p) => !ids.has(p.id)).map((p) => ({ ...p, timeout: 120, receivedAt: Date.now() }));
  return [...existing.filter((c) => pending.some((p) => p.id === c.id)), ...add];
}

export async function refreshModels(refresh = true) {
  try {
    setState({ models: await api(`/api/ai/models${refresh ? "?refresh=1" : ""}`) });
  } catch (e) {
    toast((e as Error).message, "error");
  }
}

export async function saveSettings(patch: any, quiet = false) {
  try {
    const settings = await api("/api/settings", { method: "PATCH", body: patch });
    setState({ settings });
    applyTheme(settings);
    await bridge.applySettings();
    syncWakeListener();
    if (!quiet) toast(t("set.saved"), "success", 1800);
    return settings;
  } catch (e) {
    toast((e as Error).message, "error");
    throw e;
  }
}

// ------------------------------------------------------------------ events
function updateMessage(runId: string, fn: (m: ChatMessage) => ChatMessage) {
  setState((s) => ({ messages: s.messages.map((m) => (m.runId === runId && m.role === "assistant" ? fn(m) : m)) }));
}

function handleEvent(ev: BackendEvent) {
  const s = getState();
  switch (ev.type) {
    case "orb.state":
      if (!(s.speaking && ev.state === "idle") && !(s.listening && ev.state === "idle")) setState({ orb: ev.state });
      break;
    case "run.started":
      if (ev.conversation_id === s.conversationId || !s.conversationId) {
        setState({ activeRun: { id: ev.run_id, mode: ev.mode, paused: false, state: "thinking", cloud: ev.cloud },
                   conversationId: ev.conversation_id });
        if (!s.messages.some((m) => m.runId === ev.run_id && m.role === "assistant")) {
          setState((st) => ({ messages: [...st.messages, { id: `a-${ev.run_id}`, role: "assistant", content: "", streaming: true, actions: [], runId: ev.run_id, ts: Date.now(), mode: ev.mode }] }));
        }
      }
      break;
    case "run.status":
      if (s.activeRun && s.activeRun.id === ev.run_id) setState({ activeRun: { ...s.activeRun, state: ev.state, paused: ev.state === "paused" } });
      break;
    case "chat.delta":
      updateMessage(ev.run_id, (m) => ({ ...m, content: m.content + ev.text }));
      break;
    case "chat.tool":
      updateMessage(ev.run_id, (m) => ({ ...m, actions: [...m.actions, { ...ev.call, pending: true }] }));
      break;
    case "chat.tool_result":
      updateMessage(ev.run_id, (m) => {
        const exists = m.actions.some((a) => a.id === ev.result.id);
        const actions = exists ? m.actions.map((a) => (a.id === ev.result.id ? { ...a, ...ev.result, pending: false } : a))
                               : [...m.actions, { ...ev.result, pending: false }];
        return { ...m, actions };
      });
      break;
    case "agent.plan":
      updateMessage(ev.run_id, (m) => ({ ...m, plan: ev.plan }));
      break;
    case "chat.done": {
      updateMessage(ev.run_id, (m) => ({ ...m, content: ev.text, streaming: false, warning: ev.warning,
        actions: ev.actions.map((a: any) => ({ ...(m.actions.find((x) => x.id === a.id) || {}), ...a, pending: false })) }));
      if (s.activeRun?.id === ev.run_id) setState({ activeRun: null });
      void api("/api/conversations").then((conversations) => setState({ conversations })).catch(() => {});
      const v = getState().settings?.voice;
      const spoken = getState().lastInputWasVoice;
      if (v?.enabled && v.tts_engine !== "off" && (v.speak_responses && spoken) && ev.status !== "cancelled") {
        void speak(ev.text, () => {
          if (v.continuous_conversation && getState().lastInputWasVoice) void pushToTalk();
        });
      }
      break;
    }
    case "run.error":
      toast(ev.error, "error", 7000);
      break;
    case "confirmation.request":
      setState((st) => ({ confirmations: [...st.confirmations.filter((c) => c.id !== ev.id),
        { id: ev.id, action: ev.action, summary: ev.summary, risk: ev.risk, source: ev.source, details: ev.details,
          timeout: ev.timeout, receivedAt: Date.now() }] }));
      bridge.getConfig().then(() => window.focus());
      break;
    case "confirmation.closed":
      setState((st) => ({ confirmations: st.confirmations.filter((c) => c.id !== ev.id) }));
      break;
    case "screen.capture":
      setState({ screenActive: !!ev.active });
      break;
    case "metrics":
      setState({ metrics: ev.metrics, warnings: ev.warnings || [] });
      break;
    case "ai.latency":
      setState({ latency: { total_ms: ev.total_ms, first_token_ms: ev.first_token_ms } });
      break;
    case "emergency.stop":
      onEmergencyStop(false);
      break;
    case "voice.mic":
      setState({ micEnabled: ev.enabled });
      break;
    case "voice.model_loading":
      toast(`Loading speech model “${ev.model}”… (first time may download it)`, "info", 6000);
      break;
    case "automation.finished":
      toast(`${ev.name}: ${ev.ok ? "✓" : "✗"}`, ev.ok ? "success" : "warning");
      break;
    case "memory.learned":
      toast(`🧠 ${ev.key}`, "info", 2500);
      break;
    case "remote.paired":
      toast(`📱 ${ev.device}`, "success");
      break;
    case "settings.changed":
      break;
  }
}

// --------------------------------------------------------------------- chat
export async function sendMessage(text: string, opts: { mode?: "chat" | "agent"; images?: string[]; voice?: boolean } = {}) {
  const s = getState();
  if (!text.trim() && !opts.images?.length) return;
  stopSpeaking();
  setState({ lastInputWasVoice: !!opts.voice });
  const userMsg: ChatMessage = { id: `u-${Date.now()}`, role: "user", content: text, actions: [], images: opts.images, ts: Date.now(), mode: opts.mode };
  setState({ messages: [...s.messages, userMsg], orb: "thinking" });
  try {
    const r = await api<{ run_id: string; conversation_id: string }>("/api/chat", {
      body: { text, conversation_id: s.conversationId, mode: opts.mode || "chat", images: opts.images || [], source: opts.voice ? "voice" : "chat" },
    });
    setState((st) => {
      const has = st.messages.some((m) => m.runId === r.run_id && m.role === "assistant");
      return {
        conversationId: r.conversation_id,
        activeRun: st.activeRun?.id === r.run_id ? st.activeRun : { id: r.run_id, mode: opts.mode || "chat", paused: false, state: "thinking" },
        messages: has ? st.messages : [...st.messages, { id: `a-${r.run_id}`, role: "assistant", content: "", streaming: true, actions: [], runId: r.run_id, ts: Date.now(), mode: opts.mode }],
      };
    });
  } catch (e) {
    setState({ orb: "error" });
    toast((e as ApiError).message, "error");
  }
}

export function newChat() {
  stopSpeaking();
  setState({ conversationId: null, messages: [], activeRun: null, page: "chat" });
}

export async function openConversation(id: string) {
  const c = await api(`/api/conversations/${id}`);
  const messages: ChatMessage[] = c.messages.map((m: any) => ({
    id: `db-${m.id}`, role: m.role, content: m.content, ts: m.created_at * 1000, actions: m.meta?.actions || [],
    warning: m.meta?.warning, plan: m.meta?.plan, mode: m.meta?.mode, meta: m.meta,
  }));
  setState({ conversationId: id, messages, page: "chat", activeRun: null });
}

export async function deleteConversation(id: string) {
  await api(`/api/conversations/${id}`, { method: "DELETE" });
  if (getState().conversationId === id) newChat();
  setState({ conversations: await api("/api/conversations") });
}

export async function decide(id: string, approved: boolean) {
  setState((s) => ({ confirmations: s.confirmations.filter((c) => c.id !== id) }));
  try {
    await api(`/api/confirmations/${id}`, { body: { approved } });
  } catch (e) {
    toast((e as Error).message, "error");
  }
}

export async function runOp(op: "pause" | "resume" | "cancel") {
  const run = getState().activeRun;
  if (!run) return;
  await api(`/api/runs/${run.id}/${op}`, { method: "POST" });
  if (op !== "cancel") setState({ activeRun: { ...run, paused: op === "pause" } });
}

function onEmergencyStop(notify = true) {
  stopSpeaking();
  stopListening();
  setState({ confirmations: [], activeRun: null, orb: "idle" });
  if (notify) toast(t("estop.done"), "warning");
}

export async function emergencyStop() {
  onEmergencyStop();
  await bridge.emergencyStop();
  try { await api("/api/emergency-stop", { method: "POST" }); } catch { /* main process already sent it */ }
}

export async function askAboutScreen(question: string, mode: "chat" | "agent" = "chat") {
  try {
    setState({ screenActive: true });
    const snap = await api<{ image_b64: string }>("/api/screen/snapshot", { method: "POST" });
    await sendMessage(question || "Explain what is on my screen.", { images: [snap.image_b64], mode });
  } catch (e) {
    toast((e as Error).message, "error", 6000);
  } finally {
    setState({ screenActive: false });
  }
}

// -------------------------------------------------------------------- voice
const mic = new Microphone();
let recording: Recording | null = null;
let wake: SegmentDetector | null = null;
let wakeBusy = false;

async function ensureMic() {
  const s = getState();
  if (!s.micEnabled) throw new Error(t("mic.off"));
  if (!mic.active) {
    await mic.open({ deviceId: s.settings?.voice?.microphone_id || undefined, onLevel: (l) => {
      if (getState().listening) setState({ micLevel: l });
    } });
  }
}

function stopListening() {
  recording?.stop();
  recording = null;
  setState({ listening: false, micLevel: 0 });
}

export async function pushToTalk() {
  const s = getState();
  if (!s.settings?.voice?.enabled) return toast("Voice is disabled in Settings.", "warning");
  if (s.listening) { recording?.stop(); return; }
  stopSpeaking();
  try {
    await ensureMic();
  } catch (e) {
    return toast(`${t("set.mic")}: ${(e as Error).message}`, "error");
  }
  setState({ listening: true, orb: "listening" });
  recording = new Recording(mic, { autoStop: true });
  const samples = await recording.done;
  recording = null;
  setState({ listening: false, micLevel: 0, transcribing: true, orb: "thinking" });
  try {
    const r = await api<{ text: string; silent?: boolean }>("/api/voice/transcribe", { raw: encodeWav(samples), headers: { "Content-Type": "audio/wav" } });
    if (r.text) await sendMessage(r.text, { voice: true });
    else setState({ orb: "idle" });
  } catch (e) {
    setState({ orb: "error" });
    toast((e as Error).message, "error", 6000);
  } finally {
    setState({ transcribing: false });
    if (!getState().settings?.voice?.wake_word_enabled && !wake) mic.close();
  }
}

export function syncWakeListener() {
  const s = getState();
  const want = !!(s.settings?.voice?.enabled && s.settings?.voice?.wake_word_enabled && s.micEnabled && s.backendReady);
  if (want && !wake) {
    ensureMic().then(() => {
      wake = new SegmentDetector(mic, async (samples) => {
        if (wakeBusy || getState().listening || getState().speaking || getState().activeRun) return;
        wakeBusy = true;
        try {
          const r = await api<{ detected: boolean; command?: string }>("/api/voice/wake", { raw: encodeWav(samples), headers: { "Content-Type": "audio/wav" } });
          if (r.detected) {
            if (r.command && r.command.split(" ").length >= 2) await sendMessage(r.command, { voice: true });
            else await pushToTalk();
          }
        } catch {
          /* ignore transient errors */
        } finally {
          wakeBusy = false;
        }
      });
      setState({ wakeListening: true });
    }).catch((e) => toast(`${t("set.wake")}: ${(e as Error).message}`, "error"));
  } else if (!want && wake) {
    wake.stop();
    wake = null;
    setState({ wakeListening: false });
    if (!getState().listening) mic.close();
  }
}

export async function setMicEnabled(enabled: boolean) {
  if (!enabled) {
    stopListening();
    wake?.stop();
    wake = null;
    mic.close();
    setState({ wakeListening: false });
  }
  setState({ micEnabled: enabled });
  try { await api("/api/voice/mic", { body: { enabled } }); } catch { /* ignore */ }
  syncWakeListener();
  toast(enabled ? t("mic.on") : t("mic.off"), enabled ? "info" : "warning", 2000);
}
