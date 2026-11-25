import { CheckCircle2, XCircle, AlertCircle, Loader2, ChevronDown } from "lucide-react";
import { useState } from "react";
import { useT } from "../lib/i18n";
import { ActionEntry } from "../lib/store";

export default function ActionCard({ a }: { a: ActionEntry }) {
  const t = useT();
  const [open, setOpen] = useState(false);
  const state = a.pending ? "running" : !a.ok ? "failed" : a.verified === false ? "failed" : a.verified ? "verified" : "unverified";
  const style = {
    running: { cls: "border-accent/30 bg-accent/5", icon: <Loader2 size={15} className="animate-spin text-accent2" />, label: t("action.running") },
    verified: { cls: "border-emerald-400/25 bg-emerald-400/[0.04]", icon: <CheckCircle2 size={15} className="text-emerald-300" />, label: t("action.verified") },
    unverified: { cls: "border-amber-400/25 bg-amber-400/[0.04]", icon: <AlertCircle size={15} className="text-amber-300" />, label: t("action.unverified") },
    failed: { cls: "border-red-500/30 bg-red-500/[0.05]", icon: <XCircle size={15} className="text-red-300" />, label: t("action.failed") },
  }[state];
  const hasDetails = a.data && Object.keys(a.data).length > 0;
  return (
    <div className={`rounded-xl border text-sm ${style.cls}`}>
      <button className="flex w-full items-center gap-2.5 px-3 py-2 text-start" onClick={() => hasDetails && setOpen(!open)}>
        {style.icon}
        <span className="font-mono text-[12px] text-accent2">{a.name}</span>
        <span className="min-w-0 flex-1 truncate text-zinc-300">{a.message || JSON.stringify(a.arguments)}</span>
        <span className="text-[10px] uppercase tracking-wider text-zinc-500">{style.label}</span>
        {hasDetails && <ChevronDown size={14} className={`text-zinc-500 transition ${open ? "rotate-180" : ""}`} />}
      </button>
      {open && hasDetails && (
        <pre className="selectable max-h-64 overflow-auto border-t border-white/5 px-3 py-2 font-mono text-[11px] text-zinc-400" dir="ltr">{JSON.stringify(a.data, null, 2)}</pre>
      )}
    </div>
  );
}
