import { AnimatePresence, motion } from "framer-motion";
import { ArrowUp, Bot, Copy, Mic, MonitorUp, Pause, Play, Plus, Search, Square, Trash2, Volume2, AlertTriangle, ListChecks, Sparkles } from "lucide-react";
import { KeyboardEvent, useEffect, useMemo, useRef, useState } from "react";
import ActionCard from "../components/ActionCard";
import Markdown from "../components/Markdown";
import Orb from "../components/Orb";
import Waveform from "../components/Waveform";
import { askAboutScreen, deleteConversation, newChat, openConversation, pushToTalk, runOp, sendMessage } from "../lib/controller";
import { isRTL, useT } from "../lib/i18n";
import { ChatMessage, toast, useStore } from "../lib/store";
import { speak, stopSpeaking } from "../lib/tts";

function PlanView({ plan }: { plan: any }) {
  const t = useT();
  if (!plan?.steps?.length) return null;
  return (
    <div className="mb-2 rounded-xl border border-accent/20 bg-accent/[0.04] p-3">
      <div className="section-title mb-2 flex items-center gap-1.5"><ListChecks size={13} />{t("plan.title")}</div>
      <ol className="space-y-1 text-[13px]">
        {plan.steps.map((s: any, i: number) => (
          <li key={i} className={`flex gap-2 ${s.valid ? "text-zinc-300" : "text-zinc-500 line-through"}`}>
            <span className="text-accent2">{i + 1}.</span>
            <span className="font-mono text-[12px]">{s.summary || s.action}</span>
            {s.description && <span className="text-zinc-500">— {s.description}</span>}
          </li>
        ))}
      </ol>
    </div>
  );
}

function Message({ m }: { m: ChatMessage }) {
  const t = useT();
  const rtl = isRTL(m.content);
  if (m.role === "user") {
    return (
      <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} className="flex justify-end">
        <div className="max-w-[78%] rounded-2xl rounded-ee-md border border-accent/25 bg-gradient-to-br from-accent/25 to-accent/10 px-4 py-2.5 text-[14.5px] text-white shadow-glow" dir={rtl ? "rtl" : "ltr"}>
          {m.images?.length ? <div className="mb-1 flex items-center gap-1 text-xs text-accent2"><MonitorUp size={12} />{t("chat.attached")}</div> : null}
          <div className="selectable whitespace-pre-wrap">{m.content}</div>
          {m.mode === "agent" && <div className="mt-1 text-[10px] uppercase tracking-wider text-accent2/80">{t("chat.mode.agent")}</div>}
        </div>
      </motion.div>
    );
  }
  return (
    <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} className="flex gap-3">
      <div className="mt-1 grid h-8 w-8 shrink-0 place-items-center rounded-full border border-accent/30 bg-accent/10 text-accent2"><Bot size={16} /></div>
      <div className="min-w-0 max-w-[85%] flex-1">
        <PlanView plan={m.plan} />
        {m.actions.length > 0 && <div className="mb-2 space-y-1.5">{m.actions.map((a) => <ActionCard key={a.id} a={a} />)}</div>}
        {m.content ? (
          <div className="text-[14.5px] text-zinc-200" dir={rtl ? "rtl" : "ltr"}><Markdown text={m.content} /></div>
        ) : m.streaming ? (
          <div className="shimmer-text text-sm">{t("orb.thinking")}</div>
        ) : null}
        {m.streaming && m.content && <span className="ms-0.5 inline-block h-4 w-1.5 animate-blink bg-accent align-middle" />}
        {m.warning === "no_action_executed" && (
          <div className="mt-2 flex items-center gap-2 rounded-lg border border-amber-400/30 bg-amber-400/10 px-3 py-1.5 text-xs text-amber-200"><AlertTriangle size={13} />{t("chat.warn.claim")}</div>
        )}
        {!m.streaming && m.content && (
          <div className="mt-1.5 flex gap-1 opacity-60 transition hover:opacity-100">
            <button className="btn-ghost h-7 px-2 text-xs" onClick={() => { void navigator.clipboard.writeText(m.content); toast("✓", "success", 1000); }}><Copy size={12} />{t("chat.copy")}</button>
            <button className="btn-ghost h-7 px-2 text-xs" onClick={() => void speak(m.content)}><Volume2 size={12} />{t("chat.speak")}</button>
          </div>
        )}
      </div>
    </motion.div>
  );
}

