import { AnimatePresence, motion } from "framer-motion";
import { ShieldAlert, ShieldCheck, Shield, AlertTriangle } from "lucide-react";
import { useEffect, useState } from "react";
import { decide } from "../lib/controller";
import { useT } from "../lib/i18n";
import { Confirmation, useStore } from "../lib/store";

const RISK = {
  low: { cls: "border-emerald-400/40 text-emerald-300", icon: ShieldCheck },
  medium: { cls: "border-amber-400/40 text-amber-300", icon: Shield },
  high: { cls: "border-red-500/50 text-red-300", icon: ShieldAlert },
};

function Countdown({ c }: { c: Confirmation }) {
  const t = useT();
  const [now, setNow] = useState(Date.now());
  useEffect(() => { const i = setInterval(() => setNow(Date.now()), 500); return () => clearInterval(i); }, []);
  const left = Math.max(0, Math.round(c.timeout - (now - c.receivedAt) / 1000));
  return <span className="text-xs text-zinc-500">{t("confirm.expires", { s: left })}</span>;
}

function Preview({ details }: { details: any }) {
  const t = useT();
  const prev = details?.preview;
  const plan = details?.plan;
  const steps: string[] | undefined = details?.steps;
  if (plan?.steps) {
    return (
      <ol className="mt-3 space-y-1.5">
        {plan.steps.map((s: any, i: number) => (
          <li key={i} className={`flex items-start gap-2 rounded-lg border px-3 py-2 text-sm ${s.valid ? "border-white/10 bg-white/[0.03]" : "border-red-500/30 bg-red-500/5 text-zinc-500 line-through"}`}>
            <span className="mt-0.5 grid h-5 w-5 shrink-0 place-items-center rounded-full bg-accent/20 text-[10px] text-accent2">{i + 1}</span>
            <span className="min-w-0">
              <span className="font-mono text-[12px] text-accent2">{s.summary || s.action}</span>
              {s.description && <span className="block text-xs text-zinc-400">{s.description}</span>}
              {!s.valid && <span className="block text-xs text-red-300 no-underline">{t("plan.invalid")}: {s.error}</span>}
              {s.valid && s.needs_confirmation && <span className="block text-[11px] text-amber-300">⚠ asks again before running</span>}
            </span>
          </li>
        ))}
      </ol>
    );
  }
  if (steps) return <ol className="mt-3 space-y-1 font-mono text-xs text-zinc-300">{steps.map((s, i) => <li key={i}>{s}</li>)}</ol>;
  if (prev?.diff !== undefined) {
    return (
      <div className="mt-3">
        <div className="label">{t("confirm.diff")} · {prev.path}</div>
        <pre className="max-h-72 overflow-auto rounded-xl border border-white/10 bg-black/60 p-3 font-mono text-[11.5px] leading-snug" dir="ltr">
          {String(prev.diff || "(no changes)").split("\n").map((l: string, i: number) => (
            <div key={i} className={l.startsWith("+") && !l.startsWith("+++") ? "text-emerald-300" : l.startsWith("-") && !l.startsWith("---") ? "text-red-300" : l.startsWith("@@") ? "text-sky-300" : "text-zinc-400"}>{l || " "}</div>
          ))}
        </pre>
      </div>
    );
  }
  if (prev?.plan) {
    return (
      <div className="mt-3 grid grid-cols-2 gap-2 text-xs">
        {Object.entries(prev.plan as Record<string, string[]>).map(([cat, files]) => (
          <div key={cat} className="rounded-lg border border-white/10 bg-white/[0.03] p-2"><b className="text-zinc-200">{cat}</b> <span className="text-zinc-500">({files.length})</span></div>
        ))}
      </div>
    );
  }
  if (prev?.command) {
    return (
      <div className="mt-3 space-y-1 text-xs">
        <pre className="rounded-lg border border-white/10 bg-black/60 p-2 font-mono text-[12px] text-zinc-200" dir="ltr">{prev.command}</pre>
        <div className="text-zinc-500" dir="ltr">cwd: {prev.cwd}</div>
        {prev.installs_dependencies && <div className="text-amber-300">⚠ This installs dependencies.</div>}
      </div>
    );
  }
  if (prev?.files) return <ul className="mt-3 max-h-40 overflow-auto font-mono text-xs text-zinc-400" dir="ltr">{prev.files.map((f: string) => <li key={f}>{f}</li>)}</ul>;
  const args = details?.args;
  if (args && Object.keys(args).length) {
    return <pre className="mt-3 max-h-48 overflow-auto rounded-lg border border-white/10 bg-black/50 p-2 font-mono text-[11.5px] text-zinc-300" dir="ltr">{JSON.stringify(args, null, 2)}</pre>;
  }
  return null;
}

export default function ConfirmDialog() {
  const t = useT();
  const list = useStore((s) => s.confirmations);
  const c = list[0];
  useEffect(() => {
    if (!c) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") void decide(c.id, false); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [c]);
  const r = RISK[c?.risk || "medium"] || RISK.medium;
  const Icon = r.icon;
  return (
    <AnimatePresence>
      {c && (
        <motion.div key={c.id} className="fixed inset-0 z-50 grid place-items-center bg-black/70 p-4 backdrop-blur-sm"
          initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
          <motion.div role="alertdialog" aria-labelledby="confirm-title" className="glass-strong w-full max-w-lg p-5 shadow-glow-lg"
            initial={{ scale: 0.94, y: 12 }} animate={{ scale: 1, y: 0 }} exit={{ scale: 0.96, opacity: 0 }}>
            <div className="flex items-center justify-between">
              <div className={`chip ${r.cls}`}><Icon size={12} />{t(`confirm.risk.${c.risk}` as any)}</div>
              <Countdown c={c} />
            </div>
            <h2 id="confirm-title" className="mt-3 text-lg font-semibold text-white">{c.action === "agent_plan" ? t("confirm.plan") : t("confirm.title")}</h2>
            <p className="mt-1 text-sm text-zinc-300 selectable">{c.summary}</p>
            <p className="mt-1 text-xs text-zinc-500">{t("confirm.source")}: <span className="text-zinc-300">{c.source}</span>{list.length > 1 && <> · +{list.length - 1}</>}</p>
            {c.details?.untrusted_context && (
              <div className="mt-3 flex gap-2 rounded-lg border border-amber-400/30 bg-amber-400/10 p-2.5 text-xs text-amber-200"><AlertTriangle size={14} className="shrink-0" />{t("confirm.untrusted")}</div>
            )}
            <Preview details={c.details} />
            <div className="mt-5 flex justify-end gap-2">
              <button className="btn-outline" onClick={() => void decide(c.id, false)}>{t("confirm.deny")}</button>
              <button autoFocus={c.risk !== "high"} className={c.risk === "high" ? "btn-danger" : "btn-primary"} onClick={() => void decide(c.id, true)}>{t("confirm.approve")}</button>
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
