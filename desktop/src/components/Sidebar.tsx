import { motion } from "framer-motion";
import { Bot, LayoutDashboard, Workflow, Brain, ScrollText, Settings } from "lucide-react";
import { useT } from "../lib/i18n";
import { Page, setState, useStore } from "../lib/store";

const ITEMS: { page: Page; icon: typeof Bot; key: Parameters<ReturnType<typeof useT>>[0] }[] = [
  { page: "chat", icon: Bot, key: "nav.chat" },
  { page: "dashboard", icon: LayoutDashboard, key: "nav.dashboard" },
  { page: "automations", icon: Workflow, key: "nav.automations" },
  { page: "memory", icon: Brain, key: "nav.memory" },
  { page: "history", icon: ScrollText, key: "nav.history" },
  { page: "settings", icon: Settings, key: "nav.settings" },
];

export default function Sidebar() {
  const t = useT();
  const page = useStore((s) => s.page);
  const pending = useStore((s) => s.confirmations.length);
  return (
    <nav className="flex w-[84px] shrink-0 flex-col items-center gap-1.5 border-e border-white/[0.05] bg-black/20 py-4">
      {ITEMS.map(({ page: p, icon: Icon, key }) => {
        const active = p === page;
        return (
          <button key={p} onClick={() => setState({ page: p })} title={t(key)}
                  className={`group relative flex w-[72px] flex-col items-center gap-1 rounded-xl py-2.5 text-[10px] transition ${active ? "text-white" : "text-zinc-500 hover:text-zinc-200"}`}>
            {active && <motion.span layoutId="nav-active" className="absolute inset-0 rounded-xl border border-accent/40 bg-accent/15 shadow-glow" transition={{ type: "spring", stiffness: 400, damping: 34 }} />}
            <Icon size={19} className="relative" />
            <span className="relative max-w-full truncate px-1">{t(key)}</span>
            {p === "chat" && pending > 0 && <span className="absolute end-2 top-1.5 h-2 w-2 animate-blink rounded-full bg-amber-400" />}
          </button>
        );
      })}
    </nav>
  );
}