function ConversationList() {
  const t = useT();
  const conversations = useStore((s) => s.conversations);
  const current = useStore((s) => s.conversationId);
  const [q, setQ] = useState("");
  const list = useMemo(() => conversations.filter((c) => !q || c.title.toLowerCase().includes(q.toLowerCase())), [conversations, q]);
  return (
    <aside className="hidden w-64 shrink-0 flex-col border-e border-white/[0.05] bg-black/10 lg:flex">
      <div className="p-3">
        <button className="btn-outline w-full" onClick={newChat}><Plus size={15} />{t("chat.new")}</button>
        <div className="relative mt-2">
          <Search size={14} className="absolute start-2.5 top-2.5 text-zinc-500" />
          <input className="input ps-8" placeholder={t("chat.search")} value={q} onChange={(e) => setQ(e.target.value)} />
        </div>
      </div>
      <div className="section-title px-4 pb-1">{t("chat.history")}</div>
      <div className="flex-1 space-y-0.5 overflow-y-auto px-2 pb-3">
        {list.map((c) => (
          <div key={c.id} className={`group flex items-center rounded-lg ${c.id === current ? "bg-accent/15 text-white" : "text-zinc-400 hover:bg-white/[0.04] hover:text-zinc-200"}`}>
            <button className="min-w-0 flex-1 truncate px-3 py-2 text-start text-[13px]" dir="auto" onClick={() => void openConversation(c.id)}>{c.title}</button>
            <button className="hidden px-2 text-zinc-500 hover:text-red-300 group-hover:block" title={t("chat.delete")} onClick={() => void deleteConversation(c.id)}><Trash2 size={13} /></button>
          </div>
        ))}
      </div>
    </aside>
  );
}

export function Composer({ compact = false }: { compact?: boolean }) {
  const t = useT();
  const [text, setText] = useState("");
  const [mode, setMode] = useState<"chat" | "agent">("chat");
  const run = useStore((s) => s.activeRun);
  const listening = useStore((s) => s.listening);
  const transcribing = useStore((s) => s.transcribing);
  const voiceOn = useStore((s) => s.settings?.voice?.enabled);
  const micEnabled = useStore((s) => s.micEnabled);
  const screenPerm = useStore((s) => s.settings?.permissions?.screen_view);
  const ref = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.style.height = "0px";
    el.style.height = Math.min(180, el.scrollHeight) + "px";
  }, [text]);

  const submit = () => {
    if (!text.trim() || run) return;
    void sendMessage(text.trim(), { mode });
    setText("");
  };
  const onKey = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); submit(); }
  };

  return (
    <div className={`glass ${compact ? "p-2" : "p-2.5"} focus-within:border-accent/40`}>
      {!compact && (
        <div className="mb-2 flex items-center justify-between px-1">
          <div className="flex rounded-lg border border-white/10 bg-black/30 p-0.5 text-xs" title={t("chat.mode.agent_hint")}>
            {(["chat", "agent"] as const).map((m) => (
              <button key={m} onClick={() => setMode(m)} className={`relative rounded-md px-3 py-1 transition ${mode === m ? "text-white" : "text-zinc-500 hover:text-zinc-300"}`}>
                {mode === m && <motion.span layoutId="mode" className="absolute inset-0 rounded-md bg-accent/30" />}
                <span className="relative flex items-center gap-1">{m === "agent" && <Sparkles size={11} />}{t(`chat.mode.${m}`)}</span>
              </button>
            ))}
          </div>
          {run && (
            <div className="flex items-center gap-1">
              {run.mode === "agent" && (run.paused
                ? <button className="btn-ghost h-7 px-2 text-xs" onClick={() => void runOp("resume")}><Play size={12} />{t("chat.resume")}</button>
                : <button className="btn-ghost h-7 px-2 text-xs" onClick={() => void runOp("pause")}><Pause size={12} />{t("chat.pause")}</button>)}
              <button className="btn-ghost h-7 px-2 text-xs text-red-300" onClick={() => void runOp("cancel")}><Square size={11} />{t("chat.stop")}</button>
            </div>
          )}
        </div>
      )}
      <div className="flex items-end gap-2">
        <textarea ref={ref} rows={1} dir="auto" value={text} onChange={(e) => setText(e.target.value)} onKeyDown={onKey}
          placeholder={listening ? t("orb.listening") : t("chat.placeholder")}
          className="max-h-44 min-h-[40px] flex-1 resize-none bg-transparent px-2 py-2.5 text-[14.5px] text-white placeholder:text-zinc-500 focus:outline-none" />
        {screenPerm && !compact && (
          <button className="btn-ghost h-10 w-10 p-0" title={t("chat.screen")} disabled={!!run}
                  onClick={() => { void askAboutScreen(text.trim() || "", mode); setText(""); }}><MonitorUp size={18} /></button>
        )}
        {voiceOn && (
          <button className={`btn h-10 w-10 p-0 ${listening ? "bg-cyan-400/20 text-cyan-200 ring-2 ring-cyan-400/50" : "btn-ghost"}`} title={t("chat.mic")}
                  disabled={!micEnabled || transcribing} onClick={() => { stopSpeaking(); void pushToTalk(); }}>
            {transcribing ? <span className="h-4 w-4 animate-spin rounded-full border-2 border-white/20 border-t-cyan-300" /> : <Mic size={18} />}
          </button>
        )}
        {run ? (
          <button className="btn h-10 w-10 bg-red-500/80 p-0 text-white hover:bg-red-500" title={t("chat.stop")} onClick={() => void runOp("cancel")}><Square size={14} /></button>
        ) : (
          <button className="btn-primary h-10 w-10 p-0" disabled={!text.trim()} onClick={submit} title={t("chat.send")}><ArrowUp size={18} /></button>
        )}
      </div>
    </div>
  );
}

