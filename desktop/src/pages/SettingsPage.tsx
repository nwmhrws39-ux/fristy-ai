import { motion } from "framer-motion";
import { Bot, Cloud, Cpu, FolderPlus, KeyRound, Keyboard, Lock, Mic, Palette, Plug, RefreshCw, Shield, Smartphone, Trash2, Volume2, X, Folder } from "lucide-react";
import { ReactNode, useEffect, useState } from "react";
import LocalModels from "../components/LocalModels";
import { Card, Field, Select, Spinner, Toggle } from "../components/ui";
import { api } from "../lib/api";
import { bridge } from "../lib/bridge";
import { refreshModels, refreshStatus, saveSettings } from "../lib/controller";
import { useT } from "../lib/i18n";
import { setState, toast, useStore } from "../lib/store";
import { speak, voices } from "../lib/tts";

type Tab = "ai" | "voice" | "permissions" | "files" | "integrations" | "appearance" | "system" | "privacy";
const TABS: { id: Tab; icon: typeof Bot }[] = [
  { id: "ai", icon: Bot }, { id: "voice", icon: Mic }, { id: "permissions", icon: Shield }, { id: "files", icon: Folder },
  { id: "integrations", icon: Plug }, { id: "appearance", icon: Palette }, { id: "system", icon: Keyboard }, { id: "privacy", icon: Lock },
];
const SECRET_FOR: Record<string, string> = { openai: "openai_api_key", anthropic: "anthropic_api_key", gemini: "gemini_api_key", custom: "custom_api_key" };

function SecretInput({ name, label }: { name: string; label: string }) {
  const t = useT();
  const [value, setValue] = useState("");
  const [info, setInfo] = useState<any>(null);
  const load = () => api("/api/secrets").then(setInfo).catch(() => {});
  useEffect(() => { void load(); }, [name]);
  const isSet = info?.secrets?.[name];
  const save = async () => {
    try { await api(`/api/secrets/${name}`, { method: "PUT", body: { value } }); setValue(""); toast(t("set.saved"), "success", 1500); void load(); void refreshModels(); }
    catch (e) { toast((e as Error).message, "error"); }
  };
  return (
    <Field label={<span className="flex items-center gap-1.5"><KeyRound size={12} />{label}</span>}
           hint={isSet ? (info.persistent ? t("set.key_set") : t("set.key_memory")) : undefined}>
      <div className="flex gap-2">
        <input type="password" autoComplete="off" className="input font-mono" placeholder={isSet ? "••••••••••••••••" : "…"} value={value} onChange={(e) => setValue(e.target.value)} />
        <button className="btn-primary" disabled={!value} onClick={() => void save()}>{t("set.save")}</button>
        {isSet && <button className="btn-ghost text-red-300" title={t("set.remove_key")} onClick={() => api(`/api/secrets/${name}`, { method: "DELETE" }).then(load)}><Trash2 size={14} /></button>}
      </div>
    </Field>
  );
}

