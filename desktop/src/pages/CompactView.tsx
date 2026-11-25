import { Maximize2, OctagonX, X } from "lucide-react";
import { useEffect, useRef } from "react";
import ActionCard from "../components/ActionCard";
import Markdown from "../components/Markdown";
import Orb from "../components/Orb";
import Waveform from "../components/Waveform";
import { bridge } from "../lib/bridge";
import { emergencyStop, pushToTalk } from "../lib/controller";
import { isRTL, useT } from "../lib/i18n";
import { useStore } from "../lib/store";
import { Composer } from "./ChatPage";

export default function CompactView() {
  const t = useT();
  const messages = useStore((s) => s.messages);
  const orb = useStore((s) => s.orb);
  const listening = useStore((s) => s.listening);
  const speaking = useStore((s) => s.speaking);
  const ref = useRef<HTMLDivElement>(null);
  const recent = messages.slice(-6);
  useEffect(() => { ref.current?.scrollTo({ top: ref.current.scrollHeight }); }, [messages]);
  return (
    <div className="flex h-full flex-col">
      <div className="drag flex items-center justify-between px-3 py-2">
        <span className="text-[11px] font-semibold tracking-[0.3em] text-white">FRISTY</span>
        <div className="no-drag flex gap-1">
          <button className="btn-ghost h-7 w-7 p-0 text-red-300" title={t("estop")} onClick={() => void emergencyStop()}><OctagonX size={14} /></button>
          <button className="btn-ghost h-7 w-7 p-0" title={t("compact.expand")} onClick={() => void bridge.setCompact(false)}><Maximize2 size={13} /></button>
          <button className="btn-ghost h-7 w-7 p-0" onClick={() => void bridge.close()}><X size={14} /></button>
        </div>
      </div>
      <div className="flex flex-col items-center">
        <Orb size={150} onClick={() => void pushToTalk()} />
        <div className="text-sm text-zinc-300">{t(`orb.${orb}` as any)}</div>
        <div className="h-10">{(listening || speaking) && <Waveform bars={20} />}</div>
      </div>
      <div ref={ref} className="flex-1 space-y-3 overflow-y-auto px-3 pb-2">
        {recent.map((m) => (
          <div key={m.id} className={m.role === "user" ? "text-end" : ""}>
            {m.role === "user" ? (
              <span className="inline-block rounded-xl bg-accent/20 px-3 py-1.5 text-[13px] text-white" dir="auto">{m.content}</span>
            ) : (
              <div className="space-y-1">
                {m.actions.map((a) => <ActionCard key={a.id} a={a} />)}
                <div className="text-[13px] text-zinc-200" dir={isRTL(m.content) ? "rtl" : "ltr"}><Markdown text={m.content || (m.streaming ? "…" : "")} /></div>
              </div>
            )}
          </div>
        ))}
      </div>
      <div className="p-2"><Composer compact /></div>
    </div>
  );
}
