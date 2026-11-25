import { AnimatePresence, motion } from "framer-motion";
import { Check, Download, Eye, HardDrive, Loader2, RefreshCw, Trash2, Wrench, X, Cpu, ExternalLink } from "lucide-react";
import { useEffect, useState } from "react";
import { bridge } from "../lib/bridge";
import { cancelModel, deleteModel, installModel, refreshLocalModels, saveSettings } from "../lib/controller";
import { useLang, useT } from "../lib/i18n";
import { useStore } from "../lib/store";

function fmtBytes(n: number) {
  return n > 1e9 ? `${(n / 1e9).toFixed(2)} GB` : `${Math.round(n / 1e6)} MB`;
}

export function PullProgress({ job }: { job: any }) {
  return (
    <div className="w-full">
      <div className="h-1.5 w-full overflow-hidden rounded-full bg-white/[0.07]">
        <motion.div className="h-full rounded-full bg-gradient-to-r from-accent to-accent2" initial={false}
          animate={{ width: `${Math.max(2, job.percent || 0)}%` }} transition={{ duration: 0.4 }} />
      </div>
      <div className="mt-1 flex justify-between text-[11px] text-zinc-500" dir="ltr">
        <span>{job.total ? `${fmtBytes(job.completed)} / ${fmtBytes(job.total)}` : job.detail}</span>
        <span>{(job.percent || 0).toFixed(0)}%</span>
      </div>
    </div>
  );
}

function OllamaMissing() {
  const t = useT();
  return (
    <div className="rounded-xl border border-amber-400/30 bg-amber-400/[0.07] p-4">
      <div className="font-medium text-amber-100">{t("models.ollama_missing")}</div>
      <p className="mt-1 text-xs text-zinc-400">{t("models.ollama_missing_sub")}</p>
      <div className="mt-3 flex gap-2">
        <button className="btn-primary" onClick={() => void bridge.openExternal("https://ollama.com/download/windows")}><ExternalLink size={14} />{t("models.get_ollama")}</button>
        <button className="btn-outline" onClick={() => void refreshLocalModels()}><RefreshCw size={14} />{t("models.check_again")}</button>
      </div>
    </div>
  );
}

