import { AnimatePresence, motion } from "framer-motion";
import { useStore } from "../lib/store";

const KIND = { info: "border-white/10", success: "border-emerald-400/40", error: "border-red-500/50", warning: "border-amber-400/40" };

export default function Toasts() {
  const toasts = useStore((s) => s.toasts);
  return (
    <div className="pointer-events-none fixed bottom-4 end-4 z-[60] flex w-80 flex-col gap-2">
      <AnimatePresence>
        {toasts.map((t) => (
          <motion.div key={t.id} initial={{ opacity: 0, y: 12, scale: 0.96 }} animate={{ opacity: 1, y: 0, scale: 1 }} exit={{ opacity: 0, x: 30 }}
            className={`glass-strong pointer-events-auto border px-3.5 py-2.5 text-sm text-zinc-200 ${KIND[t.kind]}`}>
            {t.text}
          </motion.div>
        ))}
      </AnimatePresence>
    </div>
  );
}
