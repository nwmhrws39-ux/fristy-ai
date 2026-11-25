import { AnimatePresence, motion } from "framer-motion";
import { ArrowDown, ArrowUp, Clock, Copy, Mic, Play, Plus, Power, Trash2, Workflow, X, Zap } from "lucide-react";
import { useEffect, useState } from "react";
import { Card, Empty, Field, Select, Toggle } from "../components/ui";
import { api } from "../lib/api";
import { useT } from "../lib/i18n";
import { toast } from "../lib/store";

type Prop = { type?: string; enum?: string[]; description?: string; nullable?: boolean; minimum?: number; maximum?: number; items?: any };
const DAYS_EN = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

function blank(): any {
  return { name: "", description: "", enabled: true, confirmation: "once",
           trigger: { type: "phrase", phrases: [], time: "08:00", days: [0, 1, 2, 3, 4, 5, 6] }, conditions: [], steps: [] };
}

export function ArgField({ name, prop, value, onChange, required }: { name: string; prop: Prop; value: any; onChange: (v: any) => void; required?: boolean }) {
  const label = `${name}${required ? " *" : ""}`;
  if (prop.enum) return <Field label={label} hint={prop.description}><Select value={value ?? ""} onChange={onChange} options={[{ value: "", label: "—" }, ...prop.enum.map((e) => ({ value: e, label: e }))]} /></Field>;
  if (prop.type === "boolean") return <Toggle checked={!!value} onChange={onChange} label={name} description={prop.description} />;
  if (prop.type === "integer" || prop.type === "number") {
    return <Field label={label} hint={prop.description}><input type="number" className="input" value={value ?? ""} min={prop.minimum} max={prop.maximum}
      onChange={(e) => onChange(e.target.value === "" ? undefined : prop.type === "integer" ? parseInt(e.target.value, 10) : parseFloat(e.target.value))} /></Field>;
  }
  if (prop.type === "array") {
    return <Field label={label} hint={(prop.description || "") + " (comma separated)"}><input className="input" value={(value || []).join(", ")}
      onChange={(e) => onChange(e.target.value.split(",").map((s) => s.trim()).filter(Boolean))} /></Field>;
  }
  if (prop.type === "object") {
    return <Field label={label} hint="JSON"><textarea className="input font-mono text-xs" rows={3} defaultValue={JSON.stringify(value ?? {}, null, 1)}
      onBlur={(e) => { try { onChange(JSON.parse(e.target.value || "{}")); } catch { toast(`${name}: invalid JSON`, "error"); } }} /></Field>;
  }
  return <Field label={label} hint={prop.description}><input className="input" dir="auto" value={value ?? ""} onChange={(e) => onChange(e.target.value)} /></Field>;
}