function AITab({ s }: { s: any }) {
  const t = useT();
  const models = useStore((st) => st.models);
  const [testing, setTesting] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const provider = s.ai.provider;
  const prov = models?.providers?.find((p: any) => p.id === provider);
  const cloud = prov?.cloud;
  const modelOpts = (prov?.models || []).map((m: any) => ({ value: m.id, label: `${m.name || m.id}${m.supports_tools ? " · tools" : ""}${m.supports_vision ? " · vision" : ""}${m.size_gb ? ` · ${m.size_gb} GB` : ""}` }));
  const test = async () => {
    setTesting(true);
    try {
      const r = await api("/api/ai/test", { method: "POST" });
      toast(r.ok ? `✓ ${r.reply} (${r.latency_ms} ms)` : r.error, r.ok ? "success" : "error", 7000);
    } finally { setTesting(false); }
  };
  return (
    <div className="space-y-4">
      <Card title={t("set.provider")} icon={<Bot size={13} />}>
        <div className="grid grid-cols-2 gap-2 md:grid-cols-5">
          {(models?.providers || [{ id: "ollama", label: "Ollama" }]).map((p: any) => (
            <button key={p.id} onClick={() => void saveSettings({ ai: { provider: p.id, model: "" } }, true).then(() => refreshModels())}
              className={`rounded-xl border px-3 py-2.5 text-start text-sm transition ${p.id === provider ? "border-accent/60 bg-accent/15 text-white shadow-glow" : "border-white/10 text-zinc-400 hover:border-white/20"}`}>
              <div className="flex items-center gap-1.5 font-medium">{p.cloud ? <Cloud size={13} /> : <Cpu size={13} />}{p.label}</div>
              <div className={`mt-0.5 truncate text-[11px] ${p.error ? "text-red-300/80" : "text-zinc-500"}`}>{p.error ? t("set.unavailable") : t("set.n_models", { n: p.models?.length || 0 })}</div>
            </button>
          ))}
        </div>
        {cloud && <p className="mt-3 flex items-center gap-2 rounded-lg border border-sky-400/30 bg-sky-400/10 p-2 text-xs text-sky-200"><Cloud size={13} />{t("set.cloud_note")}</p>}
        {prov?.error && <p className="mt-3 rounded-lg border border-red-500/30 bg-red-500/10 p-2 text-xs text-red-200 selectable">{prov.error}</p>}
      </Card>
      {provider === "ollama" && <Card title={t("models.title")} icon={<Cpu size={13} />}><LocalModels /></Card>}
      <Card title={t("set.model")} actions={<button className="btn-ghost h-7 px-2 text-xs" onClick={async () => { setRefreshing(true); await refreshModels(); setRefreshing(false); }}>{refreshing ? <Spinner className="h-3 w-3" /> : <RefreshCw size={12} />}{t("set.refresh")}</button>}>
        <div className="grid gap-3 md:grid-cols-2">
          <Field label={t("set.model")} hint={provider === "ollama" && !modelOpts.length ? "No local models. Install one: ollama pull llama3.1  (or qwen2.5, gemma3 for vision)" : undefined}>
            {modelOpts.length ? (
              <Select value={s.ai.model} onChange={(v) => void saveSettings({ ai: { model: v } })} options={[{ value: "", label: "Automatic" }, ...modelOpts]} />
            ) : (
              <input className="input font-mono" placeholder={s.ai.providers[provider]?.default_model} defaultValue={s.ai.model} onBlur={(e) => void saveSettings({ ai: { model: e.target.value.trim() } })} />
            )}
          </Field>
          <Field label={t("set.baseurl")}>
            <input className="input font-mono text-xs" defaultValue={s.ai.providers[provider]?.base_url} key={provider}
                   onBlur={(e) => e.target.value !== s.ai.providers[provider]?.base_url && void saveSettings({ ai: { providers: { [provider]: { base_url: e.target.value.trim(), enabled: true } } } })} />
          </Field>
        </div>
        {SECRET_FOR[provider] && <SecretInput name={SECRET_FOR[provider]} label={`${prov?.label || provider} ${t("set.apikey")}`} />}
        <div className="grid gap-3 md:grid-cols-2">
          <Field label={`${t("set.temperature")}: ${s.ai.temperature}`}><input type="range" min={0} max={1.5} step={0.1} className="w-full accent-[rgb(var(--accent))]" defaultValue={s.ai.temperature} onMouseUp={(e) => void saveSettings({ ai: { temperature: Number((e.target as HTMLInputElement).value) } }, true)} /></Field>
          <Field label={t("set.maxtokens")}><input type="number" className="input" defaultValue={s.ai.max_tokens} min={64} max={32000} onBlur={(e) => void saveSettings({ ai: { max_tokens: Number(e.target.value) } }, true)} /></Field>
        </div>
        <Toggle checked={s.ai.fast_local_commands} onChange={(v) => void saveSettings({ ai: { fast_local_commands: v } })} label={t("set.fast")} />
        <button className="btn-outline mt-2" disabled={testing} onClick={() => void test()}>{testing ? <Spinner /> : <Bot size={14} />}{t("set.test")}</button>
      </Card>
      <Card title={t("set.agent")}>
        <div className="grid gap-3 md:grid-cols-4">
          <Field label={t("set.max_steps")}><input type="number" className="input" min={1} max={25} defaultValue={s.agent.max_steps} onBlur={(e) => void saveSettings({ agent: { max_steps: Number(e.target.value) } })} /></Field>
          <Field label={t("set.max_duration")}><input type="number" className="input" min={10} max={1800} defaultValue={s.agent.max_duration_seconds} onBlur={(e) => void saveSettings({ agent: { max_duration_seconds: Number(e.target.value) } })} /></Field>
          <Field label={t("set.recovery")}><input type="number" className="input" min={0} max={5} defaultValue={s.agent.max_recovery_attempts} onBlur={(e) => void saveSettings({ agent: { max_recovery_attempts: Number(e.target.value) } })} /></Field>
          <Field label={t("set.chat_tools")}><input type="number" className="input" min={0} max={10} defaultValue={s.agent.chat_max_tool_calls} onBlur={(e) => void saveSettings({ agent: { chat_max_tool_calls: Number(e.target.value) } })} /></Field>
        </div>
        <Toggle checked={s.agent.require_plan_approval} onChange={(v) => void saveSettings({ agent: { require_plan_approval: v } })} label={t("set.plan_approval")} />
      </Card>
    </div>
  );
}

