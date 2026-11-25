import { AnimatePresence, motion } from "framer-motion";
import { lazy, Suspense, useEffect } from "react";
import ConfirmDialog from "./components/ConfirmDialog";
import UpdateDialog from "./components/UpdateDialog";
import Orb from "./components/Orb";
import Sidebar from "./components/Sidebar";
import TitleBar from "./components/TitleBar";
import Toasts from "./components/Toasts";
import { Spinner } from "./components/ui";
import { bridge } from "./lib/bridge";
import { boot } from "./lib/controller";
import { useT } from "./lib/i18n";
import { useStore } from "./lib/store";
import ChatPage from "./pages/ChatPage";
import CompactView from "./pages/CompactView";

const DashboardPage = lazy(() => import("./pages/DashboardPage"));
const AutomationsPage = lazy(() => import("./pages/AutomationsPage"));
const MemoryPage = lazy(() => import("./pages/MemoryPage"));
const HistoryPage = lazy(() => import("./pages/HistoryPage"));
const SettingsPage = lazy(() => import("./pages/SettingsPage"));

function BackendGate() {
  const t = useT();
  const ready = useStore((s) => s.backendReady && !!s.settings);
  const error = useStore((s) => s.backendError);
  if (ready) return null;
  return (
    <div className="absolute inset-0 z-40 flex flex-col items-center justify-center bg-ink-950/95">
      <Orb size={160} />
      <div className="mt-4 text-sm text-zinc-300">{error ? t("backend.error") : t("backend.starting")}</div>
      {error ? (
        <>
          <pre className="selectable mt-3 max-h-40 max-w-xl overflow-auto rounded-lg border border-red-500/30 bg-red-500/5 p-3 text-xs text-red-200" dir="ltr">{error}</pre>
          <button className="btn-primary mt-4" onClick={() => void bridge.restartBackend()}>{t("backend.retry")}</button>
        </>
      ) : <Spinner className="mt-3 h-5 w-5" />}
    </div>
  );
}

export default function App() {
  const page = useStore((s) => s.page);
  const compact = useStore((s) => s.compact);
  useEffect(() => { void boot(); }, []);

  const pages = { chat: <ChatPage />, dashboard: <DashboardPage />, automations: <AutomationsPage />, memory: <MemoryPage />,
                  history: <HistoryPage />, settings: <SettingsPage /> };

  if (compact) {
    return (
      <div className="relative h-full overflow-hidden rounded-none border border-accent/20">
        <CompactView /><ConfirmDialog /><Toasts /><BackendGate />
      </div>
    );
  }
  return (
    <div className="relative flex h-full flex-col">
      <TitleBar />
      <div className="flex min-h-0 flex-1">
        <Sidebar />
        <main className="relative min-w-0 flex-1">
          <AnimatePresence mode="wait">
            <motion.div key={page} className="absolute inset-0" initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} transition={{ duration: 0.18 }}>
              <Suspense fallback={<div className="grid h-full place-items-center"><Spinner className="h-6 w-6" /></div>}>{pages[page]}</Suspense>
            </motion.div>
          </AnimatePresence>
        </main>
      </div>
      <ConfirmDialog />
      <UpdateDialog />
      <Toasts />
      <BackendGate />
    </div>
  );
}
