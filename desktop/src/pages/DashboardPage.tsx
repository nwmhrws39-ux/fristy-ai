import { Activity, Bot, Cpu, Gauge, HardDrive, MemoryStick, Mic, MicOff, Plug, ScrollText, Thermometer, Timer, Workflow, MessageSquare, AlertTriangle } from "lucide-react";
import { useEffect } from "react";
import { Card, Empty, Meter } from "../components/ui";
import Orb from "../components/Orb";
import { openConversation, refreshStatus } from "../lib/controller";
import { useT } from "../lib/i18n";
import { setState, useStore } from "../lib/store";

function Stat({ icon, label, value, sub, meter }: { icon: React.ReactNode; label: string; value: React.ReactNode; sub?: React.ReactNode; meter?: number | null }) {
  return (
    <div className="glass p-4">
      <div className="flex items-center gap-2 text-xs text-zinc-400">{icon}{label}</div>
      <div className="mt-2 text-2xl font-semibold tabular-nums text-white">{value}</div>
      {sub && <div className="mt-0.5 truncate text-xs text-zinc-500">{sub}</div>}
      {meter !== undefined && <div className="mt-3"><Meter value={meter} /></div>}
    </div>
  );
}

function Sparkline({ values, max = 100 }: { values: number[]; max?: number }) {
  if (values.length < 2) return <div className="h-12" />;
  const w = 240, h = 48;
  const pts = values.map((v, i) => `${(i / (values.length - 1)) * w},${h - (Math.min(v, max) / max) * (h - 4) - 2}`).join(" ");
  return (
    <svg viewBox={`0 0 ${w} ${h}`} className="h-12 w-full" preserveAspectRatio="none">
      <defs><linearGradient id="spark" x1="0" x2="0" y1="0" y2="1"><stop offset="0" stopColor="rgb(var(--accent))" stopOpacity="0.45" /><stop offset="1" stopColor="rgb(var(--accent))" stopOpacity="0" /></linearGradient></defs>
      <polygon points={`0,${h} ${pts} ${w},${h}`} fill="url(#spark)" />
      <polyline points={pts} fill="none" stroke="rgb(var(--accent-2))" strokeWidth="1.5" />
    </svg>
  );
}

const history: { cpu: number[]; ram: number[] } = { cpu: [], ram: [] };

function fmtAgo(ts: number) {
  const s = Math.round(Date.now() / 1000 - ts);
  if (s < 60) return `${s}s`;
  if (s < 3600) return `${Math.round(s / 60)}m`;
  if (s < 86400) return `${Math.round(s / 3600)}h`;
  return `${Math.round(s / 86400)}d`;
}