function VoiceTab({ s }: { s: any }) {
  const t = useT();
  const [mics, setMics] = useState<MediaDeviceInfo[]>([]);
  const [vs, setVs] = useState<SpeechSynthesisVoice[]>(voices());
  const status = useStore((st) => st.status);
  useEffect(() => {
    navigator.mediaDevices?.enumerateDevices().then((d) => setMics(d.filter((x) => x.kind === "audioinput"))).catch(() => {});
    const h = () => setVs(voices());
    speechSynthesis?.addEventListener?.("voiceschanged", h);
    return () => speechSynthesis?.removeEventListener?.("voiceschanged", h);
  }, []);
  const v = s.voice;
  const set = (patch: any) => void saveSettings({ voice: patch }, true);
  return (
    <div className="space-y-4">
      <Card title={t("set.stt")} icon={<Mic size={13} />}>
        <Toggle checked={v.enabled} onChange={(x) => set({ enabled: x })} label={t("set.voice.enabled")} />
        <Toggle checked={v.wake_word_enabled} onChange={(x) => set({ wake_word_enabled: x })} label={t("set.wake")}
                description={status?.voice?.local_stt_available ? "Runs Whisper “tiny” locally on short speech segments. Never sent to the cloud." : "Requires local speech recognition (faster-whisper), which is not installed."}
                disabled={!status?.voice?.local_stt_available} />
        <div className="grid gap-3 md:grid-cols-3">
          <Field label={t("set.stt")}><Select value={v.stt_engine} onChange={(x) => set({ stt_engine: x })} options={[{ value: "local", label: t("set.stt.local") }, { value: "openai", label: t("set.stt.openai") }]} /></Field>
          <Field label={t("set.whisper")} hint="small ≈ good Hebrew on CPU · medium/large need more RAM"><Select value={v.whisper_model} onChange={(x) => set({ whisper_model: x })} options={["tiny", "base", "small", "medium", "large-v3"].map((m) => ({ value: m, label: m }))} /></Field>
          <Field label={t("set.language")}><Select value={v.language} onChange={(x) => set({ language: x })} options={[{ value: "auto", label: t("set.lang.auto") }, { value: "he", label: "עברית" }, { value: "en", label: "English" }]} /></Field>
        </div>
        <Field label={t("set.mic")}><Select value={v.microphone_id} onChange={(x) => set({ microphone_id: x })} options={[{ value: "", label: t("set.mic.default") }, ...mics.map((m) => ({ value: m.deviceId, label: m.label || m.deviceId.slice(0, 12) }))]} /></Field>
        <Toggle checked={v.continuous_conversation} onChange={(x) => set({ continuous_conversation: x })} label={t("set.continuous")} description="After FRISTY answers a voice question, it listens again automatically." />
      </Card>
      <Card title={t("set.tts")} icon={<Volume2 size={13} />}>
        <div className="grid gap-3 md:grid-cols-3">
          <Field label={t("set.tts")}><Select value={v.tts_engine} onChange={(x) => set({ tts_engine: x })} options={[{ value: "system", label: t("set.tts.system") }, { value: "openai", label: t("set.tts.openai") }, { value: "off", label: t("set.tts.off") }]} /></Field>
          {v.tts_engine === "system" ? (
            <Field label={t("set.voice")} hint="Hebrew voices require the Hebrew speech pack in Windows Settings › Time & language › Speech."><Select value={v.voice_name} onChange={(x) => set({ voice_name: x })} options={[{ value: "", label: "Automatic (by language)" }, ...vs.map((x) => ({ value: x.name, label: `${x.name} (${x.lang})` }))]} /></Field>
          ) : v.tts_engine === "openai" ? (
            <Field label={t("set.voice")}><Select value={v.openai_voice} onChange={(x) => set({ openai_voice: x })} options={["alloy", "ash", "coral", "echo", "fable", "nova", "onyx", "sage", "shimmer"].map((x) => ({ value: x, label: x }))} /></Field>
          ) : <div />}
          <Field label={`${t("set.rate")}: ${v.rate}x`}><input type="range" min={0.5} max={2} step={0.1} defaultValue={v.rate} className="w-full accent-[rgb(var(--accent))]" onMouseUp={(e) => set({ rate: Number((e.target as HTMLInputElement).value) })} /></Field>
        </div>
        <Toggle checked={v.speak_responses} onChange={(x) => set({ speak_responses: x })} label={t("set.speak")} description="Only answers to voice questions are spoken. Press Esc to interrupt." />
        <button className="btn-outline mt-2" onClick={() => void speak(s.ui.language === "he" ? "שלום, אני פריסטי. איך אפשר לעזור?" : "Hello, I'm FRISTY. How can I help?")}><Volume2 size={14} />{t("set.test_voice")}</button>
      </Card>
    </div>
  );
}