export default function ChatPage() {
  const t = useT();
  const messages = useStore((s) => s.messages);
  const orb = useStore((s) => s.orb);
  const listening = useStore((s) => s.listening);
  const speaking = useStore((s) => s.speaking);
  const status = useStore((s) => s.status);
  const scroller = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = scroller.current;
    if (el) el.scrollTo({ top: el.scrollHeight, behavior: "smooth" });
  }, [messages]);

  const examples = [t("chat.ex1"), t("chat.ex2"), t("chat.ex3"), t("chat.ex4")];
  const empty = messages.length === 0;

  return (
    <div className="flex h-full min-h-0">
      <ConversationList />
      <div className="relative flex min-w-0 flex-1 flex-col">
        <AnimatePresence initial={false}>
          {!empty && (
            <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: "auto" }} exit={{ opacity: 0, height: 0 }}
              className="flex items-center gap-3 border-b border-white/[0.04] px-6 py-2">
              <Orb size={52} />
              <div className="min-w-0">
                <div className="text-sm font-medium text-white">{t(`orb.${orb}` as any)}</div>
                <div className="truncate text-xs text-zinc-500">{status?.ai?.model || "—"} · {status?.ai?.provider}</div>
              </div>
              {(listening || speaking) && <Waveform className="ms-auto" bars={22} />}
            </motion.div>
          )}
        </AnimatePresence>

        <div ref={scroller} className="flex-1 overflow-y-auto">
          {empty ? (
            <div className="flex h-full flex-col items-center justify-center px-6 pb-10">
              <Orb size={250} onClick={() => void pushToTalk()} />
              <div className="mt-2 h-10">{(listening || speaking) && <Waveform />}</div>
              <motion.h1 initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} className="text-2xl font-semibold text-white">{t("chat.empty.title")}</motion.h1>
              <p className="mt-1.5 text-sm text-zinc-400">{t(`orb.${orb}` as any)} · {t("chat.empty.sub")}</p>
              <div className="mt-6 grid w-full max-w-2xl grid-cols-1 gap-2 sm:grid-cols-2">
                {examples.map((ex) => (
                  <button key={ex} onClick={() => void sendMessage(ex, { mode: /,|and| ו/.test(ex) ? "agent" : "chat" })}
                          className="glass px-4 py-3 text-start text-[13px] text-zinc-300 transition hover:border-accent/40 hover:text-white" dir="auto">{ex}</button>
                ))}
              </div>
            </div>
          ) : (
            <div className="mx-auto max-w-3xl space-y-5 px-6 py-6">
              {messages.map((m) => <Message key={m.id} m={m} />)}
            </div>
          )}
        </div>
        <div className="mx-auto w-full max-w-3xl px-6 pb-5"><Composer /></div>
      </div>
    </div>
  );
}