function Editor({ initial, catalog, onClose, onSaved }: { initial: any; catalog: any[]; onClose: () => void; onSaved: () => void }) {
  const t = useT();
  const [a, setA] = useState<any>(() => JSON.parse(JSON.stringify(initial)));
  const [saving, setSaving] = useState(false);
  const set = (patch: any) => setA((x: any) => ({ ...x, ...patch }));
  const setTrigger = (patch: any) => setA((x: any) => ({ ...x, trigger: { ...x.trigger, ...patch } }));
  const setStep = (i: number, patch: any) => setA((x: any) => ({ ...x, steps: x.steps.map((s: any, j: number) => (j === i ? { ...s, ...patch } : s)) }));
  const move = (i: number, d: number) => setA((x: any) => {
    const steps = [...x.steps]; const j = i + d;
    if (j < 0 || j >= steps.length) return x;
    [steps[i], steps[j]] = [steps[j], steps[i]];
    return { ...x, steps };
  });
  const actionOpts = catalog.filter((c) => c.name !== "run_custom_command").map((c) => ({ value: c.name, label: `${c.name}${c.available ? "" : " (Windows only)"}` }));

  const save = async () => {
    setSaving(true);
    try {
      const body = { ...a };
      delete body.id; delete body.last_run_at; delete body.updated_at;
      body.steps = body.steps.map((s: any) => ({ ...s, args: Object.fromEntries(Object.entries(s.args || {}).filter(([, v]) => v !== undefined && v !== "")) }));
      if (a.id) await api(`/api/automations/${a.id}`, { method: "PUT", body });
      else await api("/api/automations", { body });
      toast(t("set.saved"), "success", 1500);
      onSaved();
    } catch (e) {
      toast((e as Error).message, "error", 7000);
    } finally {
      setSaving(false);
    }
  };

  return (
    <motion.div className="fixed inset-0 z-40 flex justify-end bg-black/60 backdrop-blur-sm" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
      <motion.div className="glass-strong m-3 flex w-full max-w-2xl flex-col overflow-hidden" initial={{ x: 60 }} animate={{ x: 0 }} exit={{ x: 60 }}>
        <header className="flex items-center justify-between border-b border-white/5 px-5 py-3">
          <h2 className="font-semibold text-white">{a.id ? a.name : t("auto.new")}</h2>
          <button className="btn-ghost h-8 w-8 p-0" onClick={onClose}><X size={16} /></button>
        </header>
        <div className="flex-1 space-y-4 overflow-y-auto p-5">
          <div className="grid grid-cols-2 gap-3">
            <Field label={t("auto.name")}><input className="input" dir="auto" value={a.name} onChange={(e) => set({ name: e.target.value })} /></Field>
            <Field label={t("auto.description")}><input className="input" dir="auto" value={a.description} onChange={(e) => set({ description: e.target.value })} /></Field>
          </div>
          <Card title={t("auto.trigger")} icon={<Zap size={13} />}>
            <div className="mb-3 flex flex-wrap gap-1.5">
              {(["phrase", "schedule", "manual", "startup"] as const).map((k) => (
                <button key={k} onClick={() => setTrigger({ type: k })} className={`chip px-3 py-1 text-xs ${a.trigger.type === k ? "border-accent/60 bg-accent/20 text-white" : ""}`}>
                  {k === "phrase" ? <Mic size={11} /> : k === "schedule" ? <Clock size={11} /> : k === "startup" ? <Power size={11} /> : <Play size={11} />}{t(`auto.trigger.${k}`)}
                </button>
              ))}
            </div>
            {a.trigger.type === "phrase" && (
              <Field label={t("auto.phrases")}><textarea className="input" rows={3} dir="auto" value={(a.trigger.phrases || []).join("\n")}
                onChange={(e) => setTrigger({ phrases: e.target.value.split("\n") })} onBlur={() => setTrigger({ phrases: a.trigger.phrases.map((p: string) => p.trim()).filter(Boolean) })} /></Field>
            )}
            {a.trigger.type === "schedule" && (
              <div className="flex flex-wrap items-end gap-4">
                <Field label={t("auto.time")}><input type="time" className="input w-32" value={a.trigger.time || "08:00"} onChange={(e) => setTrigger({ time: e.target.value })} /></Field>
                <Field label={t("auto.days")}>
                  <div className="flex gap-1">{DAYS_EN.map((d, i) => (
                    <button key={d} onClick={() => setTrigger({ days: a.trigger.days.includes(i) ? a.trigger.days.filter((x: number) => x !== i) : [...a.trigger.days, i].sort() })}
                            className={`h-8 w-10 rounded-lg border text-xs ${a.trigger.days.includes(i) ? "border-accent/60 bg-accent/25 text-white" : "border-white/10 text-zinc-500"}`}>{d}</button>
                  ))}</div>
                </Field>
              </div>
            )}
          </Card>
          <Card title={t("auto.conditions")} actions={<button className="btn-ghost h-7 px-2 text-xs" onClick={() => set({ conditions: [...a.conditions, { type: "time_between", start: "18:00", end: "23:59" }] })}><Plus size={12} />{t("auto.add_condition")}</button>}>
            {a.conditions.length === 0 && <div className="text-xs text-zinc-500">—</div>}
            {a.conditions.map((c: any, i: number) => (
              <div key={i} className="mb-2 flex flex-wrap items-center gap-2">
                <Select className="w-48" value={c.type} onChange={(v) => set({ conditions: a.conditions.map((x: any, j: number) => (j === i ? { type: v } : x)) })}
                  options={[{ value: "time_between", label: "Time between" }, { value: "weekday", label: "Weekday" }, { value: "process_running", label: "App is running" }, { value: "process_not_running", label: "App is not running" }]} />
                {c.type === "time_between" && <>
                  <input type="time" className="input w-28" value={c.start || ""} onChange={(e) => set({ conditions: a.conditions.map((x: any, j: number) => (j === i ? { ...x, start: e.target.value } : x)) })} />
                  <input type="time" className="input w-28" value={c.end || ""} onChange={(e) => set({ conditions: a.conditions.map((x: any, j: number) => (j === i ? { ...x, end: e.target.value } : x)) })} />
                </>}
                {c.type === "weekday" && <input className="input w-40" placeholder="0,1,2 (Mon=0)" value={(c.days || []).join(",")} onChange={(e) => set({ conditions: a.conditions.map((x: any, j: number) => (j === i ? { ...x, days: e.target.value.split(",").map((d) => parseInt(d, 10)).filter((d) => d >= 0 && d <= 6) } : x)) })} />}
                {(c.type === "process_running" || c.type === "process_not_running") && <input className="input w-44" placeholder="steam.exe" value={c.process || ""} onChange={(e) => set({ conditions: a.conditions.map((x: any, j: number) => (j === i ? { ...x, process: e.target.value } : x)) })} />}
                <button className="btn-ghost h-8 w-8 p-0 text-zinc-500 hover:text-red-300" onClick={() => set({ conditions: a.conditions.filter((_: any, j: number) => j !== i) })}><Trash2 size={13} /></button>
              </div>
            ))}
          </Card>
          <Card title={t("auto.steps")} icon={<Workflow size={13} />} actions={<button className="btn-ghost h-7 px-2 text-xs" onClick={() => set({ steps: [...a.steps, { action: "launch_app", args: {}, delay_seconds: 0, continue_on_error: false }] })}><Plus size={12} />{t("auto.add_step")}</button>}>
            <div className="space-y-3">
              {a.steps.map((s: any, i: number) => {
                const spec = catalog.find((c) => c.name === s.action);
                const props: Record<string, Prop> = spec?.schema?.properties || {};
                const req: string[] = spec?.schema?.required || [];
                return (
                  <div key={i} className="rounded-xl border border-white/10 bg-black/30 p-3">
                    <div className="mb-2 flex items-center gap-2">
                      <span className="grid h-6 w-6 place-items-center rounded-full bg-accent/20 text-xs text-accent2">{i + 1}</span>
                      <Select className="flex-1" value={s.action} onChange={(v) => setStep(i, { action: v, args: {} })} options={actionOpts} />
                      {spec && <span className={`chip ${spec.risk === "high" ? "text-red-300" : spec.risk === "medium" ? "text-amber-300" : "text-emerald-300"}`}>{spec.risk}</span>}
                      <button className="btn-ghost h-8 w-8 p-0" onClick={() => move(i, -1)}><ArrowUp size={13} /></button>
                      <button className="btn-ghost h-8 w-8 p-0" onClick={() => move(i, 1)}><ArrowDown size={13} /></button>
                      <button className="btn-ghost h-8 w-8 p-0 text-zinc-500 hover:text-red-300" onClick={() => set({ steps: a.steps.filter((_: any, j: number) => j !== i) })}><Trash2 size={13} /></button>
                    </div>
                    {s.description && <p className="mb-2 text-xs text-amber-200/80">{s.description}</p>}
                    {spec && !spec.permission_enabled && <p className="mb-2 text-xs text-red-300">Permission “{spec.permission}” is disabled — this step will fail until you enable it.</p>}
                    <div className="grid grid-cols-2 gap-x-3">
                      {Object.entries(props).map(([k, p]) => (
                        <ArgField key={k} name={k} prop={p} required={req.includes(k)} value={s.args?.[k]} onChange={(v) => setStep(i, { args: { ...s.args, [k]: v } })} />
                      ))}
                    </div>
                    <div className="flex items-center gap-4">
                      <label className="flex items-center gap-2 text-xs text-zinc-400">{t("auto.delay")}<input type="number" min={0} max={600} className="input w-20 py-1" value={s.delay_seconds || 0} onChange={(e) => setStep(i, { delay_seconds: Number(e.target.value) })} /></label>
                      <label className="flex items-center gap-2 text-xs text-zinc-400"><input type="checkbox" className="accent-[rgb(var(--accent))]" checked={!!s.continue_on_error} onChange={(e) => setStep(i, { continue_on_error: e.target.checked })} />{t("auto.continue")}</label>
                    </div>
                  </div>
                );
              })}
              {a.steps.length === 0 && <Empty>—</Empty>}
            </div>
          </Card>
          <Card title={t("auto.confirm")}>
            <Select value={a.confirmation} onChange={(v) => set({ confirmation: v })} options={[{ value: "once", label: t("auto.confirm.once") }, { value: "none", label: t("auto.confirm.none") }]} />
            <Toggle checked={a.enabled} onChange={(v) => set({ enabled: v })} label={t("auto.enabled")} />
          </Card>
        </div>
        <footer className="flex justify-end gap-2 border-t border-white/5 px-5 py-3">
          <button className="btn-outline" onClick={onClose}>{t("auto.cancel")}</button>
          <button className="btn-primary" disabled={saving || !a.name.trim() || !a.steps.length} onClick={() => void save()}>{t("auto.save")}</button>
        </footer>
      </motion.div>
    </motion.div>
  );
}