function PermissionsTab({ s }: { s: any }) {
  const t = useT();
  const [apps, setApps] = useState((s.closable_apps || []).join(", "));
  return (
    <div className="space-y-4">
      <Card title={t("set.permissions")} icon={<Shield size={13} />}>
        <p className="mb-2 text-xs text-zinc-500">{t("set.perm.note")}</p>
        <div className="divide-y divide-white/[0.05]">
          {Object.keys(s.permissions).map((p) => (
            <Toggle key={p} checked={s.permissions[p]} onChange={(v) => void saveSettings({ permissions: { [p]: v } })} label={t(`set.perm.${p}` as any)} />
          ))}
        </div>
      </Card>
      <Card title={t("set.closable")}>
        <div className="flex gap-2">
          <input className="input font-mono text-xs" value={apps} onChange={(e) => setApps(e.target.value)} />
          <button className="btn-primary" onClick={() => void saveSettings({ closable_apps: apps.split(",").map((x: string) => x.trim().toLowerCase()).filter(Boolean).map((x: string) => (x.endsWith(".exe") ? x : x + ".exe")) })}>{t("set.save")}</button>
        </div>
      </Card>
    </div>
  );
}

function FilesTab({ s }: { s: any }) {
  const t = useT();
  const [manual, setManual] = useState("");
  const add = async (dir: string | null) => {
    if (!dir) return;
    await saveSettings({ approved_dirs: [...s.approved_dirs, dir] }).catch(() => {});
    setManual("");
  };
  return (
    <Card title={t("set.dirs")} icon={<Folder size={13} />}>
      <p className="mb-3 text-xs text-zinc-500">{t("set.dirs.note")}</p>
      <ul className="mb-3 space-y-1.5">
        {s.approved_dirs.map((d: string) => (
          <li key={d} className="flex items-center justify-between rounded-lg border border-white/10 bg-black/30 px-3 py-2 font-mono text-xs text-zinc-300" dir="ltr">
            {d}<button className="text-zinc-500 hover:text-red-300" onClick={() => void saveSettings({ approved_dirs: s.approved_dirs.filter((x: string) => x !== d) })}><X size={14} /></button>
          </li>
        ))}
      </ul>
      <div className="flex gap-2">
        <button className="btn-primary" onClick={() => void bridge.pickFolder().then(add)}><FolderPlus size={14} />{t("set.dirs.add")}</button>
        <input className="input font-mono text-xs" dir="ltr" placeholder="C:\Users\me\Downloads" value={manual} onChange={(e) => setManual(e.target.value)} />
        <button className="btn-outline" disabled={!manual} onClick={() => void add(manual.trim())}>+</button>
      </div>
      {!s.permissions.file_access && <p className="mt-3 text-xs text-amber-300">“{t("set.perm.file_access")}” is disabled in Permissions.</p>}
    </Card>
  );
}

