import { ReactNode } from "react";
import { motion } from "framer-motion";

export function Toggle({ checked, onChange, label, description, disabled }: { checked: boolean; onChange: (v: boolean) => void; label?: ReactNode; description?: ReactNode; disabled?: boolean }) {
  return (
    <label className={`flex items-start justify-between gap-4 py-2 ${disabled ? "opacity-50" : "cursor-pointer"}`}>
      {(label || description) && (
        <span className="min-w-0">
          {label && <span className="block text-sm text-zinc-100">{label}</span>}
          {description && <span className="mt-0.5 block text-xs text-zinc-500">{description}</span>}
        </span>
      )}
      <button type="button" role="switch" aria-checked={checked} disabled={disabled} onClick={() => onChange(!checked)}
        className={`relative mt-0.5 h-6 w-11 shrink-0 rounded-full border transition ${checked ? "border-accent/60 bg-accent/70 shadow-glow" : "border-white/10 bg-white/[0.06]"}`}>
        <motion.span layout transition={{ type: "spring", stiffness: 500, damping: 32 }}
          className="absolute top-0.5 h-[18px] w-[18px] rounded-full bg-white shadow"
          style={{ insetInlineStart: checked ? 22 : 3 }} />
      </button>
    </label>
  );
}

export function Card({ title, icon, actions, children, className = "" }: { title?: ReactNode; icon?: ReactNode; actions?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <section className={`glass p-4 ${className}`}>
      {(title || actions) && (
        <header className="mb-3 flex items-center justify-between gap-2">
          <h3 className="section-title flex items-center gap-2">{icon}{title}</h3>
          {actions}
        </header>
      )}
      {children}
    </section>
  );
}

export function Field({ label, children, hint }: { label: ReactNode; children: ReactNode; hint?: ReactNode }) {
  return (
    <div className="mb-3">
      <span className="label">{label}</span>
      {children}
      {hint && <p className="mt-1 text-xs text-zinc-500">{hint}</p>}
    </div>
  );
}

export function Select({ value, onChange, options, className = "" }: { value: string; onChange: (v: string) => void; options: { value: string; label: string }[]; className?: string }) {
  return (
    <select className={`input appearance-none ${className}`} value={value} onChange={(e) => onChange(e.target.value)}>
      {options.map((o) => <option key={o.value} value={o.value} className="bg-ink-900">{o.label}</option>)}
    </select>
  );
}

export function Meter({ value, max = 100, warn = 80, danger = 92 }: { value: number | null | undefined; max?: number; warn?: number; danger?: number }) {
  const v = Math.max(0, Math.min(100, ((value ?? 0) / max) * 100));
  const color = (value ?? 0) >= danger ? "bg-red-500" : (value ?? 0) >= warn ? "bg-amber-400" : "bg-accent";
  return (
    <div className="h-1.5 w-full overflow-hidden rounded-full bg-white/[0.06]">
      <motion.div className={`h-full rounded-full ${color}`} initial={false} animate={{ width: `${v}%` }} transition={{ duration: 0.6 }} />
    </div>
  );
}

export function Empty({ children }: { children: ReactNode }) {
  return <div className="py-6 text-center text-sm text-zinc-500">{children}</div>;
}

export function Spinner({ className = "h-4 w-4" }: { className?: string }) {
  return <span className={`inline-block animate-spin rounded-full border-2 border-white/20 border-t-accent ${className}`} />;
}