export default function AutomationsPage() {
  const t = useT();
  const [list, setList] = useState<any[]>([]);
  const [templates, setTemplates] = useState<any[]>([]);
  const [catalog, setCatalog] = useState<any[]>([]);
  const [editing, setEditing] = useState<any | null>(null);
  const load = async () => {
    const [l, tp, c] = await Promise.all([api("/api/automations"), api("/api/automation-templates"), api("/api/actions")]);
    setList(l); setTemplates(tp); setCatalog(c);
  };
  useEffect(() => { void load().catch((e) => toast(e.message, "error")); }, []);

  const run = async (id: string) => {
    try {
      const r = await api(`/api/automations/${id}/run`, { method: "POST" });
      toast(r.message.split("\n")[0], r.ok ? "success" : "warning", 6000);
      void load();
    } catch (e) { toast((e as Error).message, "error"); }
  };
  const toggle = async (a: any) => {
    const body = { ...a, enabled: !a.enabled };
    delete body.id; delete body.last_run_at; delete body.updated_at;
    await api(`/api/automations/${a.id}`, { method: "PUT", body }).catch((e) => toast(e.message, "error"));
    void load();
  };
  const remove = async (id: string) => { await api(`/api/automations/${id}`, { method: "DELETE" }); void load(); };

  return (
    <div className="h-full overflow-y-auto p-6">
      <div className="mx-auto max-w-5xl">
        <div className="mb-5 flex items-center justify-between">
          <div>
            <h1 className="text-xl font-semibold text-white">{t("auto.title")}</h1>
            <p className="text-sm text-zinc-500">“Gaming Mode”, “Development Mode”, “Good Night”…</p>
          </div>
          <button className="btn-primary" onClick={() => setEditing(blank())}><Plus size={15} />{t("auto.new")}</button>
        </div>
        <div className="grid gap-3 md:grid-cols-2">
          {list.map((a) => (
            <motion.div layout key={a.id} className={`glass p-4 ${a.enabled ? "" : "opacity-60"}`}>
              <div className="flex items-start justify-between gap-3">
                <button className="min-w-0 text-start" onClick={() => setEditing(a)}>
                  <div className="truncate font-medium text-white" dir="auto">{a.name}</div>
                  <div className="mt-0.5 truncate text-xs text-zinc-500" dir="auto">{a.description || `${a.steps.length} steps`}</div>
                </button>
                <Toggle checked={a.enabled} onChange={() => void toggle(a)} />
              </div>
              <div className="mt-3 flex flex-wrap gap-1.5 text-[11px]">
                <span className="chip">{a.trigger.type === "phrase" ? `🎙 ${(a.trigger.phrases || []).slice(0, 2).join(" / ")}` : a.trigger.type === "schedule" ? `⏰ ${a.trigger.time}` : a.trigger.type}</span>
                {a.steps.slice(0, 4).map((s: any, i: number) => <span key={i} className="chip font-mono">{s.action}</span>)}
              </div>
              <div className="mt-3 flex items-center justify-between">
                <span className="text-[11px] text-zinc-600">{a.last_run_at ? `${t("auto.last_run")}: ${new Date(a.last_run_at * 1000).toLocaleString()}` : ""}</span>
                <div className="flex gap-1">
                  <button className="btn-ghost h-8 px-2 text-xs" onClick={() => void run(a.id)} disabled={!a.enabled}><Play size={13} />{t("auto.run")}</button>
                  <button className="btn-ghost h-8 w-8 p-0 text-zinc-500 hover:text-red-300" onClick={() => void remove(a.id)}><Trash2 size={13} /></button>
                </div>
              </div>
            </motion.div>
          ))}
        </div>
        {list.length === 0 && <div className="glass"><Empty>{t("auto.empty")}</Empty></div>}
        <h2 className="section-title mb-3 mt-8">{t("auto.templates")}</h2>
        <div className="grid gap-3 md:grid-cols-3">
          {templates.map((tp) => (
            <button key={tp.name} className="glass p-4 text-start transition hover:border-accent/40" onClick={() => setEditing({ ...blank(), ...tp, trigger: { ...blank().trigger, ...tp.trigger } })}>
              <div className="flex items-center gap-2 font-medium text-white"><Copy size={14} className="text-accent2" />{tp.name}</div>
              <div className="mt-1 text-xs text-zinc-500">{tp.description}</div>
            </button>
          ))}
        </div>
      </div>
      <AnimatePresence>
        {editing && <Editor initial={editing} catalog={catalog} onClose={() => setEditing(null)} onSaved={() => { setEditing(null); void load(); }} />}
      </AnimatePresence>
    </div>
  );
}