function IntegrationsTab({ s }: { s: any }) {
  const t = useT();
  const status = useStore((st) => st.status);
  const [remote, setRemote] = useState<any>(null);
  const [code, setCode] = useState<any>(null);
  const loadRemote = () => api("/api/remote").then(setRemote).catch(() => {});
  useEffect(() => { void loadRemote(); }, [s.remote.enabled]);
  const check = async () => { await api("/api/integrations?check=true"); await refreshStatus(); };
  const names: Record<string, string> = { launcher: "FRISTY Launcher", pc_manager: "FRISTY PC Manager", cleaner: "FRISTY Cleaner" };
  return (
    <div className="space-y-4">
      {(["launcher", "pc_manager", "cleaner"] as const).map((k) => {
        const cfg = s.integrations[k];
        const st = status?.integrations?.find((x: any) => x.key === k);
        return (
          <Card key={k} title={names[k]} icon={<Plug size={13} />} actions={st?.enabled && <span className={`chip ${st.connected ? "text-emerald-300" : "text-red-300"}`}>{st.connected ? t("dash.connected") : t("dash.disconnected")}</span>}>
            <Toggle checked={cfg.enabled} onChange={(v) => void saveSettings({ integrations: { [k]: { enabled: v } } }).then(check)} label={t("set.integration.enabled")} />
            {cfg.enabled && <>
              <Field label={t("set.baseurl")} hint="Must be on this PC (127.0.0.1)."><input className="input font-mono text-xs" defaultValue={cfg.base_url} onBlur={(e) => void saveSettings({ integrations: { [k]: { base_url: e.target.value.trim() } } }, true)} /></Field>
              <SecretInput name={`integration_${k}_token`} label={t("set.integration.token")} />
              {st?.error && <p className="text-xs text-red-300">{st.error}</p>}
              <button className="btn-outline" onClick={() => void check()}>{t("set.check")}</button>
            </>}
          </Card>
        );
      })}
      <Card title={t("set.remote")} icon={<Smartphone size={13} />}>
        <Toggle checked={s.remote.enabled} onChange={(v) => void saveSettings({ remote: { enabled: v } }).then(loadRemote)} label={t("set.remote.enabled")} description={`Port ${s.remote.port} · ${remote?.running ? "running" : "stopped"}`} />
        <Toggle checked={s.remote.allow_lan} onChange={(v) => void saveSettings({ remote: { allow_lan: v } }).then(loadRemote)} label={t("set.remote.lan")} disabled={!s.remote.enabled} />
        {s.remote.allow_lan && <p className="text-xs text-amber-300">{t("set.remote.lan_warn")}</p>}
        {s.remote.enabled && (
          <div className="mt-2">
            <button className="btn-primary" onClick={() => api("/api/remote/pairing", { method: "POST" }).then(setCode).catch((e) => toast(e.message, "error"))}>{t("set.remote.pair")}</button>
            {code && <div className="mt-3 rounded-xl border border-accent/40 bg-accent/10 p-4 text-center">
              <div className="text-xs text-zinc-400">{t("set.remote.code")}</div>
              <div className="mt-1 font-mono text-3xl tracking-[0.4em] text-white">{code.code}</div>
            </div>}
            <div className="label mt-4">{t("set.remote.devices")}</div>
            {(remote?.devices || []).map((d: any) => (
              <div key={d.id} className="flex items-center justify-between border-b border-white/5 py-1.5 text-sm">
                <span>{d.name} <span className="text-xs text-zinc-600">{d.last_seen ? new Date(d.last_seen * 1000).toLocaleString() : ""}</span></span>
                <button className="btn-ghost h-7 px-2 text-xs text-red-300" onClick={() => api(`/api/remote/devices/${d.id}`, { method: "DELETE" }).then(loadRemote)}>{t("set.remote.revoke")}</button>
              </div>
            ))}
          </div>
        )}
      </Card>
    </div>
  );
}