export default function DashboardPage() {
  const t = useT();
  const status = useStore((s) => s.status);
  const live = useStore((s) => s.metrics);
  const warnings = useStore((s) => s.warnings);
  const latency = useStore((s) => s.latency);
  const micEnabled = useStore((s) => s.micEnabled);
  const wake = useStore((s) => s.wakeListening);
  const conversations = useStore((s) => s.conversations);
  const orb = useStore((s) => s.orb);

  useEffect(() => { void refreshStatus(); }, []);
  const m = live || status?.metrics;
  if (m && history.cpu[history.cpu.length - 1] !== m.cpu_percent) {
    history.cpu = [...history.cpu, m.cpu_percent].slice(-60);
    history.ram = [...history.ram, m.ram_percent].slice(-60);
  }
  const temps = Object.entries(m?.temperatures || {}) as [string, number][];
  const maxTemp = temps.length ? Math.max(...temps.map(([, v]) => v)) : m?.gpu_temp_c;
  const lat = latency || { total_ms: status?.ai?.latency_ms, first_token_ms: status?.ai?.first_token_ms };
  const allWarnings = warnings.length ? warnings : status?.warnings || [];

  return (
    <div className="h-full overflow-y-auto p-6">
      <div className="mx-auto max-w-6xl space-y-4">
        <div className="glass flex items-center gap-5 p-5">
          <Orb size={92} />
          <div className="min-w-0 flex-1">
            <div className="section-title">{t("dash.ai")}</div>
            <div className="mt-1 text-xl font-semibold text-white">{t(`orb.${orb}` as any)}</div>
            <div className="mt-1 flex flex-wrap gap-2 text-xs">
              <span className="chip"><Bot size={11} />{status?.ai?.model || "—"}</span>
              <span className={`chip ${status?.ai?.cloud ? "text-sky-200" : "text-emerald-200"}`}>{status?.ai?.provider}{status?.ai?.cloud ? " · cloud" : " · local"}</span>
              {status?.ai?.supports_vision && <span className="chip">vision</span>}
              <span className="chip"><Timer size={11} />{t("dash.uptime")} {Math.round((status?.uptime_s || 0) / 60)}m</span>
              <span className="chip">v{status?.version} · {status?.platform}</span>
            </div>
          </div>
          <div className="text-end">
            <div className="section-title">{t("dash.latency")}</div>
            <div className="mt-1 text-2xl font-semibold tabular-nums text-white">{lat?.total_ms != null ? `${(lat.total_ms / 1000).toFixed(1)}s` : "—"}</div>
            <div className="text-xs text-zinc-500">{lat?.first_token_ms != null ? `${t("dash.first_token")} ${lat.first_token_ms} ms` : ""}</div>
          </div>
        </div>

        {allWarnings.length > 0 && (
          <div className="flex flex-col gap-1 rounded-xl border border-amber-400/30 bg-amber-400/10 p-3 text-sm text-amber-200">
            <div className="flex items-center gap-2 font-medium"><AlertTriangle size={15} />{t("dash.warnings")}</div>
            {allWarnings.map((w: string) => <div key={w} className="ps-6 text-xs">{w}</div>)}
          </div>
        )}

        <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
          <Stat icon={<Cpu size={14} />} label={t("dash.cpu")} value={`${Math.round(m?.cpu_percent ?? 0)}%`} meter={m?.cpu_percent} sub={<Sparkline values={history.cpu} />} />
          <Stat icon={<MemoryStick size={14} />} label={t("dash.ram")} value={`${Math.round(m?.ram_percent ?? 0)}%`} meter={m?.ram_percent}
                sub={`${m?.ram_used_gb ?? "—"} / ${m?.ram_total_gb ?? "—"} GB`} />
          <Stat icon={<Gauge size={14} />} label={t("dash.gpu")} value={m?.gpu_percent != null ? `${Math.round(m.gpu_percent)}%` : "—"} meter={m?.gpu_percent ?? undefined} sub={m?.gpu_name || "No GPU telemetry (NVIDIA only, or FRISTY PC Manager)"} />
          <Stat icon={<Thermometer size={14} />} label={t("dash.temp")} value={maxTemp != null ? `${Math.round(maxTemp)}°C` : "—"} meter={maxTemp ?? undefined}
                sub={temps.length ? temps.slice(0, 2).map(([k, v]) => `${k} ${Math.round(v)}°`).join(" · ") : "Sensors not exposed by Windows without FRISTY PC Manager"} />
        </div>

        <div className="grid gap-4 lg:grid-cols-3">
          <Card className="lg:col-span-2" title={t("dash.recent")} icon={<ScrollText size={13} />}
                actions={<button className="btn-ghost h-7 px-2 text-xs" onClick={() => setState({ page: "history" })}>→</button>}>
            {status?.recent_actions?.length ? (
              <ul className="divide-y divide-white/[0.04] text-sm">
                {status.recent_actions.slice(0, 9).map((a: any) => (
                  <li key={a.id} className="flex items-center gap-3 py-1.5">
                    <span className={`h-1.5 w-1.5 shrink-0 rounded-full ${a.status === "success" || a.status === "approved" || a.status === "ok" ? "bg-emerald-400" : a.status ? "bg-red-400" : "bg-zinc-500"}`} />
                    <span className="w-40 shrink-0 truncate font-mono text-[12px] text-accent2">{a.action || a.event}</span>
                    <span className="min-w-0 flex-1 truncate text-zinc-400">{a.event} · {a.status} · {a.source}</span>
                    <span className="text-xs text-zinc-600">{fmtAgo(a.ts)}</span>
                  </li>
                ))}
              </ul>
            ) : <Empty>{t("dash.none")}</Empty>}
          </Card>
          <div className="space-y-4">
            <Card title={t("dash.mic")} icon={micEnabled ? <Mic size={13} /> : <MicOff size={13} />}>
              <div className="text-sm text-zinc-300">{micEnabled ? t("mic.on") : t("mic.off")}</div>
              <div className="mt-1 text-xs text-zinc-500">{wake ? t("wake.on") : ""} {status?.voice?.local_stt_available ? "· Whisper ready" : "· local STT not installed"}</div>
            </Card>
            <Card title={t("dash.automations")} icon={<Workflow size={13} />}>
              {status?.automations?.items?.length ? (
                <ul className="space-y-1 text-sm">
                  {status.automations.items.slice(0, 5).map((a: any) => (
                    <li key={a.id} className="flex items-center justify-between">
                      <span className={a.enabled ? "text-zinc-200" : "text-zinc-500 line-through"}>{a.name}</span>
                      <span className="chip">{a.trigger}</span>
                    </li>
                  ))}
                </ul>
              ) : <Empty>{t("dash.none")}</Empty>}
            </Card>
          </div>
        </div>

        <div className="grid gap-4 lg:grid-cols-2">
          <Card title={t("dash.integrations")} icon={<Plug size={13} />}>
            <ul className="space-y-2 text-sm">
              {(status?.integrations || []).map((i: any) => (
                <li key={i.key} className="flex items-center justify-between">
                  <span className="text-zinc-200">{i.name}</span>
                  <span className={`chip ${!i.enabled ? "" : i.connected ? "border-emerald-400/40 text-emerald-300" : "border-red-400/30 text-red-300"}`}>
                    {!i.enabled ? t("dash.disabled") : i.connected ? t("dash.connected") : t("dash.disconnected")}
                  </span>
                </li>
              ))}
              <li className="flex items-center justify-between">
                <span className="text-zinc-200">FRISTY Remote</span>
                <span className={`chip ${status?.remote?.running ? "border-emerald-400/40 text-emerald-300" : ""}`}>
                  {status?.remote?.enabled ? `${status.remote.devices} device(s)` : t("dash.disabled")}
                </span>
              </li>
            </ul>
          </Card>
          <Card title={t("dash.conversations")} icon={<MessageSquare size={13} />}>
            {conversations.length ? (
              <ul className="space-y-0.5 text-sm">
                {conversations.slice(0, 6).map((c) => (
                  <li key={c.id}><button className="flex w-full justify-between rounded-lg px-2 py-1 text-start text-zinc-300 hover:bg-white/[0.04]" onClick={() => void openConversation(c.id)}>
                    <span className="truncate" dir="auto">{c.title}</span><span className="text-xs text-zinc-600">{fmtAgo(c.updated_at)}</span></button></li>
                ))}
              </ul>
            ) : <Empty>{t("dash.none")}</Empty>}
          </Card>
        </div>
        <div className="flex items-center justify-center gap-2 pb-2 text-[11px] text-zinc-600">
          <Activity size={11} />backend {m?.backend?.rss_mb ?? "—"} MB RAM · <HardDrive size={11} /> {t("set.data_dir")}
        </div>
      </div>
    </div>
  );
}
