import { AnimatePresence, motion } from "framer-motion";
import { Download, RefreshCw, X, CheckCircle2, ExternalLink } from "lucide-react";
import Markdown from "./Markdown";
import { bridge } from "../lib/bridge";
import { checkForUpdates, installUpdate } from "../lib/controller";
import { useT } from "../lib/i18n";
import { setState, useStore } from "../lib/store";

function mb(n: number) {
  return `${(n / 1e6).toFixed(0)} MB`;
}

export default function UpdateDialog() {
  const t = useT();
  const open = useStore((s) => s.updateOpen);
  const u = useStore((s) => s.update);
  const checking = useStore((s) => s.updateChecking);
  const progress = useStore((s) => s.updateProgress);
  const installing = useStore((s) => s.updateInstalling);
  const pct = progress && progress.total ? Math.round((100 * progress.received) / progress.total) : 0;
  return (
    <AnimatePresence>
      {open && (
        <motion.div className="fixed inset-0 z-50 grid place-items-center bg-black/70 p-4 backdrop-blur-sm" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
          <motion.div className="glass-strong w-full max-w-lg p-5" initial={{ scale: 0.95 }} animate={{ scale: 1 }}>
            <div className="flex items-center justify-between">
              <h2 className="text-lg font-semibold text-white">{t("upd.title")}</h2>
              {!installing && <button className="btn-ghost h-8 w-8 p-0" onClick={() => setState({ updateOpen: false })}><X size={16} /></button>}
            </div>
            <div className="mt-1 text-sm text-zinc-400">{t("upd.current", { v: u?.current || "—" })}</div>
            {checking && <div className="mt-4 flex items-center gap-2 text-sm text-zinc-300"><RefreshCw size={14} className="animate-spin" />{t("upd.checking")}</div>}
            {!checking && u && (
              u.available ? (
                <div className="mt-4">
                  <div className="text-base font-medium text-accent2">{t("upd.available", { v: u.latest })}</div>
                  {u.notes && <div className="mt-2 max-h-48 overflow-auto rounded-lg border border-white/10 bg-black/40 p-3 text-sm text-zinc-300"><Markdown text={u.notes} /></div>}
                  {installing ? (
                    <div className="mt-4">
                      <div className="h-2 w-full overflow-hidden rounded-full bg-white/[0.07]">
                        <motion.div className="h-full rounded-full bg-gradient-to-r from-accent to-accent2" animate={{ width: `${Math.max(2, pct)}%` }} />
                      </div>
                      <div className="mt-1 flex justify-between text-xs text-zinc-500" dir="ltr">
                        <span>{progress ? `${mb(progress.received)} / ${mb(progress.total)}` : t("upd.starting")}</span><span>{pct}%</span>
                      </div>
                      <p className="mt-2 text-xs text-zinc-400">{pct >= 100 ? t("upd.restarting") : t("upd.downloading")}</p>
                    </div>
                  ) : (
                    <div className="mt-4 flex justify-end gap-2">
                      <button className="btn-outline" onClick={() => setState({ updateOpen: false })}>{t("upd.later")}</button>
                      <button className="btn-primary" onClick={() => void installUpdate()}><Download size={14} />{t("upd.install")}</button>
                    </div>
                  )}
                </div>
              ) : (
                <div className="mt-4">
                  {u.error && u.error !== "no_release" ? (
                    <p className="text-sm text-red-300">{t("upd.error")}: {u.error}</p>
                  ) : (
                    <p className="flex items-center gap-2 text-sm text-emerald-300"><CheckCircle2 size={15} />{t("upd.latest")}</p>
                  )}
                  <div className="mt-4 flex justify-end gap-2">
                    {u.releaseUrl && <button className="btn-ghost" onClick={() => void bridge.openExternal(u.releaseUrl)}><ExternalLink size={14} />GitHub</button>}
                    <button className="btn-outline" onClick={() => void checkForUpdates(false)}><RefreshCw size={14} />{t("upd.check")}</button>
                  </div>
                </div>
              )
            )}
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