function AppearanceTab({ s }: { s: any }) {
  const t = useT();
  const swatches = ["#a855f7", "#8b5cf6", "#d946ef", "#ec4899", "#6366f1", "#22d3ee", "#10b981", "#f59e0b"];
  return (
    <Card title={t("set.appearance")} icon={<Palette size={13} />}>
      <Field label={t("set.ui.language")}>
        <div className="flex gap-2">
          {[{ v: "en", l: "English" }, { v: "he", l: "עברית" }].map((o) => (
            <button key={o.v} onClick={() => void saveSettings({ ui: { language: o.v } }, true)} className={`btn-outline ${s.ui.language === o.v ? "border-accent/60 bg-accent/20 text-white" : ""}`}>{o.l}</button>
          ))}
        </div>
      </Field>
      <Field label={t("set.accent")}>
        <div className="flex flex-wrap items-center gap-2">
          {swatches.map((c) => (
            <button key={c} onClick={() => void saveSettings({ ui: { accent_color: c } }, true)} className={`h-9 w-9 rounded-full border-2 ${s.ui.accent_color === c ? "border-white" : "border-transparent"}`} style={{ background: c, boxShadow: `0 0 16px ${c}80` }} />
          ))}
          <input type="color" className="h-9 w-12 cursor-pointer rounded-lg border border-white/10 bg-transparent" defaultValue={s.ui.accent_color} onChange={(e) => void saveSettings({ ui: { accent_color: e.target.value } }, true)} />
        </div>
      </Field>
      <Toggle checked={s.ui.reduce_motion} onChange={(v) => void saveSettings({ ui: { reduce_motion: v } }, true)} label={t("set.reduce_motion")} />
    </Card>
  );
}

function ShortcutInput({ value, onSave }: { value: string; onSave: (v: string) => void }) {
  const [rec, setRec] = useState(false);
  return (
    <button className={`input text-start font-mono text-xs ${rec ? "border-accent ring-2 ring-accent/30" : ""}`} onClick={() => setRec(true)}
      onKeyDown={(e) => {
        if (!rec) return;
        e.preventDefault();
        if (["Control", "Shift", "Alt", "Meta"].includes(e.key)) return;
        const parts = [e.ctrlKey && "CommandOrControl", e.altKey && "Alt", e.shiftKey && "Shift", e.metaKey && "Super"].filter(Boolean) as string[];
        const key = e.key === " " ? "Space" : e.key.length === 1 ? e.key.toUpperCase() : e.key;
        if (!parts.length) return;
        setRec(false);
        onSave([...parts, key].join("+"));
      }} onBlur={() => setRec(false)}>
      {rec ? "Press keys…" : value}
    </button>
  );
}