/** Full model manager (Settings → AI). */
export default function LocalModels() {
  const t = useT();
  const lang = useLang();
  const lm = useStore((s) => s.localModels);
  const pulls = useStore((s) => s.pulls);
  const current = useStore((s) => s.settings?.ai?.model);
  const [custom, setCustom] = useState("");
  useEffect(() => { void refreshLocalModels(); }, []);
  if (!lm) return <div className="py-4 text-sm text-zinc-500">{t("common.loading")}</div>;
  if (!lm.ollama_running) return <OllamaMissing />;
  const curatedIds = new Set(lm.models.map((m: any) => m.id));
  const others = (lm.installed as string[]).filter((id) => !curatedIds.has(id) && !curatedIds.has(id.replace(/:latest$/, "")));

  return (
    <div>
      <div className="mb-3 flex items-center gap-2 text-xs text-zinc-400">
        <Cpu size={13} />{t("models.your_pc", { ram: lm.ram_gb })} · Ollama {lm.ollama_version}
      </div>
      <div className="grid gap-2 md:grid-cols-2">
        {lm.models.map((m: any) => {
          const job = pulls[m.id];
          const downloading = job?.status === "downloading";
          const active = current === m.id;
          return (
            <motion.div layout key={m.id} className={`rounded-xl border p-3 ${m.recommended ? "border-accent/40 bg-accent/[0.06]" : "border-white/10 bg-white/[0.02]"} ${!m.fits ? "opacity-60" : ""}`}>
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-1.5 text-sm font-medium text-white">
                    {m.name}
                    {m.recommended && <span className="chip border-accent/50 text-accent2">{t("models.recommended")}</span>}
                    {active && <span className="chip border-emerald-400/40 text-emerald-300"><Check size={10} />{t("models.active")}</span>}
                  </div>
                  <div className="mt-0.5 text-xs text-zinc-400">{lang === "he" ? m.he : m.en}</div>
                  <div className="mt-1.5 flex flex-wrap gap-1 text-[10px]">
                    <span className="chip"><HardDrive size={10} />{m.size_gb} GB</span>
                    <span className="chip">RAM ≥ {m.min_ram_gb} GB</span>
                    {m.tools && <span className="chip"><Wrench size={10} />{t("models.actions")}</span>}
                    {m.vision && <span className="chip"><Eye size={10} />{t("models.vision")}</span>}
                  </div>
                </div>
                <div className="flex shrink-0 gap-1">
                  {m.installed ? (
                    <>
                      {!active && m.tools && <button className="btn-outline h-8 px-2.5 text-xs" onClick={() => void saveSettings({ ai: { provider: "ollama", model: m.id } })}>{t("models.use")}</button>}
                      <button className="btn-ghost h-8 w-8 p-0 text-zinc-500 hover:text-red-300" title={t("common.delete")} onClick={() => { if (window.confirm(`${t("common.delete")} ${m.id}?`)) void deleteModel(m.id); }}><Trash2 size={13} /></button>
                    </>
                  ) : downloading ? (
                    <button className="btn-ghost h-8 px-2 text-xs" onClick={() => void cancelModel(m.id)}><X size={13} />{t("common.cancel")}</button>
                  ) : (
                    <button className="btn-primary h-8 px-2.5 text-xs" onClick={() => void installModel(m.id)}><Download size={13} />{t("models.install")}</button>
                  )}
                </div>
              </div>
              {downloading && <div className="mt-2.5"><PullProgress job={job} /></div>}
              {job?.status === "error" && <div className="mt-2 text-xs text-red-300">{job.error}</div>}
            </motion.div>
          );
        })}
      </div>
      {others.length > 0 && (
        <div className="mt-3">
          <div className="label">{t("models.other_installed")}</div>
          <div className="flex flex-wrap gap-1.5">
            {others.map((id) => (
              <span key={id} className="chip gap-2 py-1 font-mono">{id}
                <button className="text-zinc-500 hover:text-red-300" onClick={() => { if (window.confirm(`${t("common.delete")} ${id}?`)) void deleteModel(id); }}><X size={11} /></button>
              </span>
            ))}
          </div>
        </div>
      )}
      <div className="mt-3 flex gap-2">
        <input className="input font-mono text-xs" dir="ltr" placeholder={t("models.custom_ph")} value={custom} onChange={(e) => setCustom(e.target.value)} />
        <button className="btn-outline" disabled={!custom.trim()} onClick={() => { void installModel(custom.trim()); setCustom(""); }}><Download size={14} />{t("models.install")}</button>
      </div>
      {Object.values(pulls).filter((j: any) => j.status === "downloading" && !curatedIds.has(j.model)).map((j: any) => (
        <div key={j.model} className="mt-2 rounded-lg border border-white/10 p-2 text-xs"><div className="mb-1 font-mono">{j.model}</div><PullProgress job={j} /></div>
      ))}
    </div>
  );
}

/** First-run banner on the assistant screen when no local model is available. */
export function NoModelBanner() {
  const t = useT();
  const lang = useLang();
  const lm = useStore((s) => s.localModels);
  const provider = useStore((s) => s.settings?.ai?.provider);
  const pulls = useStore((s) => s.pulls);
  if (provider !== "ollama" || !lm) return null;
  if (lm.ollama_running && lm.installed.length > 0) return null;
  const rec = lm.models?.find((m: any) => m.id === lm.main);
  const job = rec ? pulls[rec.id] : null;
  return (
    <AnimatePresence>
      <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} className="glass mt-6 w-full max-w-2xl border-accent/30 p-4">
        {!lm.ollama_running ? <OllamaMissing /> : (
          <div>
            <div className="font-medium text-white">{t("models.none_title")}</div>
            <p className="mt-1 text-sm text-zinc-400">{t("models.none_sub", { name: rec?.name, size: rec?.size_gb, ram: lm.ram_gb })} {lang === "he" ? rec?.he : rec?.en}</p>
            <div className="mt-3">
              {job?.status === "downloading" ? <PullProgress job={job} /> : (
                <button className="btn-primary" onClick={() => rec && void installModel(rec.id)}>
                  {job?.status === "error" ? <RefreshCw size={14} /> : <Download size={14} />}{t("models.install_named", { name: rec?.name })}
                </button>
              )}
              {job?.status === "error" && <div className="mt-2 text-xs text-red-300">{job.error}</div>}
            </div>
          </div>
        )}
      </motion.div>
    </AnimatePresence>
  );
}

export function PullingIndicator() {
  const pulls = useStore((s) => s.pulls);
  const active = Object.values(pulls).filter((j: any) => j.status === "downloading");
  if (!active.length) return null;
  const j: any = active[0];
  return <span className="chip border-accent/40 text-accent2"><Loader2 size={11} className="animate-spin" />{j.model} {Math.round(j.percent || 0)}%</span>;
}
