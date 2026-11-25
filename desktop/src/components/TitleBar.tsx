import { Minus, Square, X, PictureInPicture2, OctagonX, Cloud, Cpu, ScanEye, Mic, MicOff, Download } from "lucide-react";
import { bridge } from "../lib/bridge";
import { checkForUpdates, emergencyStop, setMicEnabled } from "../lib/controller";
import { useT } from "../lib/i18n";
import { useStore } from "../lib/store";
import { PullingIndicator } from "./LocalModels";

export default function TitleBar() {
  const t = useT();
  const status = useStore((s) => s.status);
  const screenActive = useStore((s) => s.screenActive);
  const micEnabled = useStore((s) => s.micEnabled);
  const wake = useStore((s) => s.wakeListening);
  const listening = useStore((s) => s.listening);
  const cloud = status?.ai?.cloud;
  const updateAvailable = useStore((s) => !!s.update?.available);
  const provider = status?.ai?.provider;

  return (
    <div className="drag flex h-11 shrink-0 items-center justify-between border-b border-white/[0.05] bg-black/30 ps-4 backdrop-blur-xl" dir="ltr">
      <div className="flex items-center gap-2.5">
        <div className="relative h-5 w-5">
          <div className="absolute inset-0 rounded-full bg-accent blur-[6px] opacity-70" />
          <div className="absolute inset-[3px] rounded-full bg-gradient-to-br from-white to-accent" />
        </div>
        <span className="text-[13px] font-semibold tracking-[0.32em] text-white">FRISTY<span className="text-accent"> AI</span></span>
      </div>
      <div className="no-drag flex items-center gap-1.5">
        {screenActive && (
          <span className="chip border-amber-400/40 bg-amber-400/10 text-amber-200"><ScanEye size={12} className="animate-blink" />{t("screen.active")}</span>
        )}
        <PullingIndicator />
        {wake && <span className="chip border-cyan-400/30 text-cyan-200"><span className="h-1.5 w-1.5 animate-blink rounded-full bg-cyan-300" />{t("wake.on")}</span>}
        {status && (
          <span title={cloud ? t("cloud.warn", { provider }) : undefined}
                className={`chip ${cloud ? "border-sky-400/40 bg-sky-400/10 text-sky-200" : "border-emerald-400/30 bg-emerald-400/10 text-emerald-200"}`}>
            {cloud ? <Cloud size={12} /> : <Cpu size={12} />}{cloud ? `${t("cloud.badge")} · ${provider}` : t("local.badge")}
          </span>
        )}
        <button onClick={() => void checkForUpdates(false)} title={t("upd.button")}
                className={`btn h-7 gap-1.5 border px-2.5 text-[11px] font-semibold uppercase tracking-wider ${updateAvailable ? "border-accent/60 bg-accent/20 text-white shadow-glow" : "border-white/10 text-zinc-400 hover:text-white"}`}>
          <Download size={13} />{t("upd.button")}
          {updateAvailable && <span className="h-1.5 w-1.5 animate-blink rounded-full bg-accent2" />}
        </button>
        <button onClick={() => void setMicEnabled(!micEnabled)} title={t("mic.toggle")}
                className={`btn-ghost h-7 px-2 ${!micEnabled ? "text-red-300" : listening ? "text-cyan-300" : ""}`}>
          {micEnabled ? <Mic size={14} className={listening ? "animate-blink" : ""} /> : <MicOff size={14} />}
        </button>
        <button onClick={() => void emergencyStop()} title={t("estop")}
                className="btn h-7 border border-red-500/40 bg-red-500/10 px-2.5 text-[11px] font-semibold uppercase tracking-wider text-red-300 hover:bg-red-500/25">
          <OctagonX size={13} />{t("estop")}
        </button>
        <div className="ms-2 flex">
          <button className="grid h-11 w-11 place-items-center text-zinc-400 hover:bg-white/5 hover:text-white" onClick={() => void bridge.setCompact(true)} title={t("compact.collapse")}><PictureInPicture2 size={14} /></button>
          <button className="grid h-11 w-11 place-items-center text-zinc-400 hover:bg-white/5 hover:text-white" onClick={() => void bridge.minimize()}><Minus size={14} /></button>
          <button className="grid h-11 w-11 place-items-center text-zinc-400 hover:bg-white/5 hover:text-white" onClick={() => void bridge.maximize()}><Square size={12} /></button>
          <button className="grid h-11 w-11 place-items-center text-zinc-400 hover:bg-red-600 hover:text-white" onClick={() => void bridge.close()}><X size={15} /></button>
        </div>
      </div>
    </div>
  );
}