function SystemTab({ s }: { s: any }) {
  const t = useT();
  const failures = useStore((st) => st.shortcutFailures);
  return (
    <div className="space-y-4">
      <Card title={t("set.startup")} icon={<Cpu size={13} />}>
        <Toggle checked={s.startup.start_with_windows} onChange={(v) => void saveSettings({ startup: { start_with_windows: v } })} label={t("set.startup")} description="Starts hidden in the tray." />
        <Toggle checked={s.startup.tray_mode} onChange={(v) => void saveSettings({ startup: { tray_mode: v } })} label={t("set.tray")} />
      </Card>
      <Card title={t("set.shortcuts")} icon={<Keyboard size={13} />}>
        <div className="grid gap-3 md:grid-cols-2">
          <Field label={t("set.sc.toggle")}><ShortcutInput value={s.shortcuts.toggle_window} onSave={(v) => void saveSettings({ shortcuts: { toggle_window: v } })} /></Field>
          <Field label={t("set.sc.estop")}><ShortcutInput value={s.shortcuts.emergency_stop} onSave={(v) => void saveSettings({ shortcuts: { emergency_stop: v } })} /></Field>
          <Field label={t("set.sc.compact")}><ShortcutInput value={s.shortcuts.compact_mode} onSave={(v) => void saveSettings({ shortcuts: { compact_mode: v } })} /></Field>
          <Field label={t("set.sc.ptt")}><ShortcutInput value={s.voice.push_to_talk_shortcut} onSave={(v) => void saveSettings({ voice: { push_to_talk_shortcut: v } })} /></Field>
        </div>
        {failures.length > 0 && <p className="text-xs text-red-300">Could not register (already used by another app): {failures.join(", ")}</p>}
      </Card>
    </div>
  );
}

function PrivacyTab({ s }: { s: any }) {
  const t = useT();
  return (
    <div className="space-y-4">
      <Card title={t("nav.memory")} icon={<Lock size={13} />}>
        <Toggle checked={s.memory.enabled} onChange={(v) => void saveSettings({ memory: { enabled: v } })} label={t("set.memory.enabled")} />
        <Toggle checked={s.memory.auto_learn} onChange={(v) => void saveSettings({ memory: { auto_learn: v } })} label={t("set.memory.auto")} disabled={!s.memory.enabled} />
        <Toggle checked={s.memory.summarize_conversations} onChange={(v) => void saveSettings({ memory: { summarize_conversations: v } })} label={t("set.memory.summaries")} disabled={!s.memory.enabled} />
        <button className="btn-outline mt-2" onClick={() => setState({ page: "memory" })}>{t("nav.memory")} →</button>
      </Card>
      <Card title={t("set.privacy")}>
        <p className="mb-3 text-sm text-zinc-400">{t("set.data_dir")} {t("set.cloud_note")}</p>
        <button className="btn-danger" onClick={async () => { if (window.confirm(t("set.clear_conversations") + "?")) { await api("/api/conversations", { method: "DELETE" }); setState({ conversations: [], messages: [], conversationId: null }); toast("✓", "success"); } }}><Trash2 size={14} />{t("set.clear_conversations")}</button>
      </Card>
    </div>
  );
}

export default function SettingsPage() {
  const t = useT();
  const s = useStore((st) => st.settings);
  const [tab, setTab] = useState<Tab>("ai");
  if (!s) return <div className="grid h-full place-items-center"><Spinner className="h-6 w-6" /></div>;
  const body: Record<Tab, ReactNode> = {
    ai: <AITab s={s} />, voice: <VoiceTab s={s} />, permissions: <PermissionsTab s={s} />, files: <FilesTab s={s} />,
    integrations: <IntegrationsTab s={s} />, appearance: <AppearanceTab s={s} />, system: <SystemTab s={s} />, privacy: <PrivacyTab s={s} />,
  };
  return (
    <div className="flex h-full min-h-0">
      <div className="w-52 shrink-0 space-y-0.5 border-e border-white/[0.05] p-3">
        <h1 className="mb-3 px-2 text-lg font-semibold text-white">{t("nav.settings")}</h1>
        {TABS.map(({ id, icon: Icon }) => (
          <button key={id} onClick={() => setTab(id)} className={`relative flex w-full items-center gap-2.5 rounded-lg px-3 py-2 text-sm ${tab === id ? "text-white" : "text-zinc-400 hover:text-zinc-200"}`}>
            {tab === id && <motion.span layoutId="settab" className="absolute inset-0 rounded-lg bg-accent/15" />}
            <Icon size={15} className="relative" /><span className="relative">{t(`set.${id}` as any)}</span>
          </button>
        ))}
      </div>
      <div className="flex-1 overflow-y-auto p-6"><div className="mx-auto max-w-3xl">{body[tab]}</div></div>
    </div>
  );
}
